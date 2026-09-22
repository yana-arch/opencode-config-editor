# Model catalog, normalized model formats, matching and fallback logic
class ModelCatalog:
    """Enhanced model catalog with custom models, pattern rules, filtering, and preview"""

    def __init__(self):
        self.raw = None
        self.by_provider = {}        # provider_id -> {model_id: spec}
        self.flat = {}               # model_id -> spec
        self.custom_models = {}      # model_id -> spec
        self.custom_by_provider = {} # provider_id -> {model_id: spec}
        self.pattern_rules = []      # list of rule dicts
        self.source = None
        self.last_updated = None
        self._formats_cache = None
        self._model_index = {}       # model_id -> [provider_id, ...]
        self.normalized_index = {}   # normalized_id -> [model_id, ...]
        self._load_custom_models()
        self._load_pattern_rules()

    def loaded(self) -> bool:
        """Check if catalog is loaded (including custom models)."""
        return self.raw is not None or bool(self.custom_models)

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

    def _load_custom_models(self):
        """Load user-defined custom models from CUSTOM_MODELS_FILE."""
        try:
            if CUSTOM_MODELS_FILE.exists():
                data = loads_jsonc(CUSTOM_MODELS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._apply_custom_models_dict(data)
        except Exception:
            pass

    def _apply_custom_models_dict(self, data: dict):
        """Merge custom models dict with high priority into catalog."""
        self.custom_models = {}
        self.custom_by_provider = {}

        flat_custom = {}
        by_prov = {}

        if all(isinstance(v, dict) and "models" in v for v in data.values()):
            for pid, pdata in data.items():
                models = pdata.get("models", {})
                if isinstance(models, dict):
                    by_prov[pid] = models
                    for mid, spec in models.items():
                        flat_custom[mid] = spec
        elif "models" in data and isinstance(data["models"], dict):
            pid = data.get("id") or "custom"
            by_prov[pid] = data["models"]
            flat_custom.update(data["models"])
        elif all(isinstance(v, dict) for v in data.values()):
            for mid, spec in data.items():
                pid = spec.get("provider") or "custom"
                by_prov.setdefault(pid, {})[mid] = spec
                flat_custom[mid] = spec

        self.custom_models = flat_custom
        self.custom_by_provider = by_prov

        # Overlay on active index
        for pid, models in by_prov.items():
            if pid not in self.by_provider:
                self.by_provider[pid] = {}
            for mid, spec in models.items():
                self.by_provider[pid][mid] = spec
                self.flat[mid] = spec
                if mid not in self._model_index:
                    self._model_index[mid] = []
                if pid not in self._model_index[mid]:
                    self._model_index[mid].insert(0, pid)
                norm_id = _normalize_model_id(mid)
                if norm_id:
                    self.normalized_index.setdefault(norm_id, []).insert(0, mid)
                if isinstance(spec, dict) and "aliases" in spec:
                    for alias in spec["aliases"]:
                        self._model_index.setdefault(alias, []).insert(0, pid)
                        norm_alias = _normalize_model_id(alias)
                        if norm_alias:
                            self.normalized_index.setdefault(norm_alias, []).insert(0, mid)

        self._formats_cache = None

    def _load_pattern_rules(self):
        """Load pattern rules from PATTERN_RULES_FILE."""
        try:
            if PATTERN_RULES_FILE.exists():
                data = loads_jsonc(PATTERN_RULES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.pattern_rules = [r for r in data if isinstance(r, dict)]
        except Exception:
            self.pattern_rules = []

    def save_custom_model(self, model_id: str, spec: dict, provider: str = "custom") -> bool:
        """Save/update a custom model spec in CUSTOM_MODELS_FILE."""
        model_id = str(model_id).strip()
        if not model_id:
            return False
        current = self.get_all_custom_models()
        spec_copy = dict(spec)
        spec_copy["provider"] = provider
        current[model_id] = spec_copy

        try:
            CUSTOM_MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
            CUSTOM_MODELS_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
            if self.raw:
                self._ingest(self.raw)
            else:
                self._load_custom_models()
            return True
        except OSError:
            return False

    def delete_custom_model(self, model_id: str) -> bool:
        """Delete a custom model from CUSTOM_MODELS_FILE."""
        current = self.get_all_custom_models()
        if model_id in current:
            current.pop(model_id, None)
            try:
                CUSTOM_MODELS_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
                if self.raw:
                    self._ingest(self.raw)
                else:
                    self.custom_models.pop(model_id, None)
                    self._formats_cache = None
                return True
            except OSError:
                return False
        return False

    def get_all_custom_models(self) -> Dict[str, dict]:
        """Get dict of all saved custom models."""
        try:
            if CUSTOM_MODELS_FILE.exists():
                data = loads_jsonc(CUSTOM_MODELS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return dict(self.custom_models)

    def save_pattern_rules(self, rules: List[dict]) -> bool:
        """Save list of pattern rules to PATTERN_RULES_FILE."""
        self.pattern_rules = [r for r in rules if isinstance(r, dict) and r.get("pattern")]
        try:
            PATTERN_RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
            PATTERN_RULES_FILE.write_text(json.dumps(self.pattern_rules, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except OSError:
            return False

    def get_all_pattern_rules(self) -> List[dict]:
        """Get list of all pattern rules."""
        if not self.pattern_rules:
            self._load_pattern_rules()
        return list(self.pattern_rules)

    def fetch_online(self, url: Optional[str] = None) -> Tuple[bool, str, int]:
        """Download latest catalog from online source, update cache, and reload."""
        catalog_url = (url or SettingsManager().get_catalog_url() or DEFAULT_CATALOG_URL).strip()
        try:
            req = urllib.request.Request(
                catalog_url,
                headers={"User-Agent": f"opencode-config-editor/{APP_VERSION}"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
            data = loads_jsonc(raw)
            if not isinstance(data, dict) or not data:
                return False, "Downloaded catalog is empty or invalid JSON.", 0

            CATALOG_CACHE.parent.mkdir(parents=True, exist_ok=True)
            CATALOG_CACHE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self.load(CATALOG_CACHE)
            return True, f"Catalog updated successfully from {catalog_url}!", len(self.flat)
        except Exception as e:
            return False, f"Failed to fetch catalog: {e}", 0

    def _ingest(self, data: dict):
        """Process catalog data and overlay custom models."""
        if not isinstance(data, dict) or not data:
            raise ValueError("Catalog JSON must be a non-empty object.")

        by_provider, flat = {}, {}

        # models.dev-style dump: {providerId: {..., "models": {id: spec}}}
        if all(isinstance(v, dict) and "models" in v for v in data.values()):
            for pid, pdata in data.items():
                models = pdata.get("models", {})
                if isinstance(models, dict):
                    by_provider[pid] = dict(models)
                    for mid, spec in models.items():
                        flat.setdefault(mid, spec)

        # Single provider dump: {"id":..., "models": {...}}
        elif "models" in data and isinstance(data["models"], dict):
            pid = data.get("id") or "provider"
            by_provider[pid] = dict(data["models"])
            flat.update(data["models"])

        # Flat map: {modelId: spec}
        elif all(isinstance(v, dict) for v in data.values()):
            flat.update(data)
            # Provide a synthetic provider so the normalized formats still work.
            by_provider["provider"] = dict(data)

        else:
            raise ValueError("Unrecognized model catalog format.")

        self.raw, self.by_provider, self.flat = data, by_provider, flat
        self._formats_cache = None
        self._model_index = {}
        self.normalized_index = {}
        for pid, models in by_provider.items():
            for mid, spec in models.items():
                self._model_index.setdefault(mid, []).append(pid)
                # Phase 2: Aliases
                if isinstance(spec, dict) and "aliases" in spec:
                    for alias in spec["aliases"]:
                        self._model_index.setdefault(alias, []).append(pid)

        for mid in list(self.flat.keys()):
            norm_id = _normalize_model_id(mid)
            if norm_id:
                self.normalized_index.setdefault(norm_id, []).append(mid)

            # Phase 2: Aliases in normalized index
            spec = self.flat[mid]
            if isinstance(spec, dict) and "aliases" in spec:
                for alias in spec["aliases"]:
                    norm_alias = _normalize_model_id(alias)
                    if norm_alias:
                        self.normalized_index.setdefault(norm_alias, []).append(mid)

        # Overlay custom models & load pattern rules
        self._load_custom_models()
        self._load_pattern_rules()

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

    def formats(self) -> Dict[str, Dict[str, "ModelFormat"]]:
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

    def all_formats(self) -> List["ModelFormat"]:
        """Flatten all formats across providers."""
        return [fmt for pmap in self.formats().values() for fmt in pmap.values()]

    def find_model(self, model_id: str) -> List["ModelFormat"]:
        """Match a model id across the catalog, custom models, and pattern rules."""
        matches = set()

        # 1. Exact match
        if model_id in self._model_index:
            matches.add(model_id)

        # 2. Full normalized match (most precise).
        full = _normalize_model_id(model_id)
        if full in self.normalized_index:
            for original_id in self.normalized_index[full]:
                matches.add(original_id)

        # 3. Fallback: version-stripped variants
        if not matches:
            for key in _normalized_match_keys(model_id):
                if key == full:
                    continue
                if key in self.normalized_index:
                    for original_id in self.normalized_index[key]:
                        matches.add(original_id)

        # 4. Pattern rules match
        if not matches and self.pattern_rules:
            for rule in self.pattern_rules:
                pat = str(rule.get("pattern", "")).strip()
                if not pat:
                    continue
                matched = False
                if pat.startswith("regex:"):
                    try:
                        matched = bool(re.search(pat[6:], model_id, re.IGNORECASE))
                    except re.error:
                        matched = False
                else:
                    matched = fnmatch.fnmatch(model_id.lower(), pat.lower())

                if matched:
                    ref_prov = rule.get("reference_provider")
                    ref_mod = rule.get("reference_model")
                    ref_fmt = None
                    if ref_mod:
                        mod_matches = self.find_model(ref_mod)
                        if mod_matches:
                            ref_fmt = mod_matches[0]
                    if ref_fmt is None and ref_prov:
                        ref_fmt = _find_fallback(model_id, ref_prov, self)
                    if ref_fmt is not None:
                        derived_fmt = ModelFormat(
                            provider=ref_prov or ref_fmt.provider,
                            model_id=model_id,
                            name=humanize_model_id(model_id),
                            context=ref_fmt.context,
                            output=ref_fmt.output,
                            cost_in=ref_fmt.cost_in,
                            cost_out=ref_fmt.cost_out,
                            cost_cache_read=ref_fmt.cost_cache_read,
                            cost_cache_write=ref_fmt.cost_cache_write,
                            modalities=ref_fmt.modalities,
                            attachment=ref_fmt.attachment,
                            reasoning=ref_fmt.reasoning,
                            tools=ref_fmt.tools,
                            temperature=ref_fmt.temperature,
                        )
                        return [derived_fmt]

        if not matches:
            return []

        # Collect all unique ModelFormat objects
        found_formats = {}
        fmts = self.formats()
        for mid in matches:
            providers = self._model_index.get(mid, [])
            for p in providers:
                if mid in fmts.get(p, {}):
                    fmt = fmts[p][mid]
                    found_formats[(fmt.provider, fmt.model_id)] = fmt

        return list(found_formats.values())

def try_load_bundled_catalog(catalog) -> bool:
    """Silently load the bundled models.dev catalog into `catalog` if present.

    Never prompts or raises; returns True when the catalog was loaded."""
    if catalog is None or catalog.loaded():
        return catalog is not None and catalog.loaded()
    try:
        # 1. User config dir (~/.config/opencode-config-editor/catalog.json)
        if CATALOG_CACHE.exists():
            catalog.load(CATALOG_CACHE)
            return True
        # 2. Local bundled relative to main script
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
            name=str(spec.get("name") or humanize_model_id(model_id)),
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


# Tokens rendered as uppercase acronyms in derived display names.
_NAME_ACRONYMS = {
    "gpt": "GPT", "api": "API", "url": "URL", "http": "HTTP", "https": "HTTPS",
    "ai": "AI", "ml": "ML", "llm": "LLM", "ui": "UI", "cli": "CLI", "json": "JSON",
    "xml": "XML", "html": "HTML", "css": "CSS", "js": "JS", "ts": "TS",
    "db": "DB", "id": "ID", "qa": "QA", "v": "v", "glm": "GLM", "dbrx": "DBRX",
    "qwen": "Qwen", "deepseek": "DeepSeek", "llama": "Llama", "mistral": "Mistral",
    "claude": "Claude", "gemini": "Gemini", "phi": "Phi", "gemma": "Gemma",
    "yi": "Yi", "r1": "R1", "v3": "V3", "v2": "V2", "v1": "V1",
}


def humanize_model_id(model_id: str) -> str:
    """Derive a readable label from a model id, e.g.
    ``glm-5.3-flash`` -> ``GLM 5.3 Flash``,
    ``claude-opus-4.8-thinking`` -> ``Claude Opus 4.8 Thinking``.

    Used when creating or formatting a model spec so that the model's display name
    is derived directly from its own model ID rather than inheriting an outdated
    or mismatched name from a fallback/matched catalog entry.
    """
    if not model_id:
        return model_id
    s = _NAMESPACE_RE.sub("", str(model_id).strip())
    parts = re.split(r"[-_/:]", s)
    out = []
    for p in parts:
        if not p:
            continue
        low = p.lower()
        if low in _NAME_ACRONYMS:
            out.append(_NAME_ACRONYMS[low])
        elif re.fullmatch(r"\d+(\.\d+)*", p) or re.fullmatch(r"\d{6,8}", p):
            out.append(p)
        elif re.fullmatch(r"\d+[xX]\d+[bBmMkK]|\d+[bBmMkK]", p):
            out.append(p.upper())
        else:
            out.append(p[:1].upper() + p[1:].lower())
    return " ".join(out)


def build_spec_from_format(fmt: ModelFormat, model_id: Optional[str] = None) -> dict:
    """Convert a normalized ModelFormat back into a config-shaped spec.

    When `model_id` is supplied, the spec name is set according to `model_id`
    (e.g. humanized name derived from `model_id`) to ensure models like
    `glm-5.3-flash` get `GLM 5.3 Flash` instead of the name of the matched entry.
    """
    spec = {}
    if model_id is not None:
        if fmt.model_id == model_id and fmt.name and fmt.name != fmt.model_id:
            spec["name"] = fmt.name
        else:
            spec["name"] = humanize_model_id(model_id)
    elif fmt.name and fmt.name != fmt.model_id:
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
    r'[-_](\d{4}[-_]\d{2}[-_]\d{2}'                   # YYYY-MM-DD
    r'|\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])'     # YYYYMMDD
    r'|(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])'          # MMDD (common for preview models)
    r'|v\d+(\.\d+)*|latest|preview|stable)$',
    re.IGNORECASE)

# Prefixes and suffixes to strip during normalization. Order matters for suffixes.
_NORM_PREFIXES = ("google/", "google:", "anthropic.", "openai:", "zh-", "en-")

# A leading "namespace" token followed by '/' or ':', e.g. "df/", "anthropic/",
# "openai:". Stripped so that "df/claude-opus-4.8" collapses to "claude-opus-4.8"
# and matches catalog entries stored under any other (or no) namespace.
_NAMESPACE_RE = re.compile(r'^[^/:]+[/:]')

# A trailing dotted version (e.g. "4.8", "2.1", "3.5.2") reduced to its major,
# so "claude-opus-4.8" -> "claude-opus-4" and matches "claude-opus-4".
_DOTTED_VERSION_RE = re.compile(r'(-\d+)(?:\.\d+)+$')
_NORM_SUFFIXES = (
    "-thinking",
    "-online",
    "-tool-use", "-tool_use", "-tools",
    "-preview", "-rc", "-beta", "-alpha", "-canary",
    "-latest", "-stable",
    "-chat", "-instruct", "-completions", "-completion",
    "-code", "-text",
    "-with-vision", "-vision", "-with",
)


def _normalize_model_id(mid: str) -> str:
    """Normalize a model id for fuzzy matching: lowercase, hyphens,
    a leading namespace token, and trailing version/date/general suffixes stripped."""
    s = str(mid).strip().lower().replace("_", "-")

    # Strip leading namespace/provider tokens ("df/", "anthropic:", ...).
    # Looped so "df/anthropic/claude" -> "anthropic/claude" -> "claude".
    while _NAMESPACE_RE.match(s):
        s = _NAMESPACE_RE.sub("", s, count=1)

    # Strip curated prefixes
    for prefix in _NORM_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break

    # Iteratively strip version/date and general suffixes
    changed = True
    while changed:
        changed = False
        # Try version/date regex first
        new_s = _VERSION_SUFFIX.sub("", s)
        if new_s != s:
            s = new_s
            changed = True
            continue
        # Try general suffixes
        for suffix in _NORM_SUFFIXES:
            if s.endswith(suffix):
                s = s[:-len(suffix)]
                changed = True
                break

    return s.strip("-") or str(mid).strip().lower()


def _normalized_match_keys(model_id: str) -> List[str]:
    """Candidate normalized keys for matching, most specific first.

    Starts from the fully-normalized id, then progressively drops trailing
    version/date segments so that e.g. ``df/claude-opus-4.8`` can also match a
    catalog entry stored as ``anthropic/claude-opus-4`` or ``claude-opus``.
    """
    base = _normalize_model_id(model_id)
    if not base:
        return []
    keys = [base]
    cur = base
    while True:
        new = None
        # 1) Reduce a trailing "N.M" dotted version to its major "N".
        red = _DOTTED_VERSION_RE.sub(r"\1", cur)
        if red != cur and red:
            new = red
        # 2) Drop a trailing version/date token (vN, dates, latest, ...).
        if new is None:
            red = _VERSION_SUFFIX.sub("", cur)
            if red != cur and red:
                new = red
        # 3) Drop a bare trailing "-N" or "-N.M" version.
        if new is None:
            m = re.search(r'-\d+(?:\.\d+)*$', cur)
            if m:
                red = cur[:m.start()]
                if red:
                    new = red
        if new is None or new in keys:
            break
        keys.append(new)
        cur = new
    return keys




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

    # (b) full normalized match within the reference provider first.
    if reference_provider:
        for cand_id, fmt in formats.get(reference_provider, {}).items():
            if _normalize_model_id(cand_id) == normalized:
                return fmt

    # (c) full normalized match anywhere in the catalog.
    for pid, pmap in formats.items():
        for cand_id, fmt in pmap.items():
            if _normalize_model_id(cand_id) == normalized:
                return fmt

    # (b') version-stripped variants within the reference provider.
    for key in _normalized_match_keys(mid):
        if key == normalized:
            continue
        if reference_provider:
            for cand_id, fmt in formats.get(reference_provider, {}).items():
                if _normalize_model_id(cand_id) == key:
                    return fmt

    # (c') version-stripped variants anywhere in the catalog.
    for key in _normalized_match_keys(mid):
        if key == normalized:
            continue
        for pid, pmap in formats.items():
            for cand_id, fmt in pmap.items():
                if _normalize_model_id(cand_id) == key:
                    return fmt

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


