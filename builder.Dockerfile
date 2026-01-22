# =============================================================================
# CRS-multilang Builder Dockerfile
# =============================================================================
# BUILD phase: Compiles fuzzers for the target project.
#
# Uses multilang-c-archive to get CRS build tools:
#   - llvm-patched (custom LLVM for instrumentation)
#   - libclang_rt.fuzzer.a (libFuzzer runtime)
#   - compile (OSS-Fuzz compile script)
#
# Usage:
#   docker compose up --build <crs_name>_builder
#
# Build args (provided by OSS-CRS):
#   - parent_image: Project image (e.g., gcr.io/oss-fuzz/json-c)
#   - CRS_TARGET: Target project name
#   - PROJECT_PATH: Path to OSS-Fuzz project directory
# =============================================================================

# ARG must be declared before FROM that uses it
ARG parent_image

# Reference archive image for COPY --from
FROM multilang-c-archive AS crs-tools

# Start from the project image built by OSS-Fuzz
FROM ${parent_image}

# Copy CRS build tools from archive
COPY --from=crs-tools /multilang-builder/llvm-patched /opt/llvm-patched
COPY --from=crs-tools /multilang-builder/libclang_rt.fuzzer.a /usr/local/lib/clang/18/lib/x86_64-unknown-linux-gnu/libclang_rt.fuzzer.a
COPY --from=crs-tools /multilang-builder/compile /usr/local/bin/compile

# Environment for build
ARG CRS_TARGET
ENV CRS_TARGET=${CRS_TARGET}
ENV FUZZING_ENGINE=libfuzzer
ENV SANITIZER=address
ENV ARCHITECTURE=x86_64

# Inherit WORKDIR from parent image (project source directory)
# Don't override - build.sh expects to run from the source dir

# Default: run compile script
CMD ["compile"]
