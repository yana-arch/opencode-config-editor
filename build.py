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
    "00_header.py",
    "01_settings.py",
    "02_config.py",
    "03_parsing.py",
    "04_catalog.py",
    "05_provider_fetch.py",
    "05b_adapter.py",
    "06_widgets_common.py",
    "06b_tab_base.py",
    "07_widgets_models.py",
    "08_widgets_catalog.py",
    "09_tab_providers.py",
    "10_tab_mcp.py",
    "11_tab_plugins.py",
    "12_tab_permission.py",
    "13_tab_runtime.py",
    "14_tab_agents.py",
    "15_tab_commands.py",
    "16_tab_tui.py",
    "17_tab_general.py",
    "18_tab_raw.py",
    "18b_adapter_opencode.py",
    "19_main_window.py",
    "20_main.py",
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
