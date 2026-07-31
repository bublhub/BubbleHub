#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:?usage: scripts/ci/stamp-release-version.sh <repo-root> <version>}"
VERSION="${2:?usage: scripts/ci/stamp-release-version.sh <repo-root> <version>}"

python3 - "$ROOT" "$VERSION" <<'PY'
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
version = sys.argv[2]

replacements = {
    root / "pyproject.toml": (r'(?m)^version = "[^"]+"', f'version = "{version}"'),
    root / "bubblehub" / "__init__.py": (r'__version__ = "[^"]+"', f'__version__ = "{version}"'),
    root / "app" / "Cargo.toml": (r'(?m)^version = "[^"]+"', f'version = "{version}"'),
    root / "app" / "tauri.conf.json": (r'(?m)^  "version": "[^"]+"', f'  "version": "{version}"'),
}

for path, (pattern, replacement) in replacements.items():
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"Could not stamp version in {path}")
    path.write_text(updated, encoding="utf-8")

package_json = root / "package.json"
data = json.loads(package_json.read_text(encoding="utf-8"))
data["version"] = version
package_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

print(f"Stamped release version {version} into {root}")
PY
