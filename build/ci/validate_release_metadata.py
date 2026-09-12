from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION_PATH = REPO_ROOT / "src" / "sli_ui_toolkit" / "_version.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
PKGBUILD_PATH = REPO_ROOT / "build" / "AUR-template" / "PKGBUILD"


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError(f"Unable to find {label}")
    return match.group(1)


def main() -> int:
    version_text = _read_text(VERSION_PATH)
    version_py = _extract(r'^__version__\s*=\s*"([^"]+)"', version_text, "_version.py __version__")

    pyproject_text = _read_text(PYPROJECT_PATH)
    pyproject_version = _extract(r'^version\s*=\s*"([^"]+)"', pyproject_text, "pyproject.toml version")

    pkgbuild_text = _read_text(PKGBUILD_PATH)
    pkgbuild_version = _extract(r"^pkgver=([^\n]+)$", pkgbuild_text, "AUR pkgver")

    versions = {
        "_version.py": version_py,
        "pyproject.toml": pyproject_version,
        "AUR PKGBUILD": pkgbuild_version,
    }
    unique = set(versions.values())
    if len(unique) != 1:
        lines = ", ".join(f"{k}={v}" for k, v in versions.items())
        return _fail(f"Version mismatch: {lines}")

    print(f"Release metadata OK: version={unique.pop()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
