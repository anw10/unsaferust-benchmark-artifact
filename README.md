# Understanding Unsafe Rust Dynamically: Behaviors and Benchmarks

We provide the artifacts for the paper in two formats:
1. **Docker Image**: A pre-built environment with our modified compiler, benchmarks, and instrumentation tools.
2. **Repository**: The source code to build and run everything from scratch.

## Setup

This repository contains everything needed to build the artifact. No external dependencies or submodules are required for the standard flow.

## Directory Structure

- `rustc/`: The modified Rust compiler source code.
- `perf/`: The instrumentation library and runtime tools.
- `benchmarks/`: The collection of crates used for benchmarking.
- `config.toml`: Configuration file for the `run_all_docker_tests.sh` and build process. Defines the build parameters for `rustc`.
- `pipeline/`: Scripts for running automated experiment pipelines.
- `Dockerfile`: Configuration for building the Docker image.

## Docker: Getting Started

You can load our pre-built image or build it locally.

### 1. Load Pre-built Image
```bash
docker load -i unsaferustbenchv2.tar
docker run -it unsaferustbench:v2.0
```

### 2. Build Locally
If you prefer to build the image yourself (e.g., to include local changes):
```bash
./docker-build.sh
```
This will build the image `unsaferust-bench:local`.

## Automating Experiments

We provide a comprehensive script to run all experiments automatically.

### Run All Experiments
Inside the container (or via `docker run` from host), you can execute:

```bash
# From host:
docker run --rm -v $(pwd)/run_all_docker_tests.sh:/workspace/run_all_docker_tests.sh \
    unsaferust-bench:local bash /workspace/run_all_docker_tests.sh
```

This script will:
1. Sequentially build the `perf` library for each mode (CPU, Heap, Counter, Coverage).
2. Run the benchmarks for all qualified crates.
3. Output results to the `pipeline/` directory.

## Manual Usage (Inside Container)

Once inside the container (`docker run -it ...`), you are in `/workspace`.

### 1. Build Instrumentation
Navigate to `perf` and build the desired tool:
```bash
cd perf
make coverage   # Options: coverage, counter, heap, cpu
```

### 2. Setup Environment
Source the environment script to link the instrumented library:
```bash
cd env
source coverage.sh
```

### 3. Run Benchmark
Navigate to a benchmark and run it:
```bash
cd ../../benchmarks/arrayvec-0.7.6
cargo bench
```

### 4. View Results
Results are typically written to `/tmp/`:
```bash
ls -l /tmp/*.stat
```

## config.toml
The `config.toml` file in the root directory controls the build configuration for the custom Rust compiler. It is copied into the Docker image during the build process to ensure the compiler is built with the correct flags and options supported by our instrumentation.

## Troubleshooting

- **Build Time**: Building the Docker image involves compiling LLVM and `rustc`, which can take 1-2 hours.
- **Memory**: Ensure Docker has at least 8GB of RAM allocated.
