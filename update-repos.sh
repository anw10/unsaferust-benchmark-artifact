#!/bin/bash

# Script to update repositories before building Docker image

set -e

echo "========================================"
echo "Updating repositories to latest changes"
echo "========================================"
echo ""

# Update the main repository
echo "1. Pulling latest changes from main repository..."
git pull origin main || git pull origin master || echo "Note: Could not pull from remote (may already be up to date)"
echo ""

# Remove old unsafe-rust-benchmark and clone fresh from oscardev branch
echo "2. Updating unsafe-rust-benchmark from oscardev branch..."
if [ -d "unsafe-rust-benchmark" ]; then
    echo "   - Backing up existing unsafe-rust-benchmark..."
    mv unsafe-rust-benchmark unsafe-rust-benchmark.backup.$(date +%Y%m%d_%H%M%S)
fi

echo "   - Cloning from git@github.com:GWSysSec/unsafe-rust-benchmark.git (oscardev branch)..."
git clone -b oscardev git@github.com:GWSysSec/unsafe-rust-benchmark.git unsafe-rust-benchmark || \
    git clone -b oscardev https://github.com/GWSysSec/unsafe-rust-benchmark.git unsafe-rust-benchmark

echo ""

# Navigate to unsafe-rust-benchmark directory
cd unsafe-rust-benchmark

# Initialize and update LLVM submodule to latest oscardev branch
echo "3. Updating LLVM submodule (oscardev branch)..."
git submodule update --init --recursive --remote src/llvm-project
echo ""

# Update other submodules
echo "4. Updating other submodules..."
git submodule update --init --recursive
echo ""

# Navigate back to root
cd ..

echo "========================================"
echo "Repository update complete!"
echo "========================================"
echo ""
echo "Summary:"
echo "  - Main repository: updated"
echo "  - unsafe-rust-benchmark: updated to oscardev"
echo "  - LLVM submodule: updated to latest oscardev"
echo "  - Other submodules: initialized and updated"
echo ""
echo "You can now build the Docker image with:"
echo "  ./docker-build.sh"
echo "  or"
echo "  docker build -t unsaferust-bench:local ."
