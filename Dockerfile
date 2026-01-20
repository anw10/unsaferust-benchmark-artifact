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

# Copy the local repository contents
# Note: This includes all files from your local clone
COPY . /workspace/

# Copy the config.toml to the rustc directory
# This ensures we use the exact configuration requested
COPY config.toml /workspace/rustc/config.toml



# Build rustc and LLVM
# Fix: Increase stack size to prevent SIGSEGV (needs 32MB for some crates)
ENV RUST_MIN_STACK=67108864
RUN cd rustc && \
    python3 x.py build -j 4 && \
    python3 x.py build src/tools/cargo -j 4 && \
    python3 x.py install -j 4

# Set up environment variables for the instrumentation
# We need these set BEFORE building perf so it uses the correct compiler
ENV RUSTC_PATH=/workspace/rustc/build/x86_64-unknown-linux-gnu/stage1/bin/rustc
ENV RUSTC=/workspace/rustc/build/x86_64-unknown-linux-gnu/stage1/bin/rustc
# Added llvm-config path as requested
ENV PATH="/workspace/rustc/build/x86_64-unknown-linux-gnu/stage1/bin:/workspace/rustc/build/x86_64-unknown-linux-gnu/llvm/bin:${PATH}"

# Build the Instrumentation Library
# We build 'coverage' by default so the library is present.
# Note: The 'run_all_docker_tests.sh' script will strictly clean and rebuild this
# for specific experiments (cpu, heap, etc.), but this ensures a valid state out-of-the-box.
RUN cd perf && make coverage

# Set the default working directory to perf
# WORKDIR /workspace/perf

CMD ["/bin/bash"]
