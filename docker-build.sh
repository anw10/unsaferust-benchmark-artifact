#!/bin/bash

# Script to build the unsafe Rust benchmark Docker image

set -e

echo "Building unsafe Rust benchmark Docker image..."
echo "WARNING: This build will take 1-2 hours or more depending on your system."
echo "The build process includes:"
echo "  0. Configuration check"
echo "  1. Installing system dependencies"
echo "  2. Copying repository files into Docker"
echo "  3. Building the custom Rust compiler from source"
echo "  4. Building default instrumentation library (coverage)"
echo ""
# Non-interactive mode
echo "Start building..."

# Step 0: Configuration Check
echo "Step 0: Checking configuration..."
if [ -f "config.toml" ]; then
    echo "Found local config.toml."
    # Copy to rustc directory for build
    echo "Copying config.toml to ./rustc/config.toml..."
    cp config.toml rustc/config.toml
else
    echo "WARNING: config.toml not found in current directory."
    echo "Using default configuration from repository."
fi

echo ""


echo ""
echo "Step 1-4: Building Docker image..."
# Build the Docker image
docker build -t unsaferust-bench:local -f Dockerfile . 2>&1 | tee build.log

echo ""
echo "Build complete! To run the container:"
echo "  docker run -it unsaferust-bench:local"
echo ""
echo "To run a specific benchmark:"
echo "  docker run -it unsaferust-bench:local bash -c 'cd /workspace/benchmarks/arrayvec-0.7.6 && cargo bench'"
echo ""
echo "To run ALL experiments automatically:"
echo "  docker run --rm -v \$(pwd)/run_all_docker_tests.sh:/workspace/run_all_docker_tests.sh unsaferust-bench:local bash /workspace/run_all_docker_tests.sh"
