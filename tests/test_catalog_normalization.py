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
