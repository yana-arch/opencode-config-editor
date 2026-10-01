# Connectivity and Health Check module for Provider APIs
# ---------------------------------------------------------------------------


@dataclass
class ConnectionTestResult:
    """Result of testing connectivity to a model provider API."""
    success: bool
    latency_ms: float = 0.0
    status_code: int = 0
    message: str = ""
    model_count: Optional[int] = None
    models: List[str] = field(default_factory=list)
    raw_error: str = ""

    def summary(self) -> str:
        if self.success:
            count_str = f" ({self.model_count} models found)" if self.model_count is not None else ""
            return f"✓ Connected in {self.latency_ms:.0f}ms{count_str}"
        return f"✗ Failed: {self.message}"



# opencode config variables: '{env:VAR}' and '{file:path}'
# https://opencode.ai/docs/config/#variables
_PLACEHOLDER_RE = re.compile(r"\{(env|file):([^{}]*)\}")


def _resolve_one_placeholder(kind: str, arg: str, config_dir: Optional[Path]) -> str:
    if kind == "env":
        return os.environ.get(arg, "")
    path = Path(arg.strip()).expanduser()
    if not path.is_absolute():
        path = Path(config_dir) / path
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def resolve_config_placeholders(value: str, config_dir: Optional[Path] = None) -> str:
    """Expand opencode's {env:VAR} / {file:path} config variables in a string.

    An unset variable or an unreadable file expands to an empty string, as
    opencode does. Relative {file:} paths resolve against the config file's
    directory (config_dir); '~' and absolute paths are used as-is.
    """
    if not isinstance(value, str) or "{" not in value:
        return value
    return _PLACEHOLDER_RE.sub(
        lambda m: _resolve_one_placeholder(m.group(1), m.group(2), config_dir), value
    )


def _redact_url_secrets(url: str) -> str:
    """Mask credentials carried in the query string (e.g. Gemini's ?key=)."""
    return re.sub(r"([?&](?:key|api_key|apikey|token|access_token)=)[^&]*",
                  r"\1***", url or "")



def _sanitize_secret(text: str, secret: str) -> str:
    """Strip the configured key out of text that is shown in the UI.

    urllib echoes the request line and the header block back in its errors (a
    base URL with a space, a key with a newline), so a bare str(e) can leak
    the credential into the Diagnostic Log. The key is masked both literally
    and in the repr-escaped form urllib prints for invalid header values.
    """
    out = _redact_url_secrets(text or "")
    if not secret:
        return out
    out = out.replace(secret, "***")
    for line in secret.splitlines():
        stripped = line.strip()
        if len(stripped) >= 4:
            out = out.replace(stripped, "***")
    return out


def test_provider_connection(
    base_url: str,
    api_key: str = "",
    adapter: str = "openai",
    timeout: int = 10,
    allow_local: bool = True,
    opener=None,
) -> ConnectionTestResult:
    """Send a lightweight test request to verify API endpoint connectivity and authentication.

    Measures latency and extracts model list when possible.
    """
    if not base_url or not base_url.strip():
        return ConnectionTestResult(
            success=False,
            message="Base URL is empty.",
            raw_error="Empty URL",
        )

    clean_url = base_url.strip()
    spec = ProviderFetchSpec(
        base_url=clean_url,
        adapter=adapter,
        api_key=api_key.strip() if api_key else "",
        allow_local=allow_local,
        timeout=timeout,
    )

    t0 = time.perf_counter()
    url = ""
    try:
        url = _build_fetch_url(spec)
        _validate_fetch_url(url, spec.allow_local)
        headers = _build_fetch_headers(spec)

        if opener is not None:
            raw = opener(url, headers, spec.timeout)
            status_code = 200
        else:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=spec.timeout) as r:
                raw = r.read()
                status_code = getattr(r, "status", 200)

        latency_ms = (time.perf_counter() - t0) * 1000.0

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        data = json.loads(raw)
        models_dict = parse_fetched_models(data, spec)
        model_keys = sorted(models_dict.keys())

        return ConnectionTestResult(
            success=True,
            latency_ms=latency_ms,
            status_code=status_code,
            message="Connection successful",
            model_count=len(model_keys),
            models=model_keys[:50],
        )

    except FetchError as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        text = _sanitize_secret(str(e), spec.api_key)
        return ConnectionTestResult(
            success=False,
            latency_ms=latency_ms,
            message=text,
            raw_error=text,
        )
    except urllib.error.HTTPError as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        msg = f"HTTP {e.code}: {e.reason}"
        if e.code == 401:
            msg = "HTTP 401: Unauthorized (Invalid or missing API key)"
        elif e.code == 403:
            msg = "HTTP 403: Forbidden (Access denied or insufficient permissions)"
        elif e.code == 404:
            msg = f"HTTP 404: Endpoint not found ({_redact_url_secrets(url)})"
        elif e.code == 429:
            msg = "HTTP 429: Rate limited or quota exhausted"
        return ConnectionTestResult(
            success=False,
            latency_ms=latency_ms,
            status_code=e.code,
            message=_sanitize_secret(msg, spec.api_key),
            raw_error=_sanitize_secret(str(e), spec.api_key),
        )
    except urllib.error.URLError as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        reason = str(e.reason)
        if "Connection refused" in reason:
            reason = "Connection refused (Check if local server like Ollama/vLLM is running)"
        return ConnectionTestResult(
            success=False,
            latency_ms=latency_ms,
            message=_sanitize_secret(f"Network error: {reason}", spec.api_key),
            raw_error=_sanitize_secret(str(e), spec.api_key),
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ConnectionTestResult(
            success=False,
            latency_ms=latency_ms,
            message=_sanitize_secret(f"Error: {e}", spec.api_key),
            raw_error=_sanitize_secret(str(e), spec.api_key),
        )
