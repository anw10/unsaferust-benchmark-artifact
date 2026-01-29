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
- `pipeline/`: Scripts for running automated experiment pipelines.
- `config.toml`: Configuration file for the build process (controls custom `rustc` build).
- `Dockerfile`: Configuration for building the Docker image.
- `master_runtime_stats.json`: Aggregated runtime data (CPU, Heap, Unsafe Counts) for all crates.
- `benchmark_configs.md`: Detailed configuration and static characteristics of the benchmarks.
- `benchmark_runtime_stats.csv`: Summary of crate metadata (LOC, downloads, unsafe %) and runtime statistics.

## Experiment Methodology & Data Sources

We distinguish between two types of data and experiments in this artifact:

1. **Runtime Behavior Analysis (100 Crates)**
   - **Source**: Dataset of 100 popular crates.
   - **Method**: Executed via **`cargo test`** suites.
   - **Instrumentation**: `cpu_cycle`, `heap_tracker`, `unsafe_counter`.
   - **Data**: The aggregated results are stored in `master_runtime_stats.json`. This corresponds to the runtime analysis phase described in the paper.

2. **Benchmark Dynamics (Benchmark Suite)**
   - **Source**: The specific benchmarks located in the `benchmarks/` directory (e.g., `ring`, `regex`).
   - **Method**: Executed via **`cargo bench`** performance benchmarks.
   - **Configuration**: Detailed commands and flags are listed in `benchmark_configs.md`.
   - **Goal**: To analyze behavior under specific high-load scenarios.

## Docker: Getting Started

You can load our pre-built image or build it locally.

### 1. Download and Load Tarball Docker Image (Recommended)

If you have the offline archive:

```bash
unzip unsaferustbenchv3.zip
docker load -i unsaferustbenchv3.tar
docker run -it unsaferustbench:v3
```

### 2. Build Locally

If you prefer to build the image yourself (e.g., to include local changes):

```bash
./docker-build.sh
```

This will build the image `unsaferust-bench:local`. It takes 1-2 hours as it compiles Rust from source.

## Automating Experiments (AIO)

We provide a comprehensive script to run experiments automatically.

### 1. Run Native Baseline (All Crates)

To run a native baseline (compilation and execution without extra instrumentation) for **all crates**, use the following command with no arguments:

```bash
# Inside the container:
python3 run_pipeline.py --showstats
```

_Note: This defaults to `-experiment native` and runs all crates._

### 2. Run Coverage Experiment (All Crates)

To run the unsafe coverage instrumentation on all crates:

```bash
python3 run_pipeline.py --experiment coverage --showstats
```

### 3. Run Specific Experiments

You can also use the script to run other experiments (`cpu_cycle`, `heap_tracker`, `unsafe_counter`):

```bash
python3 run_pipeline.py --experiment cpu_cycle --showstats
```

### Options

- `--experiment <name>`: Choose from `native`, `coverage`, `cpu_cycle`, `heap_tracker`, `unsafe_counter`.
- `--crate <name>`: Run for a specific crate only.
- `--showstats`: Display aggregated statistics table in the console.
- `--output <dir>`: Specify output directory.

## Manual Usage (Inside Container)

If you wish to run benchmarks manually or inspect specific crates, follow these steps inside the container (`/workspace`):

### 1. Build Instrumentation

Navigate to `perf` and build the desired tool:

```bash
cd perf
make coverage   # Options: coverage, counter, heap, cpu
```

### 2. Setup Environment

Source the environment script to link the instrumented library. These scripts set the correct `RUSTFLAGS` and output paths.

```bash
# From workspace root:
source pipeline/env/coverage.sh   # For coverage
# OR
source pipeline/env/cpu.sh        # For CPU cycle
# OR
source pipeline/env/heap.sh       # For Heap usage
# OR
source pipeline/env/counter.sh    # For Unsafe counter
```

_Note: Make sure to source only one environment script at a time (start a fresh shell if switching)._

### 3. Run Benchmark

Navigate to a benchmark and run it using `cargo bench`. See [Benchmark Configurations](benchmark_configs.md) for specific flags or commands used for complex crates.

```bash
cd benchmarks/arrayvec-0.7.6
cargo bench
```

### 4. View Results

Results are written to `/tmp/` by default when running manually:

```bash
ls -l /tmp/*.stat
cat /tmp/unsafe_coverage.stat
```

## Troubleshooting

- **Build Time**: Building the Docker image involves compiling LLVM and `rustc`, which can take 1-2 hours.
- **Memory**: Ensure Docker has at least 8GB of RAM allocated.
- **Output Paths**: The automated pipeline stores results in `pipeline/results/`, while manual runs typically output to `/tmp/` (controlled by `UNSAFE_BENCH_OUTPUT_DIR`).
