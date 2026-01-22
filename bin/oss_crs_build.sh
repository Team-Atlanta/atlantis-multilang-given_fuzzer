#!/bin/bash
# =============================================================================
# Build and push CRS-multilang images to GitHub Container Registry
# =============================================================================
#
# This script is for Team Atlanta to build and push images to ghcr.io.
# OSS-CRS will pull these pre-built images during its prepare phase via
# docker-bake.hcl with USE_PREBUILT=true (default).
#
# Usage:
#   ./oss_crs_build.sh --push             # Build and push to ghcr.io
#   ./oss_crs_build.sh --build            # Build locally only
#   ./oss_crs_build.sh --status           # Check local/remote image status
#
# Environment:
#   REGISTRY    - Registry prefix (default: ghcr.io/team-atlanta)
#   VERSION     - Image version tag (default: latest)
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
REGISTRY="${REGISTRY:-ghcr.io/team-atlanta}"
VERSION="${VERSION:-latest}"

# Images to build/push
IMAGES=(
    "multilang-given_fuzzer-clang"
    "multilang-given_fuzzer-builder"
    "multilang-given_fuzzer-builder-jvm"
    "multilang-given_fuzzer-c-archive"
    "multilang-given_fuzzer-jvm-archive"
    "multilang-given_fuzzer-crs"
    "multilang-given_fuzzer-runner"
)

log() {
    echo "[oss-crs-build] $*"
}

error() {
    echo "[oss-crs-build] ERROR: $*" >&2
    exit 1
}

# Check if image exists in registry
image_exists() {
    local image="$1"
    docker manifest inspect "${REGISTRY}/${image}:${VERSION}" > /dev/null 2>&1
}

# Build images locally (from scratch, not using registry cache)
do_build() {
    log "Building images locally (USE_PREBUILT=false)"
    cd "$PROJECT_DIR"

    USE_PREBUILT=false docker buildx bake \
        --set "*.platform=linux/amd64" \
        prepare multilang-given_fuzzer-runner
}

# Build and push images to registry
do_push() {
    log "Building and pushing images to ${REGISTRY} (version: ${VERSION})"
    cd "$PROJECT_DIR"

    # Build from scratch and push directly
    USE_PREBUILT=false docker buildx bake \
        --set "*.platform=linux/amd64" \
        --push \
        prepare multilang-given_fuzzer-runner

    log "Push complete"
}

# Show status of images
do_status() {
    log "Image status (registry: ${REGISTRY}, version: ${VERSION})"
    echo ""
    printf "%-35s %-10s %-10s\n" "IMAGE" "LOCAL" "REMOTE"
    printf "%-35s %-10s %-10s\n" "-----" "-----" "------"

    for image in "${IMAGES[@]}"; do
        local local_status="no"
        local remote_status="no"

        if docker image inspect "${image}:latest" > /dev/null 2>&1; then
            local_status="yes"
        fi

        if image_exists "$image"; then
            remote_status="yes"
        fi

        printf "%-35s %-10s %-10s\n" "$image" "$local_status" "$remote_status"
    done
}

# Print help
do_help() {
    cat << 'EOF'
Build and push CRS-multilang images to GitHub Container Registry

USAGE:
    ./oss_crs_build.sh [OPTIONS]

OPTIONS:
    --push      Build and push images to ghcr.io (recommended)
    --build     Build images locally only
    --status    Show local/remote image status
    --help      Show this help

ENVIRONMENT:
    REGISTRY    Registry prefix (default: ghcr.io/team-atlanta)
    VERSION     Image version tag (default: latest)

EXAMPLES:
    # Build and push to ghcr.io
    ./oss_crs_build.sh --push

    # Push with version tag
    VERSION=v1.0.0 ./oss_crs_build.sh --push

    # Build locally only (for testing)
    ./oss_crs_build.sh --build

    # Check image status
    ./oss_crs_build.sh --status
EOF
}

# Main
case "${1:-build}" in
    --build|build)
        do_build
        ;;
    --push|push)
        do_push
        ;;
    --status|status)
        do_status
        ;;
    --help|help|-h)
        do_help
        ;;
    *)
        error "Unknown option: $1. Use --help for usage."
        ;;
esac
