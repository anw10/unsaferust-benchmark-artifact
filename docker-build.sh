#!/bin/bash

# Script to build the unsafe Rust benchmark Docker image

set -e

echo "Building unsafe Rust benchmark Docker image..."
echo "WARNING: This build will take 1-2 hours or more depending on your system."
echo "The build process includes:"
echo "  0. Updating repositories to latest changes (rustc + LLVM oscardev branch)"
echo "  1. Installing system dependencies"
echo "  2. Copying repository files into Docker"
echo "  3. Building the custom Rust compiler from source"
echo "  4. Building instrumentation tools"
echo ""
read -p "Do you want to continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Build cancelled."
    exit 1
fi

echo ""
echo "Step 0: Updating repositories..."
./update-repos.sh

echo ""
echo "Step 1-4: Building Docker image..."
# Build the Docker image
docker build -t unsaferust-bench:local -f Dockerfile .

echo ""
echo "Build complete! To run the container:"
echo "  docker run -it unsaferust-bench:local"
echo ""
echo "To run a specific benchmark:"
echo "  docker run -it unsaferust-bench:local bash -c 'cd /workspace/benchmarks/arrayvec-0.7.6 && cargo bench'"
