# Provider model-list fetching (adapters, SSRF guard, response parsing)
# ---------------------------------------------------------------------------
# Provider model fetching (import a new provider by fetching its model list)
# ---------------------------------------------------------------------------

class FetchError(Exception):
    """Raised when fetching or parsing a provider's model list fails."""


@dataclass
class ProviderFetchSpec:
    """Describes how to fetch a model list from a provider API."""
    base_url: str
    adapter: str = "openai"           # openai | anthropic | gemini | models_dev | generic
    api_key: str = ""
    extra_headers: Dict[str, str] = field(default_factory=dict)
    # Generic adapter only:
    items_path: str = ""              # dotted path to the array, e.g. "data" or "result.models"
    id_field: str = ""                # field within each item holding the model id
    name_field: str = ""              # field within each item holding the display name
    allow_local: bool = False         # permit localhost / private IPs (Ollama, LM Studio)
    timeout: int = 15


# Well-known adapter presets: (endpoint suffix, auth mode, items_path, id_field).
FETCH_ADAPTERS = {
    "openai": {
        "label": "OpenAI-compatible (/models)",
        "suffix": "/models",
        "auth": "bearer",
        "items_path": "data",
        "id_field": "id",
        "name_field": "id",
    },
    "anthropic": {
        "label": "Anthropic / Claude (/v1/models)",
        "suffix": "/v1/models",
        "auth": "x-api-key",
        "items_path": "data",
        "id_field": "id",
        "name_field": "display_name",
    },
    "gemini": {
        "label": "Google Gemini (/v1beta/models)",
        "suffix": "/v1beta/models",
        "auth": "query-key",
        "items_path": "models",
        "id_field": "name",
        "name_field": "displayName",
    },
    "models_dev": {
        "label": "models.dev catalog (api.json)",
        "suffix": "",
        "auth": "none",
        "items_path": "",   # handled specially (catalog dump)
        "id_field": "id",
        "name_field": "name",
    },
    "generic": {
        "label": "Generic JSON (custom path)",
        "suffix": "",
        "auth": "bearer",
        "items_path": "data",
        "id_field": "id",
        "name_field": "name",
    },
}


def stale_configured_models(existing_models, fetched_ids):
    """Configured model ids that the API no longer lists (sorted)."""
    if not isinstance(existing_models, dict):
        return []
    fetched = set(fetched_ids)
    return sorted(m for m in existing_models if m not in fetched)


def npm_for_fetch(adapter: str, base_url: str) -> str:
    """Best AI-SDK npm package for a provider fetched from base_url.

    The "openai" fetch format also serves OpenAI-compatible gateways
    (OpenRouter, LiteLLM, vLLM...), which need @ai-sdk/openai-compatible;
    only openai.com itself gets the dedicated package.
    """
    host = ""
    if base_url:
        host = (urllib.parse.urlparse(base_url).hostname or "").lower()
    if adapter == "anthropic":
        return "@ai-sdk/anthropic"
    if adapter == "gemini":
        return "@ai-sdk/google"
    if adapter == "openai" and (host == "openai.com" or host.endswith(".openai.com")):
        return "@ai-sdk/openai"
    return "@ai-sdk/openai-compatible"


def apply_fetched_provider(providers, key, selected, base_url="", api_key="",
                           save_api_key=True, npm="@ai-sdk/openai",
                           remove_missing=False):
    """Merge fetched models into providers[key], persisting the endpoint config.

    - creates the entry with `npm` when missing (an existing npm is kept)
    - writes options.baseURL from the URL the models were fetched from; an
      empty base_url (list/catalog formats) never writes and never clears an
      existing options.baseURL
    - writes options.apiKey only when save_api_key is true and a key was given;
      an existing apiKey is never deleted
    - existing model specs are never overwritten (API listings carry id/name
      only; the catalog auto-match enriches specs separately)
    - remove_missing=True also drops configured models absent from the fetch
      result (opt-in sync; default keeps them)

    Returns (provider_dict, summary) where summary has added/kept/removed ids.
    """
    prov = providers.get(key)
    if not isinstance(prov, dict):
        prov = {"npm": npm, "name": key, "models": {}}
        providers[key] = prov
    if not isinstance(prov.get("models"), dict):
        prov["models"] = {}
    added, kept = [], []
    for mid, spec in selected.items():
        if mid in prov["models"]:
            kept.append(mid)
        else:
            added.append(mid)
        prov["models"].setdefault(mid, dict(spec))
    removed = []
    if remove_missing:
        for mid in sorted(prov["models"]):
            if mid not in selected:
                del prov["models"][mid]
                removed.append(mid)
    if base_url or (save_api_key and api_key):
        opts = prov.get("options")
        if not isinstance(opts, dict):
            opts = {}
            prov["options"] = opts
        if base_url:
            opts["baseURL"] = base_url
        if save_api_key and api_key:
            opts["apiKey"] = api_key
    return prov, {"added": sorted(added), "kept": sorted(kept), "removed": removed}

def api_base_url_for(adapter: str, base_url: str) -> str:
    """The options.baseURL to persist for a fetch, or '' for list formats.

    List/catalog formats (models.dev, generic) fetched a listing URL that is
    *not* an API base, so nothing is persisted for them. Every API-style
    format persists its base; for anthropic/gemini the version segment is
    part of the base the AI SDK expects (Anthropic normalises a bare host,
    Google does not), so it is added when missing.
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    preset = FETCH_ADAPTERS.get(adapter, FETCH_ADAPTERS["generic"])
    if adapter in ("models_dev", "generic"):
        return ""
    version = _version_segment(preset["suffix"]) if preset.get("suffix") else ""
    if not version or _has_version_segment(base, version):
        return base
    return f"{base}/{version}"


def _version_segment(suffix: str) -> str:
    """'v1/models' -> 'v1'; '' when the suffix carries no version segment."""
    first = (suffix or "").strip("/").split("/")[0]
    return first if re.fullmatch(r"v\d+[a-z0-9]*", first or "") else ""


def _has_version_segment(base: str, version: str) -> bool:
    """True when the last path segment of base already is the version."""
    path = urllib.parse.urlparse(base).path.rstrip("/")
    return path.rsplit("/", 1)[-1] == version


def _join_fetch_suffix(base: str, suffix: str) -> str:
    """Append an adapter suffix without duplicating the version segment.

    An SDK base may already carry its version ('https://api.x/v1', '.../v1beta');
    joining 'v1/models' onto it must yield '.../v1/models', not '.../v1/v1/models'.
    """
    base = (base or "").strip().rstrip("/")
    suffix = (suffix or "").strip().strip("/")
    if not suffix:
        return base
    if base.endswith(suffix):
        return base
    version = _version_segment(suffix)
    if version and _has_version_segment(base, version):
        return f"{base}/{suffix.split('/', 1)[1]}"
    return f"{base}/{suffix}"


def _is_local_host(host: str) -> bool:
    """True if host is localhost or resolves to a private/loopback address."""
    if not host:
        return True
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass
    # Resolve hostname; if any resolved address is private, treat as local.
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return True
            except ValueError:
                continue
    except (socket.gaierror, OSError):
        # Cannot resolve; let the request itself fail rather than blocking.
        return False
    return False


def _validate_fetch_url(url: str, allow_local: bool):
    """Basic SSRF guard: require http(s) and block private hosts unless allowed."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("URL must use http:// or https://")
    if not parsed.hostname:
        raise FetchError("URL has no host")
    if not allow_local and _is_local_host(parsed.hostname):
        raise FetchError(
            f"Refusing to fetch from local/private host '{parsed.hostname}'. "
            "Enable 'Allow local URL' for Ollama/LM Studio.")
    return parsed


def _build_fetch_url(spec: ProviderFetchSpec) -> str:
    """Combine base_url + adapter suffix (+ query key for Gemini).

    The join is version-aware: a base that already ends in the adapter's
    version segment ('/v1', '/v1beta') is not doubled.
    """
    preset = FETCH_ADAPTERS.get(spec.adapter, FETCH_ADAPTERS["generic"])
    url = _join_fetch_suffix(spec.base_url, preset["suffix"])
    if preset["auth"] == "query-key" and spec.api_key:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}key={urllib.parse.quote(spec.api_key)}"
    return url


def _build_fetch_headers(spec: ProviderFetchSpec) -> Dict[str, str]:
    preset = FETCH_ADAPTERS.get(spec.adapter, FETCH_ADAPTERS["generic"])
    headers = {"User-Agent": f"{APP_NAME}/{APP_VERSION}", "Accept": "application/json"}
    auth = preset["auth"]
    if spec.api_key and auth == "bearer":
        headers["Authorization"] = f"Bearer {spec.api_key}"
    elif spec.api_key and auth == "x-api-key":
        headers["x-api-key"] = spec.api_key
        headers["anthropic-version"] = "2023-06-01"
    headers.update(spec.extra_headers or {})
    return headers


def _extract_by_path(data, dotted: str):
    """Follow a dotted path; empty path returns data unchanged."""
    if not dotted:
        return data
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _gemini_model_id(raw_id: str) -> str:
    """Gemini ids come as 'models/gemini-1.5-pro'; strip the prefix."""
    if isinstance(raw_id, str) and raw_id.startswith("models/"):
        return raw_id[len("models/"):]
    return raw_id


def parse_fetched_models(data, spec: ProviderFetchSpec) -> dict:
    """Normalize a fetched API response into a {model_id: spec} map."""
    preset = FETCH_ADAPTERS.get(spec.adapter, FETCH_ADAPTERS["generic"])

    # models.dev returns a full catalog dump; flatten across providers.
    if spec.adapter == "models_dev":
        flat = {}
        if isinstance(data, dict):
            for _pid, pdata in data.items():
                if isinstance(pdata, dict) and isinstance(pdata.get("models"), dict):
                    for mid, mspec in pdata["models"].items():
                        flat.setdefault(mid, mspec)
        if not flat:
            raise FetchError("models.dev response contained no models.")
        return flat

    items_path = spec.items_path or preset["items_path"]
    id_field = spec.id_field or preset["id_field"]
    name_field = spec.name_field or preset["name_field"]

    items = _extract_by_path(data, items_path)
    # Some APIs return the array at the top level.
    if items is None and isinstance(data, list):
        items = data
    if not isinstance(items, list):
        raise FetchError(
            f"Could not find a model array at path '{items_path or '(root)'}'. "
            "Check the format / path.")

    out = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get(id_field)
        if not raw_id:
            continue
        mid = _gemini_model_id(raw_id) if spec.adapter == "gemini" else str(raw_id)
        model_spec = {}
        display = item.get(name_field)
        if display and str(display) != mid:
            model_spec["name"] = str(display)
        out[mid] = model_spec
    if not out:
        raise FetchError("No models with a valid id were found in the response.")
    return out


MAX_FETCH_PAGES = 20


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-runs the SSRF guard on every redirect target.

    urllib follows 30x to any host and would replay the Authorization /
    x-api-key headers. Each hop is re-validated with the same guard, and
    credentials are stripped when the origin changes.
    """

    def __init__(self, allow_local: bool):
        super().__init__()
        self.allow_local = allow_local

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_fetch_url(newurl, self.allow_local)
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        old = urllib.parse.urlparse(req.full_url)
        target = urllib.parse.urlparse(newurl)
        if (old.scheme, old.hostname) != (target.scheme, target.hostname):
            sensitive = {"authorization", "x-api-key", "proxy-authorization", "cookie"}
            for key in list(new.headers):
                if key.lower() in sensitive:
                    new.headers.pop(key, None)
        return new


def _guarded_opener(allow_local: bool):
    """An opener that applies _GuardedRedirectHandler to every request."""
    return urllib.request.build_opener(_GuardedRedirectHandler(allow_local))


def _next_page_url(data, spec: ProviderFetchSpec, current_url: str) -> str:
    """URL of the next page, or '' when this was the last one."""
    if not isinstance(data, dict):
        return ""
    parts = urllib.parse.urlsplit(current_url)
    if spec.adapter == "anthropic":
        if not data.get("has_more"):
            return ""
        token = data.get("last_id") or data.get("after_id")
        if not token:
            return ""
        query = {"before_id": "", "after_id": str(token)}
    elif spec.adapter == "gemini":
        token = data.get("nextPageToken")
        if not token:
            return ""
        query = {"pageToken": str(token)}
    else:
        return ""
    params = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    params.update({k: v for k, v in query.items() if v})
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(params),
         parts.fragment))


def _read_page(url, headers, spec, opener):
    """One HTTP(S) request, through the injected opener or the guarded one."""
    if opener is not None:
        raw = opener(url, headers, spec.timeout)
    else:
        req = urllib.request.Request(url, headers=headers)
        try:
            with _guarded_opener(spec.allow_local).open(req, timeout=spec.timeout) as r:
                raw = r.read()
        except FetchError:
            raise
        except Exception as e:  # urllib raises many subclasses; surface uniformly
            raise FetchError(f"Request failed: {e}") from e
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise FetchError(f"Response was not valid JSON: {e}") from e


def fetch_provider_models(spec: ProviderFetchSpec, *, opener=None) -> dict:
    """Fetch and normalize a provider's model list. Returns {model_id: spec}.

    Follows Anthropic (has_more/last_id) and Gemini (nextPageToken)
    pagination up to MAX_FETCH_PAGES.

    `opener` is an optional callable(url, headers, timeout) -> bytes, injected
    for testing so no real network call is made.
    """
    url = _build_fetch_url(spec)
    _validate_fetch_url(url, spec.allow_local)
    headers = _build_fetch_headers(spec)

    merged: dict = {}
    for _page in range(MAX_FETCH_PAGES):
        data = _read_page(url, headers, spec, opener)
        merged.update(parse_fetched_models(data, spec))
        next_url = _next_page_url(data, spec, url)
        if not next_url:
            return merged
        _validate_fetch_url(next_url, spec.allow_local)
        url = next_url
    return merged


