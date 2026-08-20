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
    "01_core.py",
    "02_widgets.py",
    "03_tabs.py",
    "04_main_window.py",
    "05_main.py",
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
