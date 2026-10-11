//! Resampling as Praat's `Sound: Resample` describes it: when lowering the
//! rate, first remove everything above the new Nyquist frequency in the
//! frequency domain, then compute the new samples by windowed sinc
//! interpolation.

use rustfft::{num_complex::Complex, FftPlanner};
use std::f64::consts::PI;

/// Samples on each side of the interpolated point (Praat's "precision").
const SINC_DEPTH: usize = 50;

/// Resample `samples` from `rate` to `new_rate` Hz. The result covers the
/// same duration, with its samples centred in it.
pub fn resample(samples: &[f64], rate: f64, new_rate: f64) -> Vec<f64> {
    if samples.is_empty() || rate == new_rate {
        return samples.to_vec();
    }
    let filtered;
    let source = if new_rate < rate {
        filtered = low_pass(samples, rate, 0.5 * new_rate);
        &filtered[..]
    } else {
        samples
    };

    let duration = samples.len() as f64 / rate;
    let count = (duration * new_rate).round() as usize;
    let first_time = 0.5 * (duration - (count as f64 - 1.0) / new_rate);
    (0..count)
        .map(|i| {
            // Position in the source, in samples (sample j is at (j + 0.5) / rate).
            let position = (first_time + i as f64 / new_rate) * rate - 0.5;
            interpolate_sinc(source, position)
        })
        .collect()
}

/// Zero every frequency component above `cutoff` Hz.
fn low_pass(samples: &[f64], rate: f64, cutoff: f64) -> Vec<f64> {
    // Pad so the circular FFT doesn't wrap the end of the sound onto its start.
    let size = (2 * samples.len()).next_power_of_two();
    let mut spectrum: Vec<Complex<f64>> = samples
        .iter()
        .map(|&x| Complex::new(x, 0.0))
        .chain(std::iter::repeat(Complex::new(0.0, 0.0)))
        .take(size)
        .collect();
    let mut planner = FftPlanner::new();
    planner.plan_fft_forward(size).process(&mut spectrum);
    for (k, value) in spectrum.iter_mut().enumerate() {
        let bin = k.min(size - k); // negative frequencies mirror positive ones
        if bin as f64 * rate / size as f64 > cutoff {
            *value = Complex::new(0.0, 0.0);
        }
    }
    planner.plan_fft_inverse(size).process(&mut spectrum);
    spectrum[..samples.len()].iter().map(|c| c.re / size as f64).collect()
}

/// The value at fractional sample `position`, by sinc interpolation with a
/// raised-cosine window `SINC_DEPTH` samples to each side.
fn interpolate_sinc(samples: &[f64], position: f64) -> f64 {
    let centre = position.floor() as i64;
    let mut sum = 0.0;
    for j in (centre - SINC_DEPTH as i64 + 1)..=(centre + SINC_DEPTH as i64) {
        if j < 0 || j >= samples.len() as i64 {
            continue;
        }
        let distance = position - j as f64;
        let sinc = if distance.abs() < 1e-12 {
            1.0
        } else {
            (PI * distance).sin() / (PI * distance)
        };
        let window = 0.5 + 0.5 * (PI * distance / (SINC_DEPTH as f64 + 0.5)).cos();
        sum += samples[j as usize] * sinc * window;
    }
    sum
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keeps_a_low_tone_and_duration() {
        let rate = 16000.0;
        let tone: Vec<f64> = (0..16000)
            .map(|i| (2.0 * PI * 440.0 * (i as f64 + 0.5) / rate).sin())
            .collect();
        let out = resample(&tone, rate, 10000.0);
        assert_eq!(out.len(), 10000);
        // Away from the edges, samples match the tone at their new times.
        for i in 1000..9000 {
            let expected = (2.0 * PI * 440.0 * (i as f64 + 0.5) / 10000.0).sin();
            assert!((out[i] - expected).abs() < 1e-3, "sample {}: {} vs {}", i, out[i], expected);
        }
    }

    #[test]
    fn removes_a_tone_above_the_new_nyquist() {
        let rate = 16000.0;
        let tone: Vec<f64> = (0..16000)
            .map(|i| (2.0 * PI * 6000.0 * (i as f64 + 0.5) / rate).sin())
            .collect();
        let out = resample(&tone, rate, 10000.0);
        let peak = out[1000..9000].iter().fold(0.0f64, |m, x| m.max(x.abs()));
        assert!(peak < 1e-3, "6 kHz tone survived resampling to 10 kHz: peak {}", peak);
    }
}
