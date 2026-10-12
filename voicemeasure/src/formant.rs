// SPDX-License-Identifier: MIT

//! Formant analysis as described in Praat's manual for
//! `Sound: To Formant (burg)...`:
//!
//! 1. Resample to twice the maximum formant frequency.
//! 2. Pre-emphasise: x[i] -= a * x[i - 1], a = exp(-2 pi F dt), F being the
//!    pre-emphasis frequency.
//! 3. For each frame, apply a Gaussian-like window twice the nominal window
//!    length, and compute LPC coefficients by Burg's method (Press et al.,
//!    Numerical Recipes), with twice as many poles as formants.
//! 4. The roots of the LPC polynomial give the formants' frequencies and
//!    bandwidths. Formants below 50 Hz or above the maximum minus 50 Hz are
//!    dropped.

use crate::frames::frame_times;
use crate::resample::resample;
use rustfft::num_complex::Complex;
use std::f64::consts::PI;

/// Analysis settings; `Default` gives the ones textgrid-formants.praat uses:
/// `To Formant (burg): 0, 5, 5000, 0.025, 50`.
#[derive(Clone, Debug)]
pub struct FormantSettings {
    /// Seconds between frames; 0 means a quarter of the window length.
    pub time_step: f64,
    pub max_formants: f64,
    pub max_formant_hz: f64,
    /// The nominal (effective) window length; the window used is twice this.
    pub window_length: f64,
    pub pre_emphasis_from_hz: f64,
}

impl Default for FormantSettings {
    fn default() -> Self {
        FormantSettings {
            time_step: 0.0,
            max_formants: 5.0,
            max_formant_hz: 5000.0,
            window_length: 0.025,
            pre_emphasis_from_hz: 50.0,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Formant {
    pub frequency: f64,
    pub bandwidth: f64,
}

#[derive(Clone, Debug)]
pub struct FormantFrame {
    pub time: f64,
    /// In order of frequency.
    pub formants: Vec<Formant>,
}

/// Formant analysis of a mono sound sampled at `rate` Hz.
pub fn to_formant_burg(samples: &[f64], rate: f64, settings: &FormantSettings) -> Vec<FormantFrame> {
    let duration = samples.len() as f64 / rate;
    let new_rate = 2.0 * settings.max_formant_hz;
    let mut sound = resample(samples, rate, new_rate);
    // The resampled sound's samples are centred in its duration.
    let first_sample_time = 0.5 * (duration - (sound.len() as f64 - 1.0) / new_rate);

    let alpha = (-2.0 * PI * settings.pre_emphasis_from_hz / new_rate).exp();
    for i in (1..sound.len()).rev() {
        sound[i] -= alpha * sound[i - 1];
    }

    let window_length = 2.0 * settings.window_length;
    let time_step = if settings.time_step > 0.0 {
        settings.time_step
    } else {
        settings.window_length / 4.0
    };
    let window_samples = (window_length * new_rate).floor() as usize;
    let window = gaussian_window(window_samples);
    let poles = (2.0 * settings.max_formants).round() as usize;

    frame_times(duration, window_length, time_step)
        .into_iter()
        .map(|time| {
            // The window spans samples centre - N/2 + 1 ..= centre + N/2.
            // Chosen empirically: of the placements tried (offsets -1..2,
            // rounding or flooring the centre), this one matches Praat
            // 6.4.06 best (see docs/CURRENT.md).
            let centre = ((time - first_sample_time) * new_rate).round() as i64;
            let start = centre - (window_samples / 2) as i64 + 1;
            let frame: Vec<f64> = (0..window_samples)
                .map(|i| {
                    let j = start + i as i64;
                    if j >= 0 && (j as usize) < sound.len() {
                        sound[j as usize] * window[i]
                    } else {
                        0.0
                    }
                })
                .collect();
            FormantFrame {
                time,
                formants: formants_of_frame(&frame, poles, new_rate, settings.max_formant_hz),
            }
        })
        .collect()
}

/// Praat's Gaussian-like window: a Gaussian that falls to exp(-12) at the
/// window's edges, shifted and scaled to be exactly 0 there.
fn gaussian_window(length: usize) -> Vec<f64> {
    let edge = (-12.0f64).exp();
    let middle = 0.5 * (length as f64 + 1.0);
    (1..=length)
        .map(|i| {
            let x = (i as f64 - middle) / (length as f64 + 1.0);
            ((-48.0 * x * x).exp() - edge) / (1.0 - edge)
        })
        .collect()
}

fn formants_of_frame(frame: &[f64], poles: usize, rate: f64, max_formant_hz: f64) -> Vec<Formant> {
    let coefficients = match burg(frame, poles) {
        Some(coefficients) => coefficients,
        None => return Vec::new(), // silent frame
    };
    // x[t] ~ sum d[k] x[t - k]  =>  roots of z^m - d[1] z^(m-1) - ... - d[m].
    let mut polynomial = vec![1.0];
    polynomial.extend(coefficients.iter().map(|d| -d));
    let mut formants: Vec<Formant> = polynomial_roots(&polynomial)
        .into_iter()
        .filter(|root| root.im > 0.0)
        .map(|root| Formant {
            frequency: root.arg() * rate / (2.0 * PI),
            bandwidth: -root.norm().ln() * rate / PI,
        })
        .filter(|f| f.frequency >= 50.0 && f.frequency <= max_formant_hz - 50.0)
        .collect();
    formants.sort_by(|a, b| a.frequency.partial_cmp(&b.frequency).unwrap());
    formants
}

/// Burg's method (Numerical Recipes' `memcof`): `order` coefficients d such
/// that x[t] is predicted as sum over k of d[k] x[t - k]. None for a silent
/// frame.
fn burg(x: &[f64], order: usize) -> Option<Vec<f64>> {
    let n = x.len();
    if n <= order || x.iter().all(|&v| v == 0.0) {
        return None;
    }
    let mut forward: Vec<f64> = x[..n - 1].to_vec();
    let mut backward: Vec<f64> = x[1..].to_vec();
    let mut d = vec![0.0; order];
    let mut previous = vec![0.0; order];
    for k in 0..order {
        let (mut numerator, mut denominator) = (0.0, 0.0);
        for j in 0..n - 1 - k {
            numerator += forward[j] * backward[j];
            denominator += forward[j] * forward[j] + backward[j] * backward[j];
        }
        if denominator == 0.0 {
            return None;
        }
        d[k] = 2.0 * numerator / denominator;
        for i in 0..k {
            d[i] = previous[i] - d[k] * previous[k - 1 - i];
        }
        if k == order - 1 {
            break;
        }
        previous[..=k].copy_from_slice(&d[..=k]);
        for j in 0..n - 2 - k {
            forward[j] -= previous[k] * backward[j];
            backward[j] = backward[j + 1] - previous[k] * forward[j + 1];
        }
    }
    Some(d)
}

/// All complex roots of the polynomial with real coefficients
/// `c[0] z^n + c[1] z^(n-1) + ... + c[n]`, by the Aberth-Ehrlich method
/// followed by Newton polishing. (Durand-Kerner, used at first, often never
/// met its stopping criterion when roots were clustered, as for clean
/// synthetic signals, making analysis ~8 times slower.)
fn polynomial_roots(c: &[f64]) -> Vec<Complex<f64>> {
    let degree = c.len() - 1;
    let monic: Vec<Complex<f64>> = c.iter().map(|&v| Complex::new(v / c[0], 0.0)).collect();
    let evaluate = |z: Complex<f64>| monic.iter().fold(Complex::new(0.0, 0.0), |acc, &a| acc * z + a);
    let derivative = |z: Complex<f64>| {
        monic[..degree]
            .iter()
            .enumerate()
            .fold(Complex::new(0.0, 0.0), |acc, (i, &a)| acc * z + a * (degree - i) as f64)
    };

    // Starting points spread around a circle inside the unit circle, where
    // LPC roots lie.
    let mut roots: Vec<Complex<f64>> = (0..degree)
        .map(|k| Complex::from_polar(0.9, 2.0 * PI * (k as f64 + 0.25) / degree as f64))
        .collect();
    for _ in 0..100 {
        let mut largest_step = 0.0f64;
        for i in 0..degree {
            let slope = derivative(roots[i]);
            if slope.norm() == 0.0 {
                continue;
            }
            let newton = evaluate(roots[i]) / slope;
            let repulsion: Complex<f64> = (0..degree)
                .filter(|&j| j != i)
                .map(|j| Complex::new(1.0, 0.0) / (roots[i] - roots[j]))
                .sum();
            let step = newton / (Complex::new(1.0, 0.0) - newton * repulsion);
            roots[i] -= step;
            largest_step = largest_step.max(step.norm());
        }
        // Not tighter: clustered roots jitter at the rounding level and
        // would never stop. Newton polishing below refines each root further.
        if largest_step < 1e-12 {
            break;
        }
    }
    for root in roots.iter_mut() {
        for _ in 0..3 {
            let slope = derivative(*root);
            if slope.norm() == 0.0 {
                break;
            }
            *root -= evaluate(*root) / slope;
        }
    }
    roots
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_roots_of_a_known_polynomial() {
        // (z - 0.5)(z^2 - 2 * 0.9 cos(1) z + 0.81): roots 0.5 and 0.9 e^(+-i).
        let a = 2.0 * 0.9 * 1.0f64.cos();
        let c = [1.0, -(a + 0.5), 0.81 + 0.5 * a, -0.405];
        let mut roots = polynomial_roots(&c);
        roots.sort_by(|x, y| x.im.partial_cmp(&y.im).unwrap());
        assert!((roots[1] - Complex::new(0.5, 0.0)).norm() < 1e-10);
        assert!((roots[2] - Complex::from_polar(0.9, 1.0)).norm() < 1e-10);
    }

    #[test]
    fn finds_the_resonance_of_a_two_pole_filter() {
        // White-ish noise through a resonator at 1000 Hz, sampled at 10 kHz.
        let rate = 10000.0;
        let (r, theta) = (0.97f64, 2.0 * PI * 1000.0 / rate);
        let (a1, a2) = (2.0 * r * theta.cos(), -r * r);
        let mut seed = 12345u64;
        let mut noise = || {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            (seed >> 11) as f64 / (1u64 << 53) as f64 - 0.5
        };
        let mut y = vec![0.0; 2000];
        for t in 2..y.len() {
            y[t] = noise() + a1 * y[t - 1] + a2 * y[t - 2];
        }
        let formants = formants_of_frame(&y, 2, rate, 5000.0);
        assert_eq!(formants.len(), 1);
        assert!((formants[0].frequency - 1000.0).abs() < 20.0, "{:?}", formants);
    }
}
