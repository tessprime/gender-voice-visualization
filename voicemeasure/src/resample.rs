// SPDX-License-Identifier: MIT

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
    // Position in the source, in samples (sample j is at (j + 0.5) / rate).
    let position = |i: usize| (first_time + i as f64 / new_rate) * rate - 0.5;

    // Output i and output i + period sit at the same fraction of a source
    // sample (for 16 -> 10 kHz, period 5), so the sinc weights only need
    // computing once per phase.
    let ratio = rate / new_rate;
    let period = (1..=1000).find(|&m| {
        let steps = m as f64 * ratio;
        (steps - steps.round()).abs() < 1e-9
    });
    let period = match period {
        Some(period) if period < count => period,
        _ => return (0..count).map(|i| interpolate_sinc(source, position(i))).collect(),
    };
    let step = (period as f64 * ratio).round() as i64; // source samples per period
    let kernels: Vec<(i64, Vec<f64>)> = (0..period)
        .map(|phase| {
            let p = position(phase);
            let first = p.floor() as i64 - SINC_DEPTH as i64 + 1;
            (first, sinc_weights(p - first as f64))
        })
        .collect();
    (0..count)
        .map(|i| {
            let (first, weights) = &kernels[i % period];
            let first = first + (i / period) as i64 * step;
            if first >= 0 && first + weights.len() as i64 <= source.len() as i64 {
                let window = &source[first as usize..first as usize + weights.len()];
                window.iter().zip(weights).map(|(x, w)| x * w).sum()
            } else {
                // Near the ends some taps fall outside the sound.
                weights
                    .iter()
                    .enumerate()
                    .filter_map(|(k, w)| source.get(usize::try_from(first + k as i64).ok()?).map(|x| x * w))
                    .sum()
            }
        })
        .collect()
}

/// The 2 * SINC_DEPTH windowed-sinc weights for taps at distances
/// `first_distance`, `first_distance - 1`, ... from the interpolated point.
fn sinc_weights(first_distance: f64) -> Vec<f64> {
    (0..2 * SINC_DEPTH)
        .map(|k| {
            let distance = first_distance - k as f64;
            // From the fractional part, for precision near whole samples.
            let reduced = distance - distance.round();
            let sinc = if distance.abs() < 1e-12 {
                1.0
            } else {
                (PI * reduced).sin() * if distance.round() as i64 % 2 == 0 { 1.0 } else { -1.0 } / (PI * distance)
            };
            sinc * (0.5 + 0.5 * (PI * distance / (SINC_DEPTH as f64 + 0.5)).cos())
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
    let first = centre - SINC_DEPTH as i64 + 1;
    // Successive taps are one sample apart, so instead of two trig calls per
    // tap: sin(pi (d - k)) = (-1)^k sin(pi d), and the window's cosine is
    // advanced by rotating (cos, sin) of its angle by a fixed step.
    let first_distance = position - first as f64;
    // sin(pi d) from d's fractional part: d itself is up to SINC_DEPTH, and
    // when it's within ~1e-10 of a whole number (common: 16 -> 10 kHz puts
    // every fifth output on an input sample), sin(pi d) computed directly
    // keeps too little relative precision for sin(pi d) / (pi d).
    let nearest = first_distance.round();
    let mut sin_pi_distance =
        (PI * (first_distance - nearest)).sin() * if nearest as i64 % 2 == 0 { 1.0 } else { -1.0 };
    let step = PI / (SINC_DEPTH as f64 + 0.5);
    let (step_cos, step_sin) = (step.cos(), step.sin());
    let (mut angle_cos, mut angle_sin) = ((step * first_distance).cos(), (step * first_distance).sin());
    let mut sum = 0.0;
    for k in 0..2 * SINC_DEPTH as i64 {
        let j = first + k;
        if j >= 0 && j < samples.len() as i64 {
            let distance = first_distance - k as f64;
            let sinc = if distance.abs() < 1e-12 { 1.0 } else { sin_pi_distance / (PI * distance) };
            sum += samples[j as usize] * sinc * (0.5 + 0.5 * angle_cos);
        }
        sin_pi_distance = -sin_pi_distance;
        let rotated_cos = angle_cos * step_cos + angle_sin * step_sin; // angle - step
        angle_sin = angle_sin * step_cos - angle_cos * step_sin;
        angle_cos = rotated_cos;
    }
    sum
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The straightforward version: two trig calls per tap.
    fn interpolate_sinc_direct(samples: &[f64], position: f64) -> f64 {
        let centre = position.floor() as i64;
        let mut sum = 0.0;
        for j in (centre - SINC_DEPTH as i64 + 1)..=(centre + SINC_DEPTH as i64) {
            if j < 0 || j >= samples.len() as i64 {
                continue;
            }
            let distance = position - j as f64;
            let sinc = if distance.abs() < 1e-12 { 1.0 } else { (PI * distance).sin() / (PI * distance) };
            let window = 0.5 + 0.5 * (PI * distance / (SINC_DEPTH as f64 + 0.5)).cos();
            sum += samples[j as usize] * sinc * window;
        }
        sum
    }

    #[test]
    fn fast_interpolation_matches_the_direct_formula() {
        let samples: Vec<f64> = (0..1000).map(|i| ((i * 7919) % 1000) as f64 / 500.0 - 1.0).collect();
        let mut largest: f64 = 0.0;
        // Arbitrary positions, and positions a hair from whole samples (as
        // when resampling 16 -> 10 kHz), where precision is easiest to lose.
        let positions = (0..2000)
            .map(|i| i as f64 * 0.4999 - 3.0)
            .chain((0..900).map(|i| (i + 50) as f64 + [3e-11, -3e-11, 0.0][i % 3]));
        for position in positions {
            largest = largest.max((interpolate_sinc(&samples, position) - interpolate_sinc_direct(&samples, position)).abs());
        }
        assert!(largest < 1e-9, "largest difference {}", largest);
    }

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
