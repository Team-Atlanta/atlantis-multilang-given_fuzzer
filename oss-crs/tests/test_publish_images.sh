#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_PATH="${ROOT_DIR}/oss-crs/publish-images.sh"
CRS_YAML="${ROOT_DIR}/oss-crs/crs.yaml"

expected_version="$(awk '/^version:/ { print $2; exit }' "${CRS_YAML}")"

export ROOT_DIR SCRIPT_PATH CRS_YAML expected_version

bash <<'EOF'
set -euo pipefail
set -- help
source "${SCRIPT_PATH}" >/dev/null

if ! declare -F resolve_version >/dev/null; then
  echo "resolve_version function not found" >&2
  exit 1
fi

if [[ "$(resolve_version)" != "${expected_version}" ]]; then
  echo "default version did not match crs.yaml" >&2
  exit 1
fi

VERSION=9.9.9
if [[ "$(resolve_version)" != "9.9.9" ]]; then
  echo "VERSION override not respected" >&2
  exit 1
fi
EOF

python3 - <<'EOF'
from pathlib import Path
root = Path(__import__("os").environ["ROOT_DIR"])
files = [
    root / "oss-crs" / "docker-bake.hcl",
    root / "docker-bake.hcl",
]
for path in files:
    text = path.read_text()
    if 'variable "USE_PREBUILT" {\n  default = true\n}' not in text:
        raise SystemExit(f"USE_PREBUILT default is not true in {path}")
EOF
