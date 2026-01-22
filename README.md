# CRS-multilang

Multi-language Cyber Reasoning System for automated vulnerability discovery using UniAFL.

## OSS-CRS Integration

### Three-Phase Architecture

```
PREPARE → BUILD → RUN
```

**PREPARE** (one-time): Build CRS infrastructure images
**BUILD** (per-project): Compile fuzzers for a target project
**RUN** (per-harness): Execute fuzzing for each harness

### PREPARE Phase

Build all required base images:

```bash
docker buildx bake prepare        # Build all base images
docker buildx bake prepare-c      # Build C/C++ images only
docker buildx bake prepare-jvm    # Build JVM images only
```

**Image Dependencies:**

```
multilang-clang ──► multilang-builder ──► multilang-c-archive ──┐
                                                                ├──► crs-multilang ──► crs-multilang-runner
multilang-builder-jvm ──► multilang-jvm-archive ────────────────┘
```

### BUILD Phase

Compile fuzzers for a target project:

```bash
docker build \
  --build-arg parent_image=gcr.io/oss-fuzz/json-c \
  --build-arg CRS_TARGET=json-c \
  -f builder.Dockerfile \
  -t crs-builder-json-c .

docker run -v ./out:/out crs-builder-json-c
```

### RUN Phase

Execute CRS fuzzing:

```bash
docker buildx bake crs-multilang-runner

docker run \
  -v ./out:/out:ro \
  -v ./artifacts:/artifacts \
  -e CRS_TARGET=json-c \
  -e FUZZING_LANGUAGE=c \
  -e CRS_NAME=crs-multilang \
  crs-multilang-runner json_parse_fuzzer
```

## Environment Variables

### Build Phase

| Variable | Default | Description |
|----------|---------|-------------|
| `SANITIZER` | `address` | Sanitizer(s): `address`, `undefined`, `address,undefined` |
| `FUZZING_ENGINE` | `libfuzzer` | Fuzzing engine |
| `CRS_TARGET` | - | Target project name |

### Run Phase

| Variable | Default | Description |
|----------|---------|-------------|
| `CRS_NAME` | - | CRS identifier (enables OSS-CRS mode) |
| `CRS_TARGET` | - | Target project name |
| `TARGET_HARNESS` | (all) | Run only this harness |
| `FUZZING_LANGUAGE` | `c` | Target language: `c`, `c++`, `jvm` |

## Output Structure

```
/artifacts/
├── povs/{harness}/           # Discovered POVs (deduplicated)
│   └── {hash}_{filename}
├── corpus/{harness}/         # Fuzzing corpus
└── crs-data/
    └── coverage/{harness}/   # Coverage data
```

## Delta Mode

Focus fuzzing on code changes by providing a diff file:

```bash
docker run -v ./changes.diff:/ref.diff:ro crs-multilang-runner harness_name
```

## Ensemble Mode

Share seeds between multiple CRS instances:

```bash
docker run -v ./seed_share:/seed_share_dir crs-multilang-runner harness_name
```

## Architecture

```
CRS-multilang/
├── bin/                        # Executable scripts
│   ├── main.py                 # Main entry point (UniAFL module)
│   ├── crs_entrypoint          # Container entrypoint
│   ├── run_once                # Single input executor
│   ├── cov_runner              # Coverage runner mode
│   ├── watchdog.py             # Status logging
│   ├── seed_share.py           # Ensemble seed sharing
│   ├── extract_from_diff.py    # Delta mode diff processing
│   ├── jazzer_cleaner.py       # JVM temp cleanup
│   ├── get_run_fuzzer_opt      # Fuzzer option parsing
│   └── symbolizer/             # Coverage symbolization
├── libs/
│   ├── libCRS/                 # Core CRS Python library
│   │   ├── crs.py              # CRS framework
│   │   ├── config.py           # Configuration
│   │   ├── challenge.py        # Harness handling
│   │   ├── module.py           # Module abstraction
│   │   ├── paths.py            # Path resolution
│   │   ├── submit.py           # POV deduplication (SQLite)
│   │   ├── ossfuzz_lib.py      # Fuzz target detection
│   │   └── util.py             # Utilities
│   └── oss-fuzz/               # OSS-Fuzz base images
├── uniafl/                     # UniAFL fuzzer (Rust)
├── fuzzdb/                     # Coverage database (Rust + Python)
│   ├── src/                    # Rust implementation
│   └── python/                 # Python bindings
├── Dockerfile                  # Main CRS image
├── builder.Dockerfile          # BUILD phase image
├── runner.Dockerfile           # RUN phase image
├── Dockerfile.c_archive        # C/C++ build tools archive
├── Dockerfile.jvm_archive      # JVM build tools archive
└── docker-bake.hcl             # Build orchestration
```
