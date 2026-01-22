# =============================================================================
# CRS-multilang Builder Dockerfile (given_fuzzer variant)
# =============================================================================
# BUILD phase: Sets up build tools, compilation happens at runtime via compile_crs.
#
# This Dockerfile only prepares the build environment (LLVM, Jazzer, compile script).
# Actual compilation is deferred to `docker compose run` where source code is
# available via the framework's source injection (docker-commit).
#
# Build args (provided by OSS-CRS):
#   - parent_image: Project image with deps (e.g., gcr.io/oss-fuzz/json-c)
#   - CRS_TARGET: Target project name
#   - FUZZING_LANGUAGE: Project language (c, c++, rust, go, python, jvm)
# =============================================================================

ARG parent_image=ubuntu:22.04

# Reference archive images for CRS build tools
FROM ghcr.io/team-atlanta/multilang-given_fuzzer-c-archive:latest AS crs-tools-c
FROM ghcr.io/team-atlanta/multilang-given_fuzzer-jvm-archive:latest AS crs-tools-jvm

# =============================================================================
# Builder: parent_image + CRS tools
# =============================================================================
FROM ${parent_image}

COPY --from=crs-tools-c /multilang-builder/llvm-patched /opt/llvm-patched
COPY --from=crs-tools-c /multilang-builder/libclang_rt.fuzzer.a /usr/local/lib/clang/18/lib/x86_64-unknown-linux-gnu/libclang_rt.fuzzer.a
COPY --from=crs-tools-c /multilang-builder/compile /usr/local/bin/compile
COPY --from=crs-tools-jvm /multilang-builder/jazzer_agent_deploy.jar /usr/local/bin/jazzer_agent_deploy.jar
COPY --from=crs-tools-jvm /multilang-builder/jazzer_driver /usr/local/bin/jazzer_driver
COPY --from=crs-tools-jvm /multilang-builder/jazzer_api_deploy.jar /usr/local/lib/jazzer_api_deploy.jar
COPY --from=crs-tools-jvm /multilang-builder/jazzer_junit.jar /usr/local/bin/jazzer_junit.jar

ARG CRS_TARGET
ARG FUZZING_LANGUAGE
ENV CRS_TARGET=${CRS_TARGET}
ENV FUZZING_LANGUAGE=${FUZZING_LANGUAGE}
ENV FUZZING_ENGINE=libfuzzer
ENV SANITIZER=address
ENV ARCHITECTURE=x86_64

# Install rsync for clean source snapshots between build variants
RUN apt-get update -qq && apt-get install -y -qq rsync >/dev/null 2>&1 || true

COPY bin/compile_crs /usr/local/bin/compile_crs

CMD ["compile_crs"]
