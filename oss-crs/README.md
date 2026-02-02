# OSS-CRS

A framework for running Cyber Reasoning Systems (CRS) for automated bug finding and fixing.

## Prerequisites

1. **Clone oss-fuzz** (contains target project definitions):
   ```bash
   git clone git@github.com:Team-Atlanta/oss-fuzz.git ~/oss-fuzz
   ```

2. **Clone oss-crs**:
   ```bash
   git clone git@github.com:sslab-gatech/oss-crs.git ~/oss-crs
   cd ~/oss-crs
   git checkout "feat/refine-oss-crs"
   ```

## Configuration

Create a compose configuration file (e.g., `/tmp/example-compose.yaml`):

```yaml
run_env: local
docker_registry: ghcr.io/team-atlanta/test  # Customize as needed

# Infrastructure settings (required)
oss_crs_infra:
  cpuset: "0-3"
  memory: "8G"

# CRS instance A
bugfinding-a:
  source:
    # Option 1: Use a remote repository
    # url: https://github.com/Team-Atlanta/atlantis-multilang-given_fuzzer
    # ref: main
    
    # Option 2: Use a local path
    local_path: ~/atlantis-multilang-given_fuzzer
  cpuset: "4-7"
  memory: "16G"
  llm_budget: 100  # Budget in dollars

# CRS instance B (optional, for ensemble runs)
bugfinding-b:
  source:
    local_path: ~/atlantis-multilang-given_fuzzer
  cpuset: "8-11"
  memory: "16G"
  llm_budget: 100
```

## Usage

Run the following commands from the `oss-crs` directory:

### 1. Prepare the environment

```bash
uv run crs-compose prepare --compose-file /tmp/example-compose.yaml
```

### 2. Build the target

```bash
uv run crs-compose build-target \
  --compose-file /tmp/example-compose.yaml \
  --target-proj-path ~/oss-fuzz/projects/aixcc/c/mock-c
```

### 3. Run the CRS

```bash
uv run crs-compose run \
  --compose-file /tmp/example-compose.yaml \
  --target-proj-path ~/oss-fuzz/projects/aixcc/c/mock-c \
  --target-harness fuzz_process_input_header
```
