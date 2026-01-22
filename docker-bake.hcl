# =============================================================================
# CRS-multilang Docker Bake Configuration
# =============================================================================
#
# Replaces multilang-all.sh with parallel builds and proper dependency tracking.
#
# Build order (with parallelism):
#   parallel:  multilang-clang ─────────┐
#                                       ├──► multilang-builder ──► crs-multilang
#   parallel:  multilang-builder-jvm ───┘
#
# Usage:
#   docker buildx bake prepare     # Build all base images
#   docker buildx bake prepare-c   # Build C/C++ images only
#   docker buildx bake prepare-jvm # Build JVM images only
#   docker buildx bake --print     # Show build plan as JSON
#
# =============================================================================

variable "BASE_IMAGES_DIR" {
  default = "libs/oss-fuzz/infra/base-images"
}

# -----------------------------------------------------------------------------
# Groups
# -----------------------------------------------------------------------------

group "default" {
  targets = ["prepare"]
}

group "prepare" {
  targets = ["multilang-clang", "multilang-builder", "multilang-builder-jvm", "multilang-c-archive", "multilang-jvm-archive", "crs-multilang"]
}

group "prepare-c" {
  targets = ["multilang-clang", "multilang-builder", "multilang-c-archive", "crs-multilang"]
}

group "prepare-jvm" {
  targets = ["multilang-builder-jvm", "multilang-jvm-archive"]
}

# Archive images for extracting build artifacts
group "archives" {
  targets = ["multilang-c-archive", "multilang-jvm-archive"]
}

# -----------------------------------------------------------------------------
# Base Images (PREPARE phase)
# -----------------------------------------------------------------------------

# Custom LLVM/Clang with fuzzing support
# Independent - can build in parallel with multilang-builder-jvm
target "multilang-clang" {
  context    = "${BASE_IMAGES_DIR}/multilang-clang"
  dockerfile = "Dockerfile"
  tags       = ["multilang-clang:latest"]
}

# C/C++ builder with Rust, Python, compile scripts
# Depends on multilang-clang
target "multilang-builder" {
  context    = "${BASE_IMAGES_DIR}/base-builder"
  dockerfile = "Dockerfile.multilang"
  tags       = ["multilang-builder:latest"]
  contexts = {
    multilang-clang = "target:multilang-clang"
  }
}

# JVM builder with Jazzer
# Independent - can build in parallel with multilang-clang
target "multilang-builder-jvm" {
  context    = "${BASE_IMAGES_DIR}/base-builder-jvm"
  dockerfile = "Dockerfile.multilang"
  tags       = ["multilang-builder-jvm:latest"]
}

# -----------------------------------------------------------------------------
# CRS Main Image
# -----------------------------------------------------------------------------

# Main CRS image with UniAFL, llvm-cov-custom, FuzzDB, libCRS
target "crs-multilang" {
  context    = "."
  dockerfile = "Dockerfile"
  tags       = ["crs-multilang:latest"]
  # Note: Dockerfile uses COPY --from=multilang-builder implicitly
  # The FROM statements in Dockerfile handle dependencies
}

# -----------------------------------------------------------------------------
# Archive Images (for extracting build artifacts)
# -----------------------------------------------------------------------------

# C/C++ archive - extracts llvm-patched, libclang_rt.fuzzer.a, compile
target "multilang-c-archive" {
  context    = "."
  dockerfile = "Dockerfile.c_archive"
  tags       = ["multilang-c-archive:latest"]
  contexts = {
    multilang-builder = "target:multilang-builder"
  }
}

# JVM archive - extracts Jazzer artifacts
target "multilang-jvm-archive" {
  context    = "."
  dockerfile = "Dockerfile.jvm_archive"
  tags       = ["multilang-jvm-archive:latest"]
  contexts = {
    multilang-builder-jvm = "target:multilang-builder-jvm"
  }
}

# -----------------------------------------------------------------------------
# Runner Image (for OSS-CRS run phase)
# -----------------------------------------------------------------------------

# Thin runner that references crs-multilang
# This can be customized for specific run configurations
target "crs-multilang-runner" {
  context    = "."
  dockerfile = "runner.Dockerfile"
  tags       = ["crs-multilang-runner:latest"]
  contexts = {
    crs-multilang = "target:crs-multilang"
  }
}
