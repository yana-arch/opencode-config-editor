# Model catalog, normalized model formats, matching and fallback logic
class ModelCatalog:
    """Enhanced model catalog with filtering and preview"""

    def __init__(self):
        self.raw = None
        self.by_provider = {}  # provider_id -> {model_id: spec}
        self.flat = {}         # model_id -> spec
        self.source = None
        self.last_updated = None
        self._formats_cache = None
        self._model_index = {}  # model_id -> [provider_id, ...]

    def loaded(self) -> bool:
        """Check if catalog is loaded"""
        return self.raw is not None

    def load(self, path: Path):
        """Load catalog from file"""
        data = _load_json_file(path)
        self._ingest(data)
        self.source = str(path)
        self.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def load_text(self, text: str):
        """Load catalog from text"""
        data = json.loads(text)
        self._ingest(data)
        self.source = "(pasted)"
        self.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ingest(self, data: dict):
        """Process catalog data"""
        if not isinstance(data, dict) or not data:
            raise ValueError("Catalog JSON must be a non-empty object.")

        by_provider, flat = {}, {}

        # models.dev-style dump: {providerId: {..., "models": {id: spec}}}
        if all(isinstance(v, dict) and "models" in v for v in data.values()):
            for pid, pdata in data.items():
                models = pdata.get("models", {})
                if isinstance(models, dict):
                    by_provider[pid] = models
                    for mid, spec in models.items():
                        flat.setdefault(mid, spec)

        # Single provider dump: {"id":..., "models": {...}}
        elif "models" in data and isinstance(data["models"], dict):
            pid = data.get("id") or "provider"
            by_provider[pid] = data["models"]
            flat.update(data["models"])

        # Flat map: {modelId: spec}
        elif all(isinstance(v, dict) for v in data.values()):
            flat.update(data)
            # Provide a synthetic provider so the normalized formats still work.
            by_provider["provider"] = data

        else:
            raise ValueError("Unrecognized model catalog format.")

        self.raw, self.by_provider, self.flat = data, by_provider, flat
        self._formats_cache = None
        self._model_index = {}
        for pid, models in by_provider.items():
            for mid in models:
                self._model_index.setdefault(mid, []).append(pid)

    def models_for(self, provider_key: str, npm: str = None) -> dict:
        """Get models for provider"""
        candidates = [provider_key, npm, (npm or "").split("/")[-1]]
        for candidate in candidates:
            if candidate and candidate in self.by_provider:
                return self.by_provider[candidate]
        return self.flat

    def filter_models(self, search: str) -> dict:
        """Filter models by search string"""
        if not search:
            return self.flat

        search = search.lower()
        return {
            mid: spec for mid, spec in self.flat.items()
            if search in mid.lower() or
               (isinstance(spec.get("name"), str) and search in spec["name"].lower())
        }

    def formats(self) -> Dict[str, Dict[str, ModelFormat]]:
        """Lazily build normalized formats: provider -> model_id -> ModelFormat."""
        if getattr(self, "_formats_cache", None) is not None:
            return self._formats_cache
        cache = {}
        for pid, models in self.by_provider.items():
            pmap = {}
            for mid, spec in models.items():
                pmap[mid] = ModelFormat.from_spec(pid, mid, spec)
            cache[pid] = pmap
        self._formats_cache = cache
        return cache

    def all_formats(self) -> List[ModelFormat]:
        """Flatten all formats across providers."""
        return [fmt for pmap in self.formats().values() for fmt in pmap.values()]

    def find_model(self, model_id: str) -> List[ModelFormat]:
        """Match a model id across the whole catalog (may match many providers)."""
        providers = self._model_index.get(model_id)
        if not providers:
            return []
        fmts = self.formats()
        return [fmts[p][model_id] for p in providers if model_id in fmts.get(p, {})]

def try_load_bundled_catalog(catalog) -> bool:
    """Silently load the bundled models.dev catalog into `catalog` if present.

    Never prompts or raises; returns True when the catalog was loaded."""
    if catalog is None or catalog.loaded():
        return catalog is not None and catalog.loaded()
    try:
        bundled = Path(__file__).resolve().parent / "models" / "models.dev.catalog.json"
        if bundled.exists():
            catalog.load(bundled)
            return True
    except (OSError, ValueError):
        pass
    return False

def _merge_model_spec(existing, catalog_spec: dict, overwrite: bool) -> dict:
    """Merge model spec with catalog spec"""
    if not isinstance(existing, dict):
        existing = {}
    existing = dict(existing)
    for k, v in catalog_spec.items():
        if k in ("cost", "limit") and isinstance(v, dict):
            sub = dict(existing.get(k, {})) if isinstance(existing.get(k), dict) else {}
            for sk, sv in v.items():
                if overwrite or sk not in sub:
                    sub[sk] = sv
            existing[k] = sub
        else:
            if overwrite or k not in existing:
                existing[k] = v
    return existing


# ---------------------------------------------------------------------------
# Model Format normalization
# ---------------------------------------------------------------------------

# Flexible key aliases so new providers/schemas only need a map entry.
SPEC_ALIASES = {
    "context": ["limit.context", "context_window", "max_input_tokens", "context_length"],
    "output": ["limit.output", "max_output_tokens", "output_tokens", "max_tokens"],
    "modalities": ["modalities", "input_modalities", "supported_media"],
    "cost_in": ["cost.input", "cost_in", "input_cost"],
    "cost_out": ["cost.output", "cost_out", "output_cost"],
    "cost_cache_read": ["cost.cache_read", "cache_read"],
    "cost_cache_write": ["cost.cache_write", "cache_write"],
}


def _deep_get(spec: dict, dotted: str):
    """Resolve a dotted path ('limit.context') in a dict."""
    cur = spec
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _first_value(spec: dict, aliases) -> Optional[object]:
    for key in aliases:
        v = _deep_get(spec, key)
        if v is not None:
            return v
    return None


def _as_bool(v) -> bool:
    return bool(v) if v is not None else False


@dataclass
class Modalities:
    """Normalized input/output modalities of a model."""
    input_mods: List[str] = field(default_factory=lambda: ["text"])
    output_mods: List[str] = field(default_factory=lambda: ["text"])
    inferred: bool = False

    @property
    def has_image_input(self) -> bool:
        return any(m in ("image", "vision") for m in self.input_mods)

    @property
    def has_pdf_input(self) -> bool:
        return "pdf" in self.input_mods

    @property
    def supports_text_input(self) -> bool:
        return "text" in self.input_mods or not self.input_mods

    @property
    def supports_text_output(self) -> bool:
        return "text" in self.output_mods or not self.output_mods

    def label(self) -> str:
        in_str = "+".join(self.input_mods) if self.input_mods else "?"
        out_str = "+".join(self.output_mods) if self.output_mods else "?"
        mark = "~" if self.inferred else ""
        return f"in:{in_str}{mark} / out:{out_str}"


@dataclass
class ModelFormat:
    """Normalized description of a model across any provider."""
    provider: str
    model_id: str
    name: str
    context: Optional[int] = None
    output: Optional[int] = None
    modalities: Modalities = field(default_factory=Modalities)
    attachment: bool = False
    reasoning: bool = False
    tools: bool = False
    temperature: bool = False
    cost_in: Optional[float] = None
    cost_out: Optional[float] = None
    cost_cache_read: Optional[float] = None
    cost_cache_write: Optional[float] = None

    def context_k(self) -> str:
        return _fmt_tokens(self.context)

    def output_k(self) -> str:
        return _fmt_tokens(self.output)

    def cost_in_label(self) -> str:
        return _fmt_cost(self.cost_in)

    def cost_out_label(self) -> str:
        return _fmt_cost(self.cost_out)

    @classmethod
    def from_spec(cls, provider: str, model_id: str, spec: dict) -> "ModelFormat":
        spec = spec or {}

        context = _first_value(spec, SPEC_ALIASES["context"])
        output = _first_value(spec, SPEC_ALIASES["output"])

        mods = _parse_modalities(spec)

        attachment = _as_bool(spec.get("attachment"))
        reasoning = _as_bool(spec.get("reasoning"))
        tools = _as_bool(spec.get("tool_call") or spec.get("tools"))
        temperature = _as_bool(spec.get("temperature"))

        cost_in = _first_value(spec, SPEC_ALIASES["cost_in"])
        cost_out = _first_value(spec, SPEC_ALIASES["cost_out"])
        cache_read = _first_value(spec, SPEC_ALIASES["cost_cache_read"])
        cache_write = _first_value(spec, SPEC_ALIASES["cost_cache_write"])

        return cls(
            provider=provider,
            model_id=model_id,
            name=str(spec.get("name") or model_id),
            context=_as_int(context),
            output=_as_int(output),
            modalities=mods,
            attachment=attachment,
            reasoning=reasoning,
            tools=tools,
            temperature=temperature,
            cost_in=_as_float(cost_in),
            cost_out=_as_float(cost_out),
            cost_cache_read=_as_float(cache_read),
            cost_cache_write=_as_float(cache_write),
        )


def _parse_modalities(spec: dict) -> Modalities:
    """Parse modalities, inferring from attachment when missing."""
    raw = _first_value(spec, SPEC_ALIASES["modalities"])

    if isinstance(raw, dict):
        in_mods = raw.get("input")
        out_mods = raw.get("output")
        inferred = False
    elif isinstance(raw, list):
        in_mods, out_mods = raw, ["text"]
        inferred = True
    else:
        in_mods, out_mods = None, None
        inferred = True

    in_list = [str(m) for m in in_mods] if in_mods else None
    out_list = [str(m) for m in out_mods] if out_mods else None

    # Fallback: attachment implies image input
    if not in_list and _as_bool(spec.get("attachment")):
        in_list = ["text", "image"]
    elif not in_list:
        in_list = ["text"]

    if not out_list:
        out_list = ["text"]

    return Modalities(input_mods=in_list, output_mods=out_list, inferred=inferred)


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_tokens(v) -> str:
    if v is None:
        return "?"
    if v >= 1000000:
        return f"{v / 1000000:.1f}M"
    if v >= 1000:
        return f"{v / 1000:.0f}k"
    return str(v)


def _fmt_cost(v) -> str:
    if v is None:
        return "?"
    return f"${v:.4f}"


def build_spec_from_format(fmt: ModelFormat) -> dict:
    """Convert a normalized ModelFormat back into a config-shaped spec."""
    spec = {}
    if fmt.name and fmt.name != fmt.model_id:
        spec["name"] = fmt.name

    limit = {}
    if fmt.context is not None:
        limit["context"] = fmt.context
    if fmt.output is not None:
        limit["output"] = fmt.output
    if limit:
        spec["limit"] = limit

    cost = {}
    if fmt.cost_in is not None:
        cost["input"] = fmt.cost_in
    if fmt.cost_out is not None:
        cost["output"] = fmt.cost_out
    if fmt.cost_cache_read is not None:
        cost["cache_read"] = fmt.cost_cache_read
    if fmt.cost_cache_write is not None:
        cost["cache_write"] = fmt.cost_cache_write
    if cost:
        spec["cost"] = cost

    if not fmt.modalities.inferred:
        spec["modalities"] = {
            "input": list(fmt.modalities.input_mods),
            "output": list(fmt.modalities.output_mods),
        }

    if fmt.attachment:
        spec["attachment"] = True
    if fmt.reasoning:
        spec["reasoning"] = True
    if fmt.tools:
        spec["tool_call"] = True
    if fmt.temperature:
        spec["temperature"] = True
    return spec


@dataclass
class ApplyReport:
    """Result of applying catalog specs to a config's providers."""
    matched: List[str] = field(default_factory=list)
    filled: List[str] = field(default_factory=list)
    added: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    ambiguous: List[tuple] = field(default_factory=list)

    def any_changes(self) -> bool:
        return bool(self.matched or self.filled or self.added)


def apply_catalog_to_config(catalog, config_providers: dict, *,
                            overwrite: bool = False,
                            add_new: bool = False,
                            resolve_fn=None) -> ApplyReport:
    """Match each configured model id against the catalog and merge specs."""
    report = ApplyReport()
    formats = catalog.formats()

    for prov_name, prov_cfg in list((config_providers or {}).items()):
        if not isinstance(prov_cfg, dict):
            continue
        models = prov_cfg.get("models")
        if models is None:
            # Only create an empty models map if we'll actually add something.
            has_new = add_new and bool(formats.get(prov_name))
            models = prov_cfg.setdefault("models", {}) if has_new else {}
        if not isinstance(models, dict):
            continue

        for mid, spec in list(models.items()):
            matches = catalog.find_model(mid)
            if not matches:
                report.unknown.append(f"{prov_name}/{mid}")
                continue

            chosen = _resolve_match(matches, prov_name, mid, resolve_fn)
            if chosen is None:
                report.ambiguous.append((prov_name, mid, matches))
                continue

            merged = _merge_model_spec(spec, build_spec_from_format(chosen), overwrite)
            changed = merged != (spec or {})
            if changed:
                models[mid] = merged
                report.filled.append(f"{prov_name}/{mid}")
            else:
                report.unchanged.append(f"{prov_name}/{mid}")

        if add_new:
            known_ids = set(models.keys())
            for fmt in formats.get(prov_name, {}).values():
                if fmt.model_id not in known_ids:
                    models[fmt.model_id] = build_spec_from_format(fmt)
                    report.added.append(f"{prov_name}/{fmt.model_id}")
                    known_ids.add(fmt.model_id)

    return report


def _resolve_match(matches, prov_name, mid=None, resolve_fn=None):
    """Pick a match: prefer same provider name, else ask resolve_fn, else first."""
    if len(matches) == 1:
        return matches[0]
    for m in matches:
        if m.provider == prov_name:
            return m
    if resolve_fn is not None:
        return resolve_fn(prov_name, mid, matches)
    return None


def _format_completeness(fmt: ModelFormat) -> int:
    """Count how much metadata a format carries (used to rank matches)."""
    score = 0
    for v in (fmt.context, fmt.output, fmt.cost_in, fmt.cost_out,
              fmt.cost_cache_read, fmt.cost_cache_write):
        if v is not None:
            score += 1
    if not fmt.modalities.inferred:
        score += 1
    if fmt.name and fmt.name != fmt.model_id:
        score += 1
    return score


def _sort_matches(matches, prov_name):
    """Order matches: same provider name first, then by completeness (desc)."""
    return sorted(
        matches,
        key=lambda m: (m.provider != prov_name, -_format_completeness(m)),
    )


_VERSION_SUFFIX = re.compile(
    r'[-_](\d{4}[-_]\d{2}[-_]\d{2}'
    r'|\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])'
    r'|v\d+(\.\d+)*|latest|preview|stable)$',
    re.IGNORECASE)


def _normalize_model_id(mid: str) -> str:
    """Normalize a model id for fuzzy fallback: lowercase, underscores to
    hyphens, and trailing version/date suffixes stripped."""
    s = str(mid).strip().lower().replace("_", "-")
    prev = None
    while prev != s:
        prev = s
        s = _VERSION_SUFFIX.sub("", s)
    return s.strip("-") or str(mid).strip().lower()


def _find_fallback(mid: str, reference_provider: Optional[str], catalog):
    """Try to find a catalog format for an unmatched model id.

    Order: (a) exact id within the reference provider, (b) normalized-id
    match anywhere, (c) normalized-id match within the reference provider,
    (d) longest shared prefix within the reference provider.
    Returns a ModelFormat or None. Never raises on a missing catalog.
    """
    if catalog is None or not getattr(catalog, "loaded", lambda: False)():
        return None
    formats = catalog.formats()

    # (a) exact id within reference provider
    if reference_provider:
        fmt = formats.get(reference_provider, {}).get(mid)
        if fmt is not None:
            return fmt

    normalized = _normalize_model_id(mid)
    if not normalized:
        return None

    # (b) normalized match within the reference provider first
    if reference_provider:
        pmap = formats.get(reference_provider, {})
        if normalized in pmap:
            return pmap[normalized]

    # (c) normalized match anywhere in the catalog
    for pid, pmap in formats.items():
        if normalized in pmap:
            return pmap[normalized]

    # (d) longest shared prefix within the reference provider
    if reference_provider:
        pmap = formats.get(reference_provider, {})
        best, best_len = None, 0
        for cand_id in pmap:
            cand_norm = _normalize_model_id(cand_id)
            if not cand_norm:
                continue
            common = 0
            for a, b in zip(normalized, cand_norm):
                if a != b:
                    break
                common += 1
            # Require a meaningful prefix and a remaining "family" shape.
            if common > best_len and common >= min(len(normalized), len(cand_norm)) - 4 \
                    and common >= 4:
                best, best_len = pmap[cand_id], common
        return best

    return None


