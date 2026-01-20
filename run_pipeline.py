#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
import argparse
import time
from pathlib import Path
from datetime import datetime

# Impor aggregator
sys.path.append(str(Path(__file__).parent / "pipeline"))
try:
    from pipeline.aggregator import Aggregator
except ImportError:
    # If standard import fails (e.g. running from root), try relative
    sys.path.append("pipeline")
    from aggregator import Aggregator

# Configuration
SCRIPT_DIR = Path(__file__).parent.absolute()
BENCHMARK_DIR = SCRIPT_DIR / "benchmarks"
PERF_DIR = SCRIPT_DIR / "perf"
PERF_TARGET_DIR = PERF_DIR / "target" / "release"
PERF_RLIB = PERF_TARGET_DIR / "libunsafe_perf.rlib"
PERF_DEPS = PERF_TARGET_DIR / "deps"

# Experiment Definitions
EXPERIMENTS = {
    "cpu_cycle": {
        "feature": "cpu_cycle_counter",
        "output_file": "cpu_cycle.stat",
        "flags": [
            "-C", "unsafe_include_native_lib=false",
            "-C", "llvm-args=-enable-instmarker",
            "-C", "llvm-args=-enable-cpu-cycle-count",
            "-C", "llvm-args=-enable-external-call-tracker",
        ]
    },
    "heap_tracker": {
        "feature": "heap_tracker",
        "output_file": "heap_stat.stat",
        "flags": [
            "-C", "unsafe_include_native_lib=false",
            "-C", "llvm-args=-enable-instmarker",
            "-C", "llvm-args=-enable-heap-tracker",
        ]
    },
    "unsafe_counter": {
        "feature": "unsafe_counter",
        "output_file": "unsafe_counter.stat",
        "flags": [
            "-C", "unsafe_include_native_lib=false",
            "-C", "llvm-args=-enable-instmarker",
            "-C", "llvm-args=-enable-unsafe-function-tracker",
            "-C", "llvm-args=-enable-unsafe-inst-counter",
        ]
    },
    "coverage": {
        "feature": "unsafe_coverage",
        "output_file": "unsafe_coverage.stat",
        "flags": [
            "-C", "unsafe_include_native_lib=false", # Note: false for coverage
            "-C", "llvm-args=-enable-instmarker",
            "-C", "llvm-args=-enable-dynamic-line-count",
        ]
    },
}

# Crate-Specific Configurations
CRATE_CONFIGS = {
    "rayon": {
        "cwd": "rayon-demo",
        "cmds": [
            "cargo build --release",
            "../target/release/rayon-demo nbody bench --bodies 500"
        ]
    },
    "parking_lot": {
        "cwd": "benchmark", # Note: 'benchmark' folder, singular based on ls output
        "cmds": [
            "cargo build --release",
            "./target/release/mutex 2 4 10 2 4",
            "./target/release/rwlock 4 4 4 10 2 4"
        ]
    },
    "memchr": {
        "cwd": "benchmarks", # Run from benchmarks/memchr/benchmarks (engines.toml location)
        "cmds": [
            # 1. Build using cargo (relies on global RUSTUP_TOOLCHAIN=stage1)
            # Need to be in the engine dir for build? No, we can build manually first.
            "cd engines/rust-memchr && cargo clean && cargo build --release",
            
            # 2. Run execution via rebar measure --verify (runs all rust-memchr benchmarks once)
            # rebar expects to be run from dir containing engines.toml, which is 'benchmarks' relative to crate root.
            # But crate root is benchmarks/memchr. 'cwd' above makes us start in benchmarks/memchr/benchmarks.
            f"{os.path.expanduser('~/.cargo/bin/rebar')} measure --verify -e 'rust/memchr/memmem/(oneshot|prebuilt)' -d .",
        ],
        "flags": ["-C", "target-feature=-sse2,-avx2"]
    },
    "jni": {
        "cmds": ["cargo bench --features invocation"]
    },
    "ring": {
        "cmds": ["cargo bench --benches"]
    },
    "rayon-core": { # rayon repo has recursed members? usually we run 'rayon'
        "skip": True # Assuming rayon covers it
    }
}

def run_cmd(cmd, cwd=None, env=None, timeout=None):
    """Run a shell command."""
    print(f"Running: {cmd} (cwd={cwd})")
    try:
        subprocess.run(
            cmd, 
            cwd=cwd, 
            env=env, 
            check=True, 
            shell=True,
            timeout=timeout
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}: {cmd}")
        return False
    except subprocess.TimeoutExpired:
        print(f"Command timed out: {cmd}")
        return False

def build_perf(feature):
    """Build the perf library with the specified feature."""
    print(f"building perf library with feature: {feature}...")
    
    # Ensure RUSTFLAGS is NOT set for this build to avoid circular dependencies/errors
    env = os.environ.copy()
    if "RUSTFLAGS" in env:
        del env["RUSTFLAGS"]

    # Clean first ensures no feature mixing
    run_cmd("cargo clean", cwd=PERF_DIR, env=env) 
    
    cmd = f"cargo build --release --features {feature}"
    if not run_cmd(cmd, cwd=PERF_DIR, env=env):
        print(f"Failed to build perf library for {feature}")
        sys.exit(1)

def run_crate(crate_name, exp_name, config, output_dir):
    """Run experiment for a single crate."""
    print(f"Processing crate: {crate_name} [{exp_name}]")
    
    crate_dir = BENCHMARK_DIR / crate_name
    if not crate_dir.exists():
        # Try finding fuzzy match
        matches = [d for d in BENCHMARK_DIR.iterdir() if d.is_dir() and d.name.startswith(crate_name)]
        if matches:
             crate_dir = matches[0]
             print(f"Found crate directory: {crate_dir.name}")
        else:
             print(f"Crate directory not found: {crate_name}")
             return

    # Check for custom config
    # Matches 'rayon' or 'rayon-1.5.0' -> check if key is in name?
    # Better: check if crate_name (dirname) starts with key
    custom_config = None
    for k, v in CRATE_CONFIGS.items():
        if crate_name == k or crate_name.startswith(k + "-"):
            custom_config = v
            break
            
    if custom_config and custom_config.get("skip"):
        print(f"Skipping {crate_name} as per config.")
        return

    # Prepare environment
    env = os.environ.copy()
    env["RUSTC_BOOTSTRAP"] = "1" # Force nightly features for unstable flags
    env["RUSTUP_TOOLCHAIN"] = "stage1" # Force unified toolchain (1.80.0-dev) that supports unsafe info
    if "RUSTC" in env:
        del env["RUSTC"] # Ensure we use RUSTUP_TOOLCHAIN selection, not shell override
    
    # Calculate relative paths for flags when running inside crate_dir
    
    # Calculate relative paths for flags when running inside crate_dir
    # RUSTFLAGS paths must be relative to the CWD of the cargo process (crate_dir)
    try:
        # PERF_RLIB is typically "perf/target/release/libunsafe_perf.rlib" relative to root
        # crate_dir is "benchmarks/foo" relative to root
        # We need path from benchmarks/foo -> perf/target...
        # Using os.path.relpath(target, start)
        
        # Resolve to absolute first to be safe for calculation, then convert to relative
        abs_crate_dir = crate_dir.resolve()
        abs_perf_rlib = PERF_RLIB.resolve()
        abs_perf_deps = PERF_DEPS.resolve()
        abs_output_dir = output_dir.resolve()
        
        rel_perf_rlib = os.path.relpath(abs_perf_rlib, abs_crate_dir)
        rel_perf_deps = os.path.relpath(abs_perf_deps, abs_crate_dir)
        rel_output_dir = os.path.relpath(abs_output_dir, abs_crate_dir)
        
    except Exception as e:
        print(f"Error calculating relative paths: {e}")
        return

    # Construct RUSTFLAGS with ABSOLUTE paths for build stability
    # Relative paths in RUSTFLAGS fail for dependencies (e.g. libc) as rustc CWD changes or differs
    rustflags = [
        "--emit=llvm-ir,link",
        "-Z", "unstable-options",
        f"--extern", f"force:unsafe_perf={PERF_RLIB}",
        "-L", f"{PERF_DEPS}"
    ]
    rustflags.extend(config["flags"])
    
    env["RUSTFLAGS"] = " ".join(rustflags)
    env["UNSAFE_BENCH_OUTPUT_DIR"] = str(rel_output_dir)
    print(f"DEBUG: UNSAFE_BENCH_OUTPUT_DIR={rel_output_dir} (cwd={crate_dir})")
    
    # Determine execution strategy
    exec_cwd = crate_dir
    cmds = ["cargo bench"] # Default
    
    if custom_config:
        if "cwd" in custom_config:
            exec_cwd = crate_dir / custom_config["cwd"]
            # Re-calculate relative output dir for the NEW cwd
            try:
                abs_exec_cwd = exec_cwd.resolve()
                rel_output_dir_custom = os.path.relpath(abs_output_dir, abs_exec_cwd)
                env["UNSAFE_BENCH_OUTPUT_DIR"] = str(rel_output_dir_custom)
                print(f"DEBUG: Custom CWD UNSAFE_BENCH_OUTPUT_DIR={rel_output_dir_custom}")
            except Exception as e:
                print(f"Error calculating relative path for custom cwd: {e}")
        
        if "cmds" in custom_config:
            cmds = custom_config["cmds"]

    # Execute Commands
    success = True
    for cmd in cmds:
        if not run_cmd(cmd, cwd=exec_cwd, env=env, timeout=600):
            print(f"Command failed: {cmd}")
            success = False
            break # Stop executing subsequent commands (e.g. run after build) if previous failed
            
    if success:
        print(f"Success: {crate_name}")
        
        # Rename output file
        # The runtime writes to output_dir / output_file
        expected_file = output_dir / config["output_file"]
        if expected_file.exists():
            new_name = output_dir / f"{crate_name}_{config['output_file']}"
            shutil.move(expected_file, new_name)
            print(f"Saved results to: {new_name.name}")
        else:
             # It implies no coverage/stats were written.
             # For some crates (like parking_lot), running the binary works.
             # If file not found, maybe it wasn't named as expected?
             # But the runtime always writes to {UNSAFE_BENCH_OUTPUT_DIR}/unsafe_coverage.stat etc.
             print(f"Warning: Expected output file not found: {expected_file}")

def main():
    parser = argparse.ArgumentParser(description="Unsafe Rust Benchmark Pipeline")
    parser.add_argument("--crate", help="Run for specific crate")
    parser.add_argument("--experiment", choices=EXPERIMENTS.keys(), help="Run specific experiment")
    parser.add_argument("--all", action="store_true", help="Run all experiments")
    parser.add_argument("--output", help="Custom output directory")
    
    args = parser.parse_args()
    
    if not args.all and not args.experiment:
        print("Please specify --experiment or --all")
        return

    # Setup Output Directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if args.output:
        base_output_dir = Path(args.output)
    else:
        base_output_dir = SCRIPT_DIR / "results" / timestamp
    
    base_output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Results will be stored in: {base_output_dir}")

    # Determine what to run
    experiments_to_run = []
    if args.all:
        experiments_to_run = list(EXPERIMENTS.keys())
    else:
        experiments_to_run = [args.experiment]

    crates_to_run = []
    if args.crate:
        crates_to_run = [args.crate]
    else:
        # Auto-discover crates
        crates_to_run = [d.name for d in BENCHMARK_DIR.iterdir() if d.is_dir()]

    print(f"Experiments: {experiments_to_run}")
    print(f"Crates: {len(crates_to_run)}")

    # Execution Loop
    for exp in experiments_to_run:
        print(f"\n=== Starting Experiment: {exp} ===")
        config = EXPERIMENTS[exp]
        
        # 1. Build Perf Lib
        build_perf(config["feature"])
        
        # 2. Run Crates
        for crate in crates_to_run:
            # We use the same output dir for all experiments, 
            # the file suffices (e.g. _cpu_cycle.stat) differentiate them.
            # But coverage tracks cumulative runs.
            # Each execute appends.
            
            run_crate(crate, exp, config, base_output_dir)

    # Aggregation
    print("\n=== Aggregating Results ===")
    agg = Aggregator(base_output_dir)
    agg.collect_all()
    agg.print_table()
    
    print(f"\nFull results in: {base_output_dir}")

if __name__ == "__main__":
    main()
