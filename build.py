#!/usr/bin/env python3
"""Ghép các file module trong src/ thành một file duy nhất để chạy.

Cách dùng:
    python3 build.py            # tạo opencode-config-editor.py
    python3 opencode-config-editor.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
OUT = ROOT / "opencode-config-editor.py"

ORDER = [
    # --- core: generic, agent-agnostic ---
    "core/header.py",
    "core/settings.py",
    "core/config.py",
    "core/parsing.py",
    "core/catalog.py",
    "core/provider_fetch.py",
    "core/adapter.py",
    "core/widgets_common.py",
    "core/base_tab.py",
    "core/widgets_models.py",
    "core/widgets_catalog.py",
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
    # --- app: window + entrypoint ---
    "app/main_window.py",
    "app/main.py",
]

def build() -> None:
    parts = []
    for name in ORDER:
        p = SRC / name
        if not p.exists():
            raise SystemExit(f"Thiếu file module: {p}")
        parts.append(p.read_text(encoding="utf-8"))
    text = "".join(parts)
    if not text.endswith("\n"):
        text += "\n"
    OUT.write_text(text, encoding="utf-8")
    print(f"Đã tạo {OUT} ({len(text.splitlines())} dòng)")

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
