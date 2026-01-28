#!/bin/bash
# Environment setup for CPU Cycle Counting

# Path to the instrumentation library (must be built first via 'cd perf && make cpu')
export PERF_LIB="/workspace/perf/target/release/libunsafe_perf.rlib"
export PERF_DEPS="/workspace/perf/target/release/deps"

export RUSTC_BOOTSTRAP=1
export RUSTUP_TOOLCHAIN=stage1

# Flags for CPU Cycle:
# - enable instmarker
# - enable cpu-cycle-count
# - enable external-call-tracker
export RUSTFLAGS="--emit=llvm-ir,link -Z unstable-options --extern force:unsafe_perf=$PERF_LIB -L $PERF_DEPS -C unsafe_include_native_lib=false -C llvm-args=-enable-instmarker -C llvm-args=-enable-cpu-cycle-count -C llvm-args=-enable-external-call-tracker"

export UNSAFE_BENCH_OUTPUT_DIR="/tmp"

echo "Environment configured for CPU Cycle Counting."
echo "Output will be written to: $UNSAFE_BENCH_OUTPUT_DIR"
