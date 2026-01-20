#!/usr/bin/env python3
import os
import re
import math
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class CrateStats:
    name: str
    # CPU Cycle
    cpu_unsafe_pct: float = 0.0
    # Heap
    heap_total_usage: int = 0
    heap_unsafe_usage: int = 0
    heap_unsafe_pct: float = 0.0
    # Unsafe Counter
    inst_total: int = 0
    inst_unsafe: int = 0
    inst_unsafe_pct: float = 0.0
    
    loads_unsafe: int = 0
    stores_unsafe: int = 0
    calls_unsafe_inst: int = 0
    
    func_total: int = 0
    func_unsafe: int = 0
    func_unsafe_pct: float = 0.0
    
    calls_total_dyn: int = 0
    calls_unsafe_dyn: int = 0
    calls_unsafe_dyn_pct: float = 0.0
    
    # Coverage
    cov_registered: int = 0
    cov_executed: int = 0
    cov_pct: float = 0.0
    
    # Time (placeholder, would need external timing)
    time_sec: float = 0.0
    
    # SLOC (placeholder, needs static analysis or hardcoded)
    sloc: str = "-"

class Aggregator:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.stats: Dict[str, CrateStats] = {}

    def get_crate(self, name: str) -> CrateStats:
        if name not in self.stats:
            self.stats[name] = CrateStats(name=name)
        return self.stats[name]

    def parse_cpu_stats(self):
        """Parses *_cpu_cycle.stat files"""
        for f in self.output_dir.glob("*_cpu_cycle.stat"):
            crate = f.stem.replace("_cpu_cycle", "")
            stats = self.get_crate(crate)
            try:
                content = f.read_text()
                # Extract using Simple Regex or Split
                # "Unsafe percentage: 12.34"
                m = re.search(r"Unsafe percentage:\s*([\d\.]+)", content)
                if m:
                    stats.cpu_unsafe_pct = float(m.group(1))
            except Exception as e:
                print(f"Error parsing CPU stats for {crate}: {e}")

    def parse_heap_stats(self):
        """Parses *_heap_stat.stat files"""
        for f in self.output_dir.glob("*_heap_stat.stat"):
            crate = f.stem.replace("_heap_stat", "")
            stats = self.get_crate(crate)
            try:
                content = f.read_text()
                # Aggregate multiple runs if present (file appended)
                # We'll take the SUM of all blocks? Or the LAST one?
                # Heap tracker appends. The aggregator usually sums.
                # Let's sum totals.
                
                total_usage = 0
                unsafe_mem = 0
                
                blocks = content.split("===== Heap Usage Statistics =====")
                for block in blocks:
                    if not block.strip(): continue
                    
                    tu = re.search(r"Total heap usage:\s*(\d+)", block)
                    um = re.search(r"Unsafe heap memory:\s*(\d+)", block)
                    
                    if tu: total_usage += int(tu.group(1))
                    if um: unsafe_mem += int(um.group(1))
                
                stats.heap_total_usage = total_usage
                stats.heap_unsafe_usage = unsafe_mem
                if total_usage > 0:
                    stats.heap_unsafe_pct = (unsafe_mem / total_usage) * 100.0
            except Exception as e:
                print(f"Error parsing Heap stats for {crate}: {e}")

    def parse_unsafe_counter_stats(self):
        """Parses *_unsafe_counter.stat files"""
        for f in self.output_dir.glob("*_unsafe_counter.stat"):
            crate = f.stem.replace("_unsafe_counter", "")
            stats = self.get_crate(crate)
            try:
                content = f.read_text()
                # Summing logic for appended runs
                
                total_inst = 0
                unsafe_inst = 0
                loads = 0
                stores = 0
                calls = 0
                total_func = 0
                unsafe_func = 0
                calls_dyn = 0
                calls_unsafe_dyn = 0
                
                # Simple line-based summing
                for line in content.splitlines():
                    if ":" not in line: continue
                    k, v = line.split(":", 1)
                    val = int(v.replace(",", "").strip())
                    
                    if "Total instructions" in k: total_inst += val
                    elif "Unsafe instructions" in k: unsafe_inst += val
                    elif "Unsafe loads" in k: loads += val
                    elif "Unsafe stores" in k: stores += val
                    elif "Unsafe calls" in k: calls += val # instruction calls?
                    elif "Unique functions" in k: total_func = max(total_func, val) # Max for unique? Or sum? unique is per run. use max.
                    elif "Unique unsafe functions" in k: unsafe_func = max(unsafe_func, val)
                    elif "Total function calls" in k: calls_dyn += val
                    elif "Unsafe function calls" in k: calls_unsafe_dyn += val

                stats.inst_total = total_inst
                stats.inst_unsafe = unsafe_inst
                if total_inst > 0:
                    stats.inst_unsafe_pct = (unsafe_inst / total_inst) * 100.0
                
                stats.loads_unsafe = loads
                stats.stores_unsafe = stores
                stats.calls_unsafe_inst = calls

                stats.func_total = total_func
                stats.func_unsafe = unsafe_func
                if total_func > 0:
                    stats.func_unsafe_pct = (unsafe_func / total_func) * 100.0

                stats.calls_total_dyn = calls_dyn
                stats.calls_unsafe_dyn = calls_unsafe_dyn
                if calls_dyn > 0:
                    stats.calls_unsafe_dyn_pct = (calls_unsafe_dyn / calls_dyn) * 100.0

            except Exception as e:
                print(f"Error parsing Counter stats for {crate}: {e}")

    def parse_coverage_stats(self):
        """Parses *_unsafe_coverage.stat files"""
        for f in self.output_dir.glob("*_unsafe_coverage.stat"):
            crate = f.stem.replace("_unsafe_coverage", "")
            stats = self.get_crate(crate)
            try:
                content = f.read_text()
                
                # Parse all RUN blocks
                # We want to identify distinct runs and filter out those with 0 execution
                # But keep runs if they are the ONLY runs? 
                # Heuristic: If we have multiple runs, discard the ones with 0 execution.
                
                runs = []
                current_run = {'reg': set(), 'exec': set()}
                current_section = None
                
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("=== RUN_"):
                        # Save previous run if it has data (or at least existed)
                        # We only save if we processed a run.
                        # Actually we can just start a new run object.
                        # But we need to handle the first one.
                        # Let's collect them all first.
                        runs.append({'reg': set(), 'exec': set()})
                        current_run = runs[-1]
                        current_section = None
                    elif line == "=== REGISTERED_LINES ===":
                        current_section = "reg"
                    elif line == "=== EXECUTED_LINES ===":
                        current_section = "exec"
                    elif line.startswith("==="):
                        current_section = None
                    elif line and current_section == "reg" and "reg" in current_run: # Check runs not empty
                        current_run['reg'].add(line)
                    elif line and current_section == "exec" and "exec" in current_run:
                        current_run['exec'].add(line)
                
                # Filter runs
                # If a run has 0 executed lines, but >0 registered lines, it might be a ghost run.
                # However, if ALL runs have 0 executed lines, we keep them (0% coverage).
                
                valid_runs = []
                runs_with_execution = [r for r in runs if len(r['exec']) > 0]
                
                if runs_with_execution:
                    valid_runs = runs_with_execution
                    # print(f"Filtered {len(runs) - len(valid_runs)} ghost runs for {crate}")
                else:
                    valid_runs = runs
                
                # Aggregate/Union
                final_registered = set()
                final_executed = set()
                
                for r in valid_runs:
                    final_registered.update(r['reg'])
                    final_executed.update(r['exec'])
                        
                stats.cov_registered = len(final_registered)
                stats.cov_executed = len(final_executed)
                if stats.cov_registered > 0:
                    stats.cov_pct = (len(final_executed) / len(final_registered)) * 100.0
                    
            except Exception as e:
                print(f"Error parsing Coverage stats for {crate}: {e}")

    def collect_all(self):
        self.parse_cpu_stats()
        self.parse_heap_stats()
        self.parse_unsafe_counter_stats()
        self.parse_coverage_stats()

    def print_table(self):
        print("\n" + "="*145)
        print(f"{'Benchmark':<15} | {'CPU %':<8} | {'Heap %':<8} | {'U.Load':<8} | {'U.Store':<8} | {'U.Call %':<8} | {'U.Inst %':<8} | {'Fn %':<8} | {'Cov %':<8}")
        print("-" * 145)
        
        for name, s in sorted(self.stats.items()):
            # CPU
            cpu_str = f"{s.cpu_unsafe_pct:.2f}%"
            
            # Heap
            heap_str = f"{s.heap_unsafe_pct:.2f}%"
            
            # Unsafe Loads/Stores -> Raw count for now? Or inferred % ?
            # User wants match with LaTeX. LaTeX has percentages.
            # Assuming Load % of Total Inst is useless. 
            # I will print Pct of Unsafe Inst for columns that don't have totals? 
            # Or Raw counts. Let's print Raw counts for Load/Store but Pct for Calls/Inst.
            # Actually, let's print formatted string to keep options open
            
            load_str = f"{s.loads_unsafe}"
            store_str = f"{s.stores_unsafe}"
            
            # Unsafe Calls -> Dynamic % (unsafe calls / total calls)
            call_str = f"{s.calls_unsafe_dyn_pct:.2f}%"
            
            # Unsafe Inst -> % of total
            inst_str = f"{s.inst_unsafe_pct:.2f}%"
            
            # Func % -> Unique Unsafe Fn / Total Unique Fn
            fn_str = f"{s.func_unsafe_pct:.2f}%"
            
            # Coverage
            cov_str = f"{s.cov_pct:.2f}%"
            
            print(f"{name:<15} | {cpu_str:<8} | {heap_str:<8} | {load_str:<8} | {store_str:<8} | {call_str:<8} | {inst_str:<8} | {fn_str:<8} | {cov_str:<8}")
        
        print("="*145 + "\n")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        d = Path(sys.argv[1])
    else:
        d = Path("results") 
    
    agg = Aggregator(d)
    agg.collect_all()
    agg.print_table()
