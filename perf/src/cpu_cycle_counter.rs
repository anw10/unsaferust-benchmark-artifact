//! Runtime library for CPU cycle tracking.
//!
//! This version uses a simplified state model for tracking CPU cycles:
//! - Total cycles: Entire program execution
//! - Unsafe cycles: Time spent in unsafe blocks
//! - External cycles: Time spent in external calls from safe code only
//!
//! Calculation: unsafe / (total - external) gives the percentage of internal
//! execution that is unsafe.

use ctor::dtor;
use lazy_static::lazy_static;
use std::cell::Cell;
use std::ffi::c_void;
use std::os::raw::{c_char, c_int};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use crate::write_output;

const MAX_THREADS: usize = 4096;

#[derive(Debug, Clone, Copy, PartialEq)]
#[repr(usize)]
enum ThreadState {
    Uninitialized,
    Active,
    Terminated,
}

#[repr(C, align(64))] // Cache-line aligned to prevent false sharing
struct ThreadStats {
    thread_id: AtomicU64,
    state: AtomicUsize, // Stores ThreadState as usize
    start_tsc: AtomicU64,

    // Three cycle counters
    total_cycles: AtomicU64,     // Total program execution
    unsafe_cycles: AtomicU64,    // Time in unsafe blocks
    external_cycles: AtomicU64,  // External calls from safe code only

    // Block counts
    unsafe_blocks: AtomicU64,
    external_calls: AtomicU64,

    _padding: [u64; 2],
}

impl ThreadStats {
    const fn new() -> Self {
        Self {
            thread_id: AtomicU64::new(0),
            state: AtomicUsize::new(ThreadState::Uninitialized as usize),
            start_tsc: AtomicU64::new(0),
            total_cycles: AtomicU64::new(0),
            unsafe_cycles: AtomicU64::new(0),
            external_cycles: AtomicU64::new(0),
            unsafe_blocks: AtomicU64::new(0),
            external_calls: AtomicU64::new(0),
            _padding: [0; 2],
        }
    }
}

struct ThreadRegistry {
    threads: [ThreadStats; MAX_THREADS],
    next_slot: AtomicUsize,
    stats_written: AtomicBool,
}

impl ThreadRegistry {
    const fn new() -> Self {
        Self {
            threads: [const { ThreadStats::new() }; MAX_THREADS],
            next_slot: AtomicUsize::new(0),
            stats_written: AtomicBool::new(false),
        }
    }

    fn allocate_slot(&self) -> Option<usize> {
        // First, try to reuse a terminated thread slot
        let current_slots = self.next_slot.load(Ordering::Acquire);
        for slot in 0..current_slots.min(MAX_THREADS) {
            let stats = &self.threads[slot];
            let current_state = stats.state.load(Ordering::Acquire);

            // Try to atomically change from Terminated to Uninitialized for reuse
            if current_state == ThreadState::Terminated as usize {
                let swap_result = stats.state.compare_exchange(
                    ThreadState::Terminated as usize,
                    ThreadState::Uninitialized as usize,
                    Ordering::AcqRel,
                    Ordering::Acquire
                );

                if swap_result.is_ok() {
                    // Successfully claimed a terminated slot for reuse, reset its statistics
                    stats.thread_id.store(0, Ordering::Relaxed);
                    stats.start_tsc.store(0, Ordering::Relaxed);
                    stats.total_cycles.store(0, Ordering::Relaxed);
                    stats.unsafe_cycles.store(0, Ordering::Relaxed);
                    stats.external_cycles.store(0, Ordering::Relaxed);
                    stats.unsafe_blocks.store(0, Ordering::Relaxed);
                    stats.external_calls.store(0, Ordering::Relaxed);
                    return Some(slot);
                }
            }
        }

        // No terminated slots available, try to allocate a new one
        let slot = self.next_slot.fetch_add(1, Ordering::Relaxed);
        if slot < MAX_THREADS {
            Some(slot)
        } else {
            self.next_slot.fetch_sub(1, Ordering::Relaxed);
            None
        }
    }
}

static REGISTRY: ThreadRegistry = ThreadRegistry::new();

// Simple thread-local state tracking
thread_local! {
    static THREAD_SLOT: Cell<Option<usize>> = Cell::new(None);
    static IN_UNSAFE: Cell<u32> = Cell::new(0);
    static IN_EXTERNAL: Cell<u32> = Cell::new(0);
}

#[inline(always)]
fn read_tsc() -> u64 {
    #[cfg(target_arch = "x86_64")]
    unsafe {
        core::arch::x86_64::_rdtsc()
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos() as u64
    }
}

/// Initializes tracking for the current thread, allocating a slot in the registry.
fn initialize_thread() -> Option<usize> {
    THREAD_SLOT.with(|slot_cell| {
        if let Some(slot) = slot_cell.get() {
            return Some(slot);
        }

        if let Some(slot) = REGISTRY.allocate_slot() {
            let tsc = read_tsc();
            let stats = &REGISTRY.threads[slot];
            stats.thread_id.store(get_thread_id(), Ordering::Relaxed);
            stats.start_tsc.store(tsc, Ordering::Release);
            stats.state.store(ThreadState::Active as usize, Ordering::Release);

            // Initialize state
            IN_UNSAFE.with(|in_unsafe| in_unsafe.set(0));
            IN_EXTERNAL.with(|in_external| in_external.set(0));

            slot_cell.set(Some(slot));
            Some(slot)
        } else {
            eprintln!("[Runtime] Error: Maximum number of threads ({}) exceeded.", MAX_THREADS);
            None
        }
    })
}

fn get_thread_id() -> u64 {
    #[cfg(target_family = "unix")]
    {
        unsafe { libc::pthread_self() as u64 }
    }
    #[cfg(not(target_family = "unix"))]
    {
        // This is not a stable ID but is a reasonable fallback.
        std::thread::current().id().as_u64().get()
    }
}

/// Marks the current thread as terminated and records its final cycles.
fn thread_cleanup() {
    if let Some(slot) = THREAD_SLOT.with(|s| s.get()) {
        if slot < MAX_THREADS {
            let final_tsc = read_tsc();
            let stats = &REGISTRY.threads[slot];

            // Calculate total cycles for this thread
            let start_tsc = stats.start_tsc.load(Ordering::Acquire);
            if final_tsc > start_tsc {
                let total = final_tsc - start_tsc;
                stats.total_cycles.store(total, Ordering::Release);
            }

            stats.state.store(ThreadState::Terminated as usize, Ordering::Release);
        }
    }
}

// ==========================================================================================
// === C ABI Functions for LLVM Pass
// ==========================================================================================

#[no_mangle]
pub extern "C" fn record_program_start() {
    initialize_thread();
}

#[no_mangle]
#[inline(always)]
pub extern "C" fn cpu_cycle_start_measurement() -> u64 {
    // Don't track unsafe cycles if we're inside an external call
    // (symmetric with external_call_start which skips if in_unsafe)
    let in_external = IN_EXTERNAL.with(|depth| depth.get());
    if in_external > 0 {
        return 0; // Skip, this will be counted as external time
    }

    // Increment depth counter and check if we were already in an unsafe block
    let was_nested = IN_UNSAFE.with(|depth| {
        let current = depth.get();
        depth.set(current + 1);
        current > 0  // true if we were already in an unsafe block
    });

    if was_nested {
        return 0; // Skip nested unsafe blocks
    }

    // Only reach here for the outermost unsafe block
    let slot = match THREAD_SLOT.with(|s| s.get()).or_else(initialize_thread) {
        Some(slot) => slot,
        None => return 0,
    };

    let stats = &REGISTRY.threads[slot];
    stats.unsafe_blocks.fetch_add(1, Ordering::Relaxed);

    read_tsc()
}

#[no_mangle]
#[inline(always)]
pub extern "C" fn cpu_cycle_end_measurement(start_tsc: u64) {
    // Decrement depth counter and check if we're exiting the outermost unsafe block
    let is_outermost = IN_UNSAFE.with(|depth| {
        let current = depth.get();
        if current > 0 {
            depth.set(current - 1);
            current == 1  // true if we're exiting the outermost unsafe block (1 -> 0)
        } else {
            false
        }
    });

    if start_tsc == 0 || !is_outermost {
        return; // Was nested, in external, or not initialized
    }

    let slot = match THREAD_SLOT.with(|s| s.get()) {
        Some(slot) => slot,
        None => return,
    };

    let end_tsc = read_tsc();
    if end_tsc > start_tsc {
        let cycles = end_tsc - start_tsc;
        let stats = &REGISTRY.threads[slot];
        stats.unsafe_cycles.fetch_add(cycles, Ordering::Relaxed);
    }
}

#[no_mangle]
#[inline(always)]
pub extern "C" fn external_call_start() -> u64 {
    // Only track external calls from safe code
    let in_unsafe = IN_UNSAFE.with(|depth| depth.get());
    if in_unsafe > 0 {
        return 0; // Skip, this is part of unsafe time
    }

    // Increment depth counter and check if we were already in an external call
    let was_nested = IN_EXTERNAL.with(|depth| {
        let current = depth.get();
        depth.set(current + 1);
        current > 0  // true if we were already in an external call
    });

    if was_nested {
        return 0; // Skip nested external calls
    }

    // Only reach here for the outermost external call
    let slot = match THREAD_SLOT.with(|s| s.get()).or_else(initialize_thread) {
        Some(slot) => slot,
        None => return 0,
    };

    let stats = &REGISTRY.threads[slot];
    stats.external_calls.fetch_add(1, Ordering::Relaxed);

    read_tsc()
}

#[no_mangle]
#[inline(always)]
pub extern "C" fn external_call_end(start_tsc: u64) {
    // Decrement depth counter and check if we're exiting the outermost call
    let is_outermost = IN_EXTERNAL.with(|depth| {
        let current = depth.get();
        if current > 0 {
            depth.set(current - 1);
            current == 1  // true if we're exiting the outermost call (1 -> 0)
        } else {
            false
        }
    });

    if start_tsc == 0 || !is_outermost {
        return; // Was nested, in unsafe, or not initialized
    }

    let slot = match THREAD_SLOT.with(|s| s.get()) {
        Some(slot) => slot,
        None => return,
    };

    let end_tsc = read_tsc();
    if end_tsc > start_tsc {
        let cycles = end_tsc - start_tsc;
        let stats = &REGISTRY.threads[slot];
        stats.external_cycles.fetch_add(cycles, Ordering::Relaxed);
    }
}

// ==========================================================================================
// === Automatic Thread Lifecycle Management via pthread_create Interposition
// ==========================================================================================

type ThreadStartRoutine = extern "C" fn(*mut c_void) -> *mut c_void;

struct ThreadInfo {
    routine: ThreadStartRoutine,
    arg: *mut c_void,
}

extern "C" fn thread_start_wrapper(arg: *mut c_void) -> *mut c_void {
    // Automatic initialization
    initialize_thread();
    let info = unsafe { Box::from_raw(arg as *mut ThreadInfo) };
    let result = (info.routine)(info.arg);
    // Automatic cleanup
    thread_cleanup();
    result
}

type PthreadCreateFn = extern "C" fn(*mut libc::pthread_t, *const libc::pthread_attr_t, ThreadStartRoutine, *mut c_void) -> c_int;

lazy_static! {
    static ref REAL_PTHREAD_CREATE: Option<PthreadCreateFn> = {
        unsafe {
            // Try to find pthread_create using RTLD_NEXT first
            let symbol = libc::dlsym(libc::RTLD_NEXT, "pthread_create\0".as_ptr() as *const c_char);

            if !symbol.is_null() {
                Some(std::mem::transmute(symbol))
            } else {
                // If RTLD_NEXT fails, we'll disable interposition
                eprintln!("[Runtime] Warning: pthread_create interposition disabled - could not find symbol");
                None
            }
        }
    };
}

#[no_mangle]
pub extern "C" fn pthread_create(thread: *mut libc::pthread_t, attr: *const libc::pthread_attr_t, start_routine: ThreadStartRoutine, arg: *mut c_void) -> c_int {
    if let Some(real_pthread_create) = *REAL_PTHREAD_CREATE {
        let info = Box::new(ThreadInfo { routine: start_routine, arg });
        let info_ptr = Box::into_raw(info) as *mut c_void;
        real_pthread_create(thread, attr, thread_start_wrapper, info_ptr)
    } else {
        // Fallback: if interposition is disabled, return an error
        eprintln!("[Runtime] Warning: pthread_create called but interposition is disabled - returning error");
        libc::ENOSYS
    }
}

// ==========================================================================================
// === Statistics Reporting
// ==========================================================================================

#[no_mangle]
pub extern "C" fn print_cpu_cycle_stats() {
    // Use compare_exchange for exactly-once execution.
    if REGISTRY.stats_written.compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst).is_ok() {
        dump_stats();
    }
}

/// This function is registered to run when the program exits.
#[dtor]
fn final_cleanup() {
    print_cpu_cycle_stats();
}

fn calculate_total_stats() -> (u64, u64, u64, u64, u64) {
    let mut total_cycles = 0;
    let mut total_unsafe = 0;
    let mut total_external = 0;
    let mut total_unsafe_blocks = 0;
    let mut total_external_calls = 0;

    let max_slot = REGISTRY.next_slot.load(Ordering::Acquire);
    for slot in 0..max_slot.min(MAX_THREADS) {
        let stats = &REGISTRY.threads[slot];

        // Read state first
        let state = stats.state.load(Ordering::Acquire);
        if state == ThreadState::Uninitialized as usize {
            continue;
        }

        // Read all values atomically to get a consistent snapshot
        let thread_unsafe = stats.unsafe_cycles.load(Ordering::Acquire);
        let thread_external = stats.external_cycles.load(Ordering::Acquire);
        let thread_unsafe_blocks = stats.unsafe_blocks.load(Ordering::Acquire);
        let thread_external_calls = stats.external_calls.load(Ordering::Acquire);

        // For active threads, calculate total cycles dynamically
        // For terminated threads, use the stored value
        let thread_total = if state == ThreadState::Active as usize {
            let current_tsc = read_tsc();
            let start_tsc = stats.start_tsc.load(Ordering::Acquire);
            if current_tsc > start_tsc {
                current_tsc - start_tsc
            } else {
                0
            }
        } else {
            stats.total_cycles.load(Ordering::Acquire)
        };

        // Validate consistency: skip thread if data is inconsistent
        // (can happen if thread terminated between reading state and total)
        if thread_unsafe > thread_total || thread_external > thread_total {
            eprintln!("[Runtime] Warning: Inconsistent thread data detected (slot {}), skipping", slot);
            continue;
        }

        total_cycles += thread_total;
        total_unsafe += thread_unsafe;
        total_external += thread_external;
        total_unsafe_blocks += thread_unsafe_blocks;
        total_external_calls += thread_external_calls;
    }

    (total_cycles, total_unsafe, total_external, total_unsafe_blocks, total_external_calls)
}

fn dump_stats() {
    let (total_cycles, unsafe_cycles, external_cycles, unsafe_blocks, external_calls) = calculate_total_stats();

    // Calculate internal cycles (excluding external calls from safe code)
    let internal_cycles = if total_cycles > external_cycles {
        total_cycles - external_cycles
    } else {
        total_cycles
    };

    // Validate that unsafe_cycles doesn't exceed internal_cycles
    // With the fixed tracking logic (nesting depth counters), this should never happen
    if unsafe_cycles > internal_cycles && internal_cycles > 0 {
        eprintln!("[Runtime] WARNING: unsafe_cycles ({}) > internal_cycles ({})", unsafe_cycles, internal_cycles);
        eprintln!("  This suggests potential measurement issues (e.g., TSC inconsistency or race conditions)");
    }

    // Calculate percentage of internal execution that is unsafe
    let unsafe_percentage = if internal_cycles > 0 {
        (unsafe_cycles as f64 / internal_cycles as f64) * 100.0
    } else {
        0.0
    };

    // Create structured output for script parsing
    let output = format!(
        concat!(
            "\n===== CPU Cycle Statistics =====\n",
            "Total cycles: {}\n",
            "Unsafe cycles: {}\n",
            "External cycles: {}\n",
            "Internal cycles: {}\n",
            "Unsafe percentage: {:.2}\n",
            "Unsafe blocks: {}\n",
            "External calls: {}\n",
        ),
        total_cycles, unsafe_cycles, external_cycles, internal_cycles, unsafe_percentage,
        unsafe_blocks, external_calls
    );

    // Write structured output to file for script parsing
    let _ = write_output(&output, "cpu_cycle.stat");
}
