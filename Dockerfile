FROM ubuntu:22.04

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    cmake \
    ninja-build \
    python3 \
    python3-pip \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Copy ONLY rustc first to cache the heavy build
COPY rustc /workspace/rustc

# Configure rustc build for Docker
# The config.toml in rustc/config.toml is already configured for this environment:
# - prefix = "/workspace/rust-root"
# - extended = true
# - tools = ["cargo"]


# Build rustc and LLVM
# Fix: Increase stack size to prevent SIGSEGV (needs 32MB for some crates)
ENV RUST_MIN_STACK=67108864
RUN cd rustc && \
    python3 x.py build -j 4 && \
    python3 x.py build src/tools/cargo -j 4 && \
    python3 x.py install -j 4

# Set up environment variables for the instrumentation
# We need these set BEFORE building perf so it uses the correct compiler
# 1. /workspace/rust-root/bin: The 'install' step puts the stable binaries here (rustc, cargo)
# 2. /workspace/rustc/build/.../stage1/bin: The stage1 compiler (if needed directly)
# 3. llvm/bin: For llvm-config
ENV RUSTC_PATH=/workspace/rust-root/bin/rustc
ENV RUSTC=/workspace/rust-root/bin/rustc
ENV PATH="/workspace/rust-root/bin:/workspace/rustc/build/x86_64-unknown-linux-gnu/stage1/bin:/workspace/rustc/build/x86_64-unknown-linux-gnu/llvm/bin:${PATH}"

# Copy the rest of the repository (scripts, benchmarks, perf)
# This way, changes to scripts don't invalidate the rustc build
COPY . /workspace/

# Install JDK for JNI benchmark and Clang for Ring (Placed here to preserve rustc build cache)
RUN apt-get update && apt-get install -y default-jdk clang && rm -rf /var/lib/apt/lists/*

# Build the Instrumentation Library
# We build 'coverage' by default so the library is present.
# Note: The 'run_all_docker_tests.sh' script will strictly clean and rebuild this
# for specific experiments (cpu, heap, etc.), but this ensures a valid state out-of-the-box.
RUN cd perf && make coverage

# Set the default working directory to perf
# WORKDIR /workspace/perf

CMD ["/bin/bash"]
