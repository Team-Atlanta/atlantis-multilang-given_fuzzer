# CRS-multilang

An OSS-CRS compatible Cyber Reasoning System supporting multiple languages (C, C++, Rust, Go, JVM).

## Architecture

```
Builder Phase                          Runner Phase
┌─────────────────────────┐           ┌─────────────────────────────┐
│ builder.Dockerfile       │           │ runner.Dockerfile            │
│                          │           │                              │
│ Stage 1: SANITIZER=addr  │──/out/──▶│ crs_entrypoint               │
│   → fuzzing binary       │           │   ├─ symlink /coverage-out   │
│                          │           │   ├─ extract .crs-src.tar.gz │
│ Stage 2: SANITIZER=cov   │           │   └─ run main.py             │
│   → coverage binary      │           │                              │
│   → .coverage-out/       │           │ main.py → UniAFL             │
│                          │           │   ├─ cfg_analyzer (Redis)    │
│ Final: .crs-src.tar.gz   │           │   ├─ fuzzing loop            │
│                          │           │   └─ coverage symbolization  │
└─────────────────────────┘           └─────────────────────────────┘
```

## OSS-CRS Interface

### Build Phase

The framework provides:
- `parent_image`: Pre-built image with source + deps (e.g., `gcr.io/oss-fuzz/json-c`)
- Build args: `CRS_TARGET`, `FUZZING_LANGUAGE`
- Volume: `/out` (build output destination)

Our builder produces:
- `/out/{harness}` — ASAN-instrumented fuzzing binary
- `/out/.coverage-out/{harness}` — Coverage-instrumented binary (best-effort)
- `/out/.crs-src.tar.gz` — Source tree tarball (for runtime symbolization)

### Run Phase

The framework provides:
- Volumes: `/out` (build output), `/artifacts` (persistent), `/ref.diff` (optional), `/seed_share_dir` (optional)
- Env vars: `CRS_TARGET`, `CRS_NAME`, `SANITIZER`, `FUZZING_ENGINE`
- Command: `["run-harness", "--harness_name", "<harness>"]`

Our runner outputs:
- `/artifacts/povs/` — Discovered crash inputs (POVs)
- `/artifacts/corpus/` — Fuzzing corpus
- `/artifacts/crs-data/coverage/` — Source-level coverage (`.cov` JSON files)

## Coverage Pipeline

Two symbolization paths, selected automatically based on coverage binary availability:

1. **Coverage binary** (preferred): Runs input through coverage-instrumented binary → profraw → profdata → `llvm-cov export` → source-level coverage
2. **addr2line fallback**: Parses SanCov counter addresses via `cfg_analyzer.py` → Redis → `symbolizer.py` → source-level coverage

Both produce the same `.cov` format:
```json
{"func_name": {"src": "/src/project/file.c", "lines": [10, 11, 12]}}
```

## Prepare → Build → Run

The CRS lifecycle has three phases:

### 1. Prepare (one-time base image setup)

Builds the toolchain images that `builder.Dockerfile` and `runner.Dockerfile` depend on:

```
multilang-given_fuzzer-clang ──► multilang-given_fuzzer-builder ──► multilang-given_fuzzer-c-archive ──┐
                                                                                                      ├──► builder.Dockerfile (per-target)
multilang-given_fuzzer-builder-jvm ──► multilang-given_fuzzer-jvm-archive ────────────────────────────┘

multilang-given_fuzzer-crs ──► multilang-given_fuzzer-runner
```

```bash
# Pull pre-built images from registry (default, fast)
docker buildx bake prepare

# Or build from scratch locally
USE_PREBUILT=false docker buildx bake prepare

# Build and push to registry
docker buildx bake --push prepare

# Subsets
docker buildx bake prepare-c    # C/C++ only
docker buildx bake prepare-jvm  # JVM only
```

Images produced:

| Image | Contents |
|-------|----------|
| `multilang-given_fuzzer-clang` | Custom LLVM/Clang with fuzzing support |
| `multilang-given_fuzzer-builder` | C/C++ builder (Rust, Python, compile scripts) |
| `multilang-given_fuzzer-builder-jvm` | JVM builder (Jazzer) |
| `multilang-given_fuzzer-c-archive` | Extracted build artifacts (llvm-patched, libclang_rt.fuzzer.a, compile) |
| `multilang-given_fuzzer-jvm-archive` | Extracted Jazzer artifacts (jazzer_driver, jazzer_agent_deploy.jar) |
| `multilang-given_fuzzer-crs` | Main CRS image (UniAFL, FuzzDB, libCRS, symbolizers) |
| `multilang-given_fuzzer-runner` | Thin runner with `crs_entrypoint` |

### 2. Build (per-target)

Uses `builder.Dockerfile` to compile the target project:

```bash
# Via OSS-CRS framework (automatic)
# The framework builds with: parent_image, CRS_TARGET, FUZZING_LANGUAGE

# Via docker bake (local testing)
docker buildx bake -f docker-bake.hcl

# Via compile_crs wrapper inside the builder container
compile_crs
```

### 3. Run (per-harness)

```bash
# Run a harness
docker run <runner_image> <harness_name>

# List available harnesses
docker run <runner_image> list

# Interactive shell
docker run <runner_image> shell
```

## Configuration

The runner accepts `/crs.config` (JSON):
```json
{
  "target_harnesses": ["harness_name"],
  "modules": ["uniafl"],
  "others": {
    "input_gens": ["mock_input_gen"]
  }
}
```

When run via OSS-CRS, `crs_entrypoint` auto-generates this from the harness name argument.

## Project Structure

```
bin/
  main.py                  # Entry point: configures and runs UniAFL
  crs_entrypoint           # Runtime setup (env, symlinks, source restore)
  compile_crs              # Build wrapper (ASAN + coverage builds)
  watchdog.py              # Periodic coverage/corpus status logging
  symbolizer/
    cfg_analyzer.py        # Binary → address-to-line mapping via objdump
    harness_coverage_runner.py  # Coverage binary symbolization (profraw → llvm-cov)
    symbolizer.py          # addr2line fallback symbolization
    addr_line_mapper.py    # Redis-backed address→line cache
uniafl/                    # Rust fuzzer (LibAFL-based)
  src/
    executor/              # Harness execution, coverage saving, crash detection
    msa/                   # Multi-seed architecture (manager, state, scheduler)
fuzzdb/                    # Seed prioritization (diff matching, vuln scoring)
builder.Dockerfile         # Multi-stage build (ASAN + coverage)
runner.Dockerfile          # Runtime image
docker-bake.hcl            # Docker buildx bake configuration
```
