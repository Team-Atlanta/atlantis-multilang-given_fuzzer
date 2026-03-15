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

bash <<'EOF'
set -euo pipefail
set -- help
source "${SCRIPT_PATH}" >/dev/null

prepare_log="$(mktemp)"
rebuild_log="$(mktemp)"
trap 'rm -f "${prepare_log}" "${rebuild_log}"' EXIT

docker() {
  local log_path="$DOCKER_LOG_PATH"
  {
    printf 'USE_PREBUILT=%s\n' "${USE_PREBUILT-}"
    printf 'VERSION=%s\n' "${VERSION-}"
    printf 'REGISTRY=%s\n' "${REGISTRY-}"
    printf 'ARGS=%s\n' "$*"
  } > "${log_path}"
}

VERSION=7.7.7
REGISTRY=ghcr.io/example
PLATFORM=linux/amd64

DOCKER_LOG_PATH="${prepare_log}"
prepare_images

grep -qx 'USE_PREBUILT=' "${prepare_log}"
grep -qx 'VERSION=7.7.7' "${prepare_log}"
grep -qx 'REGISTRY=ghcr.io/example' "${prepare_log}"
grep -qx 'ARGS=buildx bake -f oss-crs/docker-bake.hcl --set \*.platform=linux/amd64 prepare' "${prepare_log}"

DOCKER_LOG_PATH="${rebuild_log}"
prepare_images true

grep -qx 'USE_PREBUILT=false' "${rebuild_log}"
grep -qx 'VERSION=7.7.7' "${rebuild_log}"
grep -qx 'REGISTRY=ghcr.io/example' "${rebuild_log}"
grep -qx 'ARGS=buildx bake -f oss-crs/docker-bake.hcl --set \*.platform=linux/amd64 prepare' "${rebuild_log}"
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
