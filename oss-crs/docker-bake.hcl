# =============================================================================
# CRS-multilang Docker Bake Configuration (given_fuzzer variant)
# =============================================================================
#
# Replaces multilang-all.sh with parallel builds and proper dependency tracking.
#
# Build order (with parallelism):
#   parallel:  multilang-given_fuzzer-clang ─────────┐
#                                                    ├──► multilang-given_fuzzer-builder ──► multilang-given_fuzzer-crs
#   parallel:  multilang-given_fuzzer-builder-jvm ───┘
#
# Usage (OSS-CRS prepare phase - uses cached images from registry):
#   docker buildx bake prepare        # Pull cached images from registry (default)
#   docker buildx bake prepare-c      # C/C++ images only
#   docker buildx bake prepare-jvm    # JVM images only
#
# Build from scratch (Team Atlanta):
#   USE_PREBUILT=false docker buildx bake prepare
#   docker buildx bake --push prepare  # Build and push to registry
#
# Show build plan:
#   docker buildx bake --print
#
# =============================================================================

variable "BASE_IMAGES_DIR" {
  default = "libs/oss-fuzz/infra/base-images"
}

variable "REGISTRY" {
  default = "ghcr.io/team-atlanta"
}

variable "VERSION" {
  default = "latest"
}

# When true (default): Pull cached images from registry, build only if cache miss
# When false: Build everything from scratch locally
variable "USE_PREBUILT" {
  default = false
}

# Helper function to generate tags
function "tags" {
  params = [name]
  result = [
    "${REGISTRY}/${name}:${VERSION}",
    "${REGISTRY}/${name}:latest",
    "${name}:latest"
  ]
}

# Helper to get image source (registry or local build target)
function "image_source" {
  params = [name]
  result = USE_PREBUILT ? "docker-image://${REGISTRY}/${name}:${VERSION}" : "target:${name}"
}

# -----------------------------------------------------------------------------
# Groups
# -----------------------------------------------------------------------------

group "default" {
  targets = ["prepare"]
}

group "prepare" {
  targets = ["multilang-given_fuzzer-clang", "multilang-given_fuzzer-builder", "multilang-given_fuzzer-builder-jvm", "multilang-given_fuzzer-c-archive", "multilang-given_fuzzer-jvm-archive", "multilang-given_fuzzer-crs"]
}

group "prepare-c" {
  targets = ["multilang-given_fuzzer-clang", "multilang-given_fuzzer-builder", "multilang-given_fuzzer-c-archive", "multilang-given_fuzzer-crs"]
}

group "prepare-jvm" {
  targets = ["multilang-given_fuzzer-builder-jvm", "multilang-given_fuzzer-jvm-archive"]
}

# Archive images for extracting build artifacts
group "archives" {
  targets = ["multilang-given_fuzzer-c-archive", "multilang-given_fuzzer-jvm-archive"]
}

# -----------------------------------------------------------------------------
# Base Images (PREPARE phase)
# -----------------------------------------------------------------------------

# Custom LLVM/Clang with fuzzing support
# Independent - can build in parallel with multilang-given_fuzzer-builder-jvm
target "multilang-given_fuzzer-clang" {
  context    = "${BASE_IMAGES_DIR}/multilang-clang"
  dockerfile = "Dockerfile"
  tags       = tags("multilang-given_fuzzer-clang")
  cache-from = USE_PREBUILT ? ["type=registry,ref=${REGISTRY}/multilang-given_fuzzer-clang:${VERSION}"] : []
}

# C/C++ builder with Rust, Python, compile scripts
# Depends on multilang-given_fuzzer-clang
target "multilang-given_fuzzer-builder" {
  context    = "${BASE_IMAGES_DIR}/base-builder"
  dockerfile = "Dockerfile.multilang"
  tags       = tags("multilang-given_fuzzer-builder")
  contexts = {
    multilang-clang = image_source("multilang-given_fuzzer-clang")
  }
  cache-from = USE_PREBUILT ? ["type=registry,ref=${REGISTRY}/multilang-given_fuzzer-builder:${VERSION}"] : []
}

# JVM builder with Jazzer
# Independent - can build in parallel with multilang-given_fuzzer-clang
target "multilang-given_fuzzer-builder-jvm" {
  context    = "${BASE_IMAGES_DIR}/base-builder-jvm"
  dockerfile = "Dockerfile.multilang"
  tags       = tags("multilang-given_fuzzer-builder-jvm")
  cache-from = USE_PREBUILT ? ["type=registry,ref=${REGISTRY}/multilang-given_fuzzer-builder-jvm:${VERSION}"] : []
}

# -----------------------------------------------------------------------------
# CRS Main Image
# -----------------------------------------------------------------------------

# Main CRS image with UniAFL, llvm-cov-custom, FuzzDB, libCRS
target "multilang-given_fuzzer-crs" {
  context    = "."
  dockerfile = "Dockerfile"
  tags       = tags("multilang-given_fuzzer-crs")
  cache-from = USE_PREBUILT ? ["type=registry,ref=${REGISTRY}/multilang-given_fuzzer-crs:${VERSION}"] : []
}

# -----------------------------------------------------------------------------
# Archive Images (for extracting build artifacts)
# -----------------------------------------------------------------------------

# C/C++ archive - extracts llvm-patched, libclang_rt.fuzzer.a, compile
target "multilang-given_fuzzer-c-archive" {
  context    = "."
  dockerfile = "Dockerfile.c_archive"
  tags       = tags("multilang-given_fuzzer-c-archive")
  contexts = {
    multilang-given_fuzzer-builder = image_source("multilang-given_fuzzer-builder")
  }
  cache-from = USE_PREBUILT ? ["type=registry,ref=${REGISTRY}/multilang-given_fuzzer-c-archive:${VERSION}"] : []
}

# JVM archive - extracts Jazzer artifacts
target "multilang-given_fuzzer-jvm-archive" {
  context    = "."
  dockerfile = "Dockerfile.jvm_archive"
  tags       = tags("multilang-given_fuzzer-jvm-archive")
  contexts = {
    multilang-given_fuzzer-builder-jvm = image_source("multilang-given_fuzzer-builder-jvm")
  }
  cache-from = USE_PREBUILT ? ["type=registry,ref=${REGISTRY}/multilang-given_fuzzer-jvm-archive:${VERSION}"] : []
}

# -----------------------------------------------------------------------------
# Runner Image (for OSS-CRS run phase)
# -----------------------------------------------------------------------------

# Thin runner that references multilang-given_fuzzer-crs
# This can be customized for specific run configurations
target "multilang-given_fuzzer-runner" {
  context    = "."
  dockerfile = "runner.Dockerfile"
  tags       = tags("multilang-given_fuzzer-runner")
  contexts = {
    multilang-given_fuzzer-crs = image_source("multilang-given_fuzzer-crs")
  }
  cache-from = USE_PREBUILT ? ["type=registry,ref=${REGISTRY}/multilang-given_fuzzer-runner:${VERSION}"] : []
}
