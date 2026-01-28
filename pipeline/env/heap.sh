#!/bin/bash
# Environment setup for Heap Tracker

# Path to the instrumentation library (must be built first via 'cd perf && make heap')
export PERF_LIB="/workspace/perf/target/release/libunsafe_perf.rlib"
export PERF_DEPS="/workspace/perf/target/release/deps"

export RUSTC_BOOTSTRAP=1
export RUSTUP_TOOLCHAIN=stage1

# Flags for Heap Tracker:
# - enable instmarker
# - enable heap-tracker
export RUSTFLAGS="--emit=llvm-ir,link -Z unstable-options --extern force:unsafe_perf=$PERF_LIB -L $PERF_DEPS -C unsafe_include_native_lib=false -C llvm-args=-enable-instmarker -C llvm-args=-enable-heap-tracker"

export UNSAFE_BENCH_OUTPUT_DIR="/tmp"

echo "Environment configured for Heap Tracking."
echo "Output will be written to: $UNSAFE_BENCH_OUTPUT_DIR"
