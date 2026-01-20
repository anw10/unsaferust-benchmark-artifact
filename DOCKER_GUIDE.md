# Docker Setup Guide for Unsafe Rust Benchmark

This guide will help you build and run the Unsafe Rust Benchmark artifact in a Docker container, isolated from your production environment.

## Prerequisites

- Docker installed (version 20.10 or later recommended)
- At least 20GB of free disk space
- At least 8GB of RAM available for Docker
- 2-4 hours for the initial build (if building locally)

## Quick Start (Automated)

We provide a streamlined workflow to build and run all tests:

1. **Build the Image**:
   ```bash
   ./docker-build.sh
   ```

2. **Run All Experiments**:
   ```bash
   docker run --rm -v $(pwd)/run_all_docker_tests.sh:/workspace/run_all_docker_tests.sh \
       unsaferust-bench:local bash /workspace/run_all_docker_tests.sh
   ```

## Directory Structure inside Docker

- `/workspace/rustc`: The compiled custom Rust compiler.
- `/workspace/perf`: The instrumentation library.
- `/workspace/benchmarks`: Directory containing all target crates.
- `/workspace/pipeline`: Scripts and results for automated experiments.

## Manual Usage

### Option 1: Interactive Shell
```bash
docker run -it unsaferust-bench:local
```

### Step 1: Build an instrumentation tool

Inside the container (`/workspace/perf`), choose ONE instrumentation at a time:

```bash
# For unsafe coverage tracking
make coverage

# For unsafe instruction/function counting
make counter

# For heap usage tracking
make heap

# For CPU cycle tracking
make cpu
```

### Step 2: Source the environment

After building an instrumentation, set up the environment variables:

```bash
cd env

# Source the corresponding environment file
source coverage.sh    # for coverage
# OR
source counter.sh     # for counter
# OR
source heap.sh        # for heap
# OR
source cpu.sh         # for cpu
```

### Step 3: Run a benchmark

Navigate to a benchmark and run it:

```bash
cd /workspace/benchmarks/arrayvec-0.7.6
cargo bench
```

### Step 4: View results

Results are stored in `/tmp/*.stat` files:

```bash
# Example
cat /tmp/unsafe_coverage.stat
```

## Troubleshooting

### Out of memory during build
Increase Docker's memory allocation:
- Docker Desktop: Settings → Resources → Memory (set to at least 8GB)
- Linux: Modify `/etc/docker/daemon.json`

### Instrumentation not showing data
Make sure you:
1. Built the instrumentation with `make <tool>`
2. Sourced the correct environment file
3. Only use ONE instrumentation at a time
