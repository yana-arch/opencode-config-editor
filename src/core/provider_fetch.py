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
    """Combine base_url + adapter suffix (+ query key for Gemini)."""
    preset = FETCH_ADAPTERS.get(spec.adapter, FETCH_ADAPTERS["generic"])
    base = spec.base_url.rstrip("/")
    suffix = preset["suffix"]
    # Only append the suffix when the base doesn't already include it.
    if suffix and not base.endswith(suffix.rstrip("/")):
        url = base + suffix
    else:
        url = base
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


def fetch_provider_models(spec: ProviderFetchSpec, *, opener=None) -> dict:
    """Fetch and normalize a provider's model list. Returns {model_id: spec}.

    `opener` is an optional callable(url, headers, timeout) -> bytes, injected
    for testing so no real network call is made.
    """
    url = _build_fetch_url(spec)
    _validate_fetch_url(url, spec.allow_local)
    headers = _build_fetch_headers(spec)

    if opener is not None:
        raw = opener(url, headers, spec.timeout)
    else:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=spec.timeout) as r:
                raw = r.read()
        except Exception as e:  # urllib raises many subclasses; surface uniformly
            raise FetchError(f"Request failed: {e}") from e

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise FetchError(f"Response was not valid JSON: {e}") from e

    return parse_fetched_models(data, spec)


