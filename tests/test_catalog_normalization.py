import pytest
import json
from conftest import app

@pytest.fixture
def catalog():
    c = app.ModelCatalog()
    c.load_text(json.dumps({
        "anthropic": {
            "models": {
                "claude-3-opus-20240229": {"name": "Claude 3 Opus"},
                "claude-3-sonnet-20240229": {"name": "Claude 3 Sonnet"}
            }
        },
        "google": {
            "models": {
                "gemini-1.5-pro-preview-0409": {"name": "Gemini 1.5 Pro"}
            }
        },
        "openai": {
            "models": {
                "gpt-4-turbo": {"name": "GPT-4 Turbo"},
                "gpt-4-turbo-2024-04-09": {"name": "GPT-4 Turbo Vision"}
            }
        },
        "custom": {
            "models": {
                "zh-special-model-chat": {"name": "Special Chinese Model", "aliases": ["chinese-special"]}
            }
        }
    }))
    return c


@pytest.mark.parametrize("input_id, expected_normalized_id", [
    ("claude-3-opus-20240229", "claude-3-opus"),
    ("anthropic.claude-3-opus-20240229", "claude-3-opus"),
    ("claude-3-sonnet-20240229-tool-use", "claude-3-sonnet"),
    ("gemini-1.5-pro-preview-0409", "gemini-1.5-pro"),
    ("google/gemini-1.5-pro", "gemini-1.5-pro"),
    ("gpt-4-turbo-2024-04-09", "gpt-4-turbo"),
    ("gpt-4-turbo-vision", "gpt-4-turbo"),
    ("zh-special-model-chat", "special-model"),
    ("claude-2.1", "claude-2.1"),
    ("llama-3-70b-instruct", "llama-3-70b"),
    # Namespace/provider prefixes collapsed to the bare model id
    ("df/claude-opus-4.8", "claude-opus-4.8"),
    ("anthropic/claude-opus-4", "claude-opus-4"),
    ("deepseek/deepseek-v4-flash", "deepseek-v4-flash"),
    ("openai:gpt-4.1", "gpt-4.1"),
    ("df/anthropic/claude-3-opus", "claude-3-opus"),
])
def test_normalize_model_id(input_id, expected_normalized_id):
    assert app._normalize_model_id(input_id) == expected_normalized_id

def test_normalized_index_creation(catalog):
    assert "claude-3-opus" in catalog.normalized_index
    assert catalog.normalized_index["claude-3-opus"] == ["claude-3-opus-20240229"]

    assert "claude-3-sonnet" in catalog.normalized_index
    assert catalog.normalized_index["claude-3-sonnet"] == ["claude-3-sonnet-20240229"]

    assert "gpt-4-turbo" in catalog.normalized_index
    assert set(catalog.normalized_index["gpt-4-turbo"]) == {"gpt-4-turbo", "gpt-4-turbo-2024-04-09"}

    assert "special-model" in catalog.normalized_index
    assert catalog.normalized_index["special-model"] == ["zh-special-model-chat"]

def test_find_model_with_normalization(catalog):
    # Find via a datestamped version
    matches = catalog.find_model("claude-3-opus-20240229-thinking")
    assert len(matches) == 1
    assert matches[0].model_id == "claude-3-opus-20240229"

    # Find via a prefixed, suffixed name
    matches = catalog.find_model("google:gemini-1.5-pro-preview")
    assert len(matches) == 1
    assert matches[0].model_id == "gemini-1.5-pro-preview-0409"

    # Find a model that should have multiple matches
    matches = catalog.find_model("gpt-4-turbo-with-vision")
    assert len(matches) == 2
    model_ids = {m.model_id for m in matches}
    assert model_ids == {"gpt-4-turbo", "gpt-4-turbo-2024-04-09"}

    # Find with a chinese prefix
    matches = catalog.find_model("zh-special-model")
    assert len(matches) == 1
    assert matches[0].model_id == "zh-special-model-chat"

    # Find via an alias
    matches = catalog.find_model("chinese-special")
    assert len(matches) == 1
    assert matches[0].model_id == "zh-special-model-chat"

    # Find via a messy version of an alias
    matches = catalog.find_model("CHINESE-SPECIAL-THINKING")
    assert len(matches) == 1
    assert matches[0].model_id == "zh-special-model-chat"

    # No match
    matches = catalog.find_model("no-such-model-exists")
    assert len(matches) == 0


@pytest.fixture
def namespaced_catalog():
    c = app.ModelCatalog()
    c.load_text(json.dumps({
        "anthropic": {
            "models": {
                "anthropic/claude-opus-4": {"name": "Claude Opus 4"},
                "anthropic/claude-sonnet-4": {"name": "Claude Sonnet 4"},
            }
        },
        "deepseek": {
            "models": {
                "deepseek/deepseek-v4-flash": {"name": "DeepSeek V4 Flash"},
            }
        },
    }))
    return c


def test_find_model_across_namespaces(namespaced_catalog):
    # A config id carrying an arbitrary namespace + dotted version should still
    # resolve to the catalog entry stored under a different namespace.
    matches = namespaced_catalog.find_model("df/claude-opus-4.8")
    assert len(matches) == 1
    assert matches[0].model_id == "anthropic/claude-opus-4"

    # Namespace-less query resolves to the namespaced catalog entry.
    matches = namespaced_catalog.find_model("claude-opus-4")
    assert len(matches) == 1
    assert matches[0].model_id == "anthropic/claude-opus-4"

    # Dotted version on a fully namespaced query.
    matches = namespaced_catalog.find_model("df/deepseek-v4-flash-1.0")
    assert len(matches) == 1
    assert matches[0].model_id == "deepseek/deepseek-v4-flash"


@pytest.mark.parametrize("input_id, expected_label", [
    ("glm-5.3-flash", "GLM 5.3 Flash"),
    ("claude-opus-4.8-thinking", "Claude Opus 4.8 Thinking"),
    ("claude-opus-4.8", "Claude Opus 4.8"),
    ("gpt-4.1", "GPT 4.1"),
    ("deepseek/deepseek-v4-flash", "DeepSeek V4 Flash"),
    ("df/claude-opus-4.8-thinking", "Claude Opus 4.8 Thinking"),
    ("llama-3-70b-instruct", "Llama 3 70B Instruct"),
    ("my-model-20240229", "My Model 20240229"),
    ("", ""),
])
def test_humanize_model_id(input_id, expected_label):
    assert app.humanize_model_id(input_id) == expected_label


def test_build_spec_from_format_derives_name_for_target_model_id():
    # If a model matches a different catalog model format, spec name must be derived from target model id
    fmt = app.ModelFormat.from_spec("zhipu", "glm-4-flash", {"name": "GLM 4 Flash", "attachment": True})
    spec = app.build_spec_from_format(fmt, "glm-5.3-flash")
    assert spec["name"] == "GLM 5.3 Flash"
    assert spec["attachment"] is True


def test_from_spec_uses_humanized_name_when_missing():
    fmt = app.ModelFormat.from_spec("prov", "claude-opus-4.8-thinking", {})
    assert fmt.name == "Claude Opus 4.8 Thinking"

    # An explicit name always wins.
    fmt = app.ModelFormat.from_spec("prov", "claude-opus-4.8-thinking",
                                    {"name": "My Custom Name"})
    assert fmt.name == "My Custom Name"
