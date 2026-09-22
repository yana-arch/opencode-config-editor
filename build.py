#!/usr/bin/env python3
"""Ghép các file trong src/ thành các file chạy độc lập.

Cách dùng:
    python3 build.py            # tạo opencode-config-editor.py + openclaude-config-editor.py
    python3 opencode-config-editor.py
    python3 openclaude-config-editor.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
OUT = ROOT / "opencode-config-editor.py"
OUT_OPENCLAUDE = ROOT / "openclaude-config-editor.py"

ORDER = [
    # --- core: generic, agent-agnostic ---
    "core/header.py",
    "core/settings.py",
    "core/config.py",
    "core/parsing.py",
    "core/catalog.py",
    "core/provider_fetch.py",
    "core/connectivity.py",
    "core/mcp_templates.py",
    "core/config_converter.py",
    "core/adapter.py",
    "core/widgets_common.py",
    "core/base_tab.py",
    "core/widgets_models.py",
    "core/widgets_catalog.py",
    "core/widgets_connectivity.py",
    "core/widgets_mcp_hub.py",
    "core/widgets_converter.py",
    # --- adapters/opencode: opencode + tui specifics ---
    "adapters/opencode/tab_providers.py",
    "adapters/opencode/tab_mcp.py",
    "adapters/opencode/tab_plugins.py",
    "adapters/opencode/tab_permission.py",
    "adapters/opencode/tab_runtime.py",
    "adapters/opencode/tab_agents.py",
    "adapters/opencode/tab_commands.py",
    "adapters/opencode/tab_tui.py",
    "adapters/opencode/tab_general.py",
    "adapters/opencode/tab_raw.py",
    "adapters/opencode/adapter.py",
    # --- adapters/openclaude: layered settings.json ---
    "adapters/openclaude/constants.py",
    "adapters/openclaude/config.py",
    "adapters/openclaude/tabs.py",
    "adapters/openclaude/adapter.py",
    # --- app: window + entrypoint ---
    "app/main_window.py",
    "app/main.py",
]

def _concat() -> str:
    parts = []
    for name in ORDER:
        p = SRC / name
        if not p.exists():
            raise SystemExit(f"Thiếu file: {p}")
        parts.append(p.read_text(encoding="utf-8"))
    text = "".join(parts)
    if not text.endswith("\n"):
        text += "\n"
    return text


def build() -> None:
    text = _concat()

    # Default artifact: opencode is the default adapter.
    OUT.write_text(text, encoding="utf-8")
    print(f"Đã tạo {OUT} ({len(text.splitlines())} dòng)")

    # openclaude artifact: same code, but defaults to the openclaude adapter.
    marker = "_BUILD_DEFAULT_ADAPTER = None"
    if marker not in text:
        raise SystemExit(f"Không tìm thấy marker '{marker}' trong app/main.py")
    oc_text = text.replace(marker, '_BUILD_DEFAULT_ADAPTER = "openclaude"', 1)
    OUT_OPENCLAUDE.write_text(oc_text, encoding="utf-8")
    print(f"Đã tạo {OUT_OPENCLAUDE} ({len(oc_text.splitlines())} dòng)")

    if _run_tests():
        print("Tất cả test PASS")
    else:
        raise SystemExit("Test FAILED")


def _run_tests() -> bool:
    """Run the pytest suite if pytest is available."""
    import importlib.util
    import subprocess
    import sys

    if importlib.util.find_spec("pytest") is None:
        print("(pytest không được cài — bỏ qua test. Cài bằng: pip install pytest)")
        return True
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=ROOT,
    )
    return res.returncode == 0


if __name__ == "__main__":
    build()
