#!/bin/bash
# Environment setup for Unsafe Coverage tracking

# Path to the instrumentation library (must be built first via 'cd perf && make coverage')
export PERF_LIB="/workspace/perf/target/release/libunsafe_perf.rlib"
export PERF_DEPS="/workspace/perf/target/release/deps"

# Ensure Rust environment variables are set for the custom toolchain
export RUSTC_BOOTSTRAP=1
export RUSTUP_TOOLCHAIN=stage1

# Flags for Coverage:
# - link against unsafe_perf
# - disable native lib (for coverage specific)
# - enable instmarker
# - enable dynamic line count
export RUSTFLAGS="--emit=llvm-ir,link -Z unstable-options --extern force:unsafe_perf=$PERF_LIB -L $PERF_DEPS -C unsafe_include_native_lib=false -C llvm-args=-enable-instmarker -C llvm-args=-enable-dynamic-line-count"

# Output directory for stats
export UNSAFE_BENCH_OUTPUT_DIR="/tmp"

echo "Environment configured for Unsafe Coverage."
echo "Output will be written to: $UNSAFE_BENCH_OUTPUT_DIR"
