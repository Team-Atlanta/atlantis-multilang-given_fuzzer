# =============================================================================
# CRS-multilang Runner Dockerfile (given_fuzzer variant)
# =============================================================================
# Runtime image for OSS-CRS run phase.
# Uses multilang-given_fuzzer-crs as base with run-harness entrypoint.
#
# Usage:
#   docker buildx bake multilang-given_fuzzer-runner
#   docker run multilang-given_fuzzer-runner <harness_name> [args...]
# =============================================================================

# Docker will check local first, then pull from registry if not found
FROM ghcr.io/team-atlanta/multilang-given_fuzzer-crs:latest

# Runtime sanitizer options (detect_leaks=0 for fuzzing performance)
ENV ASAN_OPTIONS="alloc_dealloc_mismatch=0:allocator_may_return_null=1:allocator_release_to_os_interval_ms=500:check_malloc_usable_size=0:detect_container_overflow=1:detect_odr_violation=0:detect_leaks=0:detect_stack_use_after_return=1:fast_unwind_on_fatal=0:handle_abort=1:handle_segv=1:handle_sigill=1:max_uar_stack_size_log=16:print_scariness=1:quarantine_size_mb=10:strict_memcmp=1:strip_path_prefix=/workspace/:symbolize=1:use_sigaltstack=1:dedup_token_length=3"
ENV MSAN_OPTIONS="print_stats=1:strip_path_prefix=/workspace/:symbolize=1:dedup_token_length=3"
ENV UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1:print_summary=1:silence_unsigned_overflow=1:strip_path_prefix=/workspace/:symbolize=1:dedup_token_length=3"
ENV FUZZING_ENGINE=libfuzzer
ENV FUZZER_ARGS="-rss_limit_mb=2560 -timeout=25"

WORKDIR /home/crs

# Run phase: ENTRYPOINT handles command ["harness_name", args...]
ENTRYPOINT ["/usr/local/bin/crs_entrypoint", "run-harness"]
