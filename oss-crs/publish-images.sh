#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

REGISTRY="${REGISTRY:-ghcr.io/team-atlanta}"
VERSION="${VERSION:-1.0.0}"
PLATFORM="${PLATFORM:-linux/amd64}"

IMAGES=(
    "multilang-given_fuzzer-clang"
    "multilang-given_fuzzer-builder"
    "multilang-given_fuzzer-builder-jvm"
    "multilang-given_fuzzer-c-archive"
    "multilang-given_fuzzer-jvm-archive"
    "multilang-given_fuzzer-crs"
)

log() {
    echo "[publish-images] $*"
}

usage() {
    cat <<EOF
Build and publish given_fuzzer prepare images.

USAGE:
    ./oss-crs/publish-images.sh <command>

COMMANDS:
    prepare         Build the canonical prepare images locally from scratch
    push            Push the canonical prepare images to the registry
    prepare-push    Run prepare, then push
    status          Show whether expected local image tags exist
    help            Show this help

ENVIRONMENT:
    REGISTRY        Registry prefix (default: ghcr.io/team-atlanta)
    VERSION         Version tag to push alongside latest (default: 1.0.0)
    PLATFORM        Build platform for docker buildx bake (default: linux/amd64)

IMAGES:
$(printf '    - %s\n' "${IMAGES[@]}")
EOF
}

ensure_local_tag() {
    local image="$1"
    local tag="$2"
    docker image inspect "${REGISTRY}/${image}:${tag}" >/dev/null 2>&1
}

prepare_images() {
    log "Building canonical prepare images locally"
    (
        cd "${PROJECT_DIR}"
        USE_PREBUILT=false VERSION="${VERSION}" REGISTRY="${REGISTRY}" \
            docker buildx bake \
            -f oss-crs/docker-bake.hcl \
            --set "*.platform=${PLATFORM}" \
            prepare
    )
}

push_one() {
    local image="$1"
    local tag="$2"
    if ! ensure_local_tag "${image}" "${tag}"; then
        echo "missing local image: ${REGISTRY}/${image}:${tag}" >&2
        exit 1
    fi
    log "Pushing ${REGISTRY}/${image}:${tag}"
    docker push "${REGISTRY}/${image}:${tag}"
}

push_images() {
    log "Pushing canonical prepare images to ${REGISTRY}"
    for image in "${IMAGES[@]}"; do
        push_one "${image}" "${VERSION}"
        if [ "${VERSION}" != "latest" ]; then
            push_one "${image}" "latest"
        fi
    done
}

status_images() {
    log "Local image status (registry: ${REGISTRY}, version: ${VERSION})"
    echo ""
    printf "%-35s %-8s %-8s\n" "IMAGE" "VERSION" "LATEST"
    printf "%-35s %-8s %-8s\n" "-----" "-------" "------"

    for image in "${IMAGES[@]}"; do
        version_status="no"
        latest_status="no"

        if ensure_local_tag "${image}" "${VERSION}"; then
            version_status="yes"
        fi
        if ensure_local_tag "${image}" "latest"; then
            latest_status="yes"
        fi

        printf "%-35s %-8s %-8s\n" "${image}" "${version_status}" "${latest_status}"
    done
}

case "${1:-help}" in
    prepare)
        prepare_images
        ;;
    push)
        push_images
        ;;
    prepare-push)
        prepare_images
        push_images
        ;;
    status)
        status_images
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "unknown command: ${1}" >&2
        echo "" >&2
        usage >&2
        exit 1
        ;;
esac
