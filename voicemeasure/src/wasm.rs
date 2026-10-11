//! A minimal C-style interface for WebAssembly, needing no bindings
//! generator. From JavaScript:
//!
//! 1. `vm_alloc(n)` returns a pointer to space for `n` f64 values; copy the
//!    samples (and, separately, the times) into the module's memory there.
//! 2. `vm_measure(samples, sample_count, rate, times, time_count, out)` writes
//!    4 values per time to `out` (allocated for `4 * time_count` values):
//!    F0, F1, F2, F3, with NaN where undefined.
//! 3. `vm_free(pointer, n)` releases what `vm_alloc` returned.

use crate::measure::measure_at;

#[no_mangle]
pub extern "C" fn vm_alloc(count: usize) -> *mut f64 {
    let mut buffer = Vec::<f64>::with_capacity(count);
    let pointer = buffer.as_mut_ptr();
    std::mem::forget(buffer);
    pointer
}

/// # Safety
/// `pointer` must come from `vm_alloc(count)` and not have been freed.
#[no_mangle]
pub unsafe extern "C" fn vm_free(pointer: *mut f64, count: usize) {
    drop(Vec::from_raw_parts(pointer, 0, count));
}

/// For timing one stage at a time: 0 = resample to 10 kHz, 1 = formants
/// (including resampling), 2 = pitch. Returns the number of output values.
///
/// # Safety
/// `samples` must be a `vm_alloc` allocation of `sample_count` values.
#[no_mangle]
pub unsafe extern "C" fn vm_stage(samples: *const f64, sample_count: usize, rate: f64, stage: u32) -> usize {
    use crate::{resample::resample, to_formant_burg, to_pitch, FormantSettings, PitchSettings};
    let samples = std::slice::from_raw_parts(samples, sample_count);
    match stage {
        0 => resample(samples, rate, 10000.0).len(),
        1 => to_formant_burg(samples, rate, &FormantSettings::default()).len(),
        _ => to_pitch(samples, rate, &PitchSettings::default()).len(),
    }
}

/// # Safety
/// The pointers must be `vm_alloc` allocations of at least `sample_count`,
/// `time_count` and `4 * time_count` values, the first two filled in.
#[no_mangle]
pub unsafe extern "C" fn vm_measure(
    samples: *const f64,
    sample_count: usize,
    rate: f64,
    times: *const f64,
    time_count: usize,
    out: *mut f64,
) {
    let samples = std::slice::from_raw_parts(samples, sample_count);
    let times = std::slice::from_raw_parts(times, time_count);
    let out = std::slice::from_raw_parts_mut(out, 4 * time_count);
    for (i, m) in measure_at(samples, rate, times).iter().enumerate() {
        for (j, value) in [m.f0, m.f1, m.f2, m.f3].iter().enumerate() {
            out[4 * i + j] = value.unwrap_or(f64::NAN);
        }
    }
}
