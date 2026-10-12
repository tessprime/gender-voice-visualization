// SPDX-License-Identifier: Apache-2.0
// Ported from Kaldi (https://github.com/kaldi-asr/kaldi), Copyright the
// Kaldi authors, Apache License 2.0; translated to Rust and modified. See
// NOTICE.

//! Acoustic features as kalpy computes them for alignment with this model:
//! Kaldi MFCCs, CMVN (mean only), frames spliced ±3, then an LDA transform.
//! Ported from Kaldi (feature-window.cc, mel-computations.cc,
//! feature-mfcc.cc, cmvn.cc, feature-functions.cc).

use crate::kaldi_io::Matrix;
use rustfft::{num_complex::Complex, FftPlanner};
use std::f64::consts::PI;

/// Kaldi MFCC options; `Default` matches the model (`english_us_arpa`),
/// except for dither, which the caller applies.
#[derive(Clone, Debug)]
pub struct MfccOptions {
    pub sample_rate: f64,
    pub frame_shift_ms: f64,
    pub frame_length_ms: f64,
    pub preemphasis: f64,
    pub num_mel_bins: usize,
    pub low_frequency: f64,
    pub high_frequency: f64,
    pub num_ceps: usize,
    pub cepstral_lifter: f64,
}

impl Default for MfccOptions {
    fn default() -> Self {
        MfccOptions {
            sample_rate: 16000.0,
            frame_shift_ms: 10.0,
            frame_length_ms: 25.0,
            preemphasis: 0.97,
            num_mel_bins: 23,
            low_frequency: 20.0,
            high_frequency: 7800.0,
            num_ceps: 13,
            cepstral_lifter: 22.0,
        }
    }
}

fn mel_scale(frequency: f64) -> f64 {
    1127.0 * (1.0 + frequency / 700.0).ln()
}

/// MFCCs of `samples` (on Kaldi's 16-bit scale, i.e. -32768..32767), one row
/// per 10 ms frame. Frames are centred on multiples of the frame shift, with
/// the signal reflected at the edges (Kaldi's `snip_edges = false`).
pub fn mfcc(samples: &[f64], options: &MfccOptions) -> Matrix {
    let shift = (options.sample_rate * 0.001 * options.frame_shift_ms) as i64;
    let length = (options.sample_rate * 0.001 * options.frame_length_ms) as usize;
    let padded = length.next_power_of_two();
    let count = (samples.len() as i64 + shift / 2) / shift;

    // Kaldi's "povey" window: a Hann window raised to the power 0.85.
    let a = 2.0 * PI / (length as f64 - 1.0);
    let window: Vec<f64> = (0..length).map(|i| (0.5 - 0.5 * (a * i as f64).cos()).powf(0.85)).collect();

    let mel_banks = mel_banks(options, padded);
    let num_bins = options.num_mel_bins;
    let dct: Vec<Vec<f64>> = (0..options.num_ceps)
        .map(|k| {
            (0..num_bins)
                .map(|n| {
                    if k == 0 {
                        (1.0 / num_bins as f64).sqrt()
                    } else {
                        (2.0 / num_bins as f64).sqrt() * (PI / num_bins as f64 * (n as f64 + 0.5) * k as f64).cos()
                    }
                })
                .collect()
        })
        .collect();
    let lifter: Vec<f64> = (0..options.num_ceps)
        .map(|i| 1.0 + 0.5 * options.cepstral_lifter * (PI * i as f64 / options.cepstral_lifter).sin())
        .collect();

    let fft = FftPlanner::new().plan_fft_forward(padded);
    let mut buffer = vec![Complex::new(0.0, 0.0); padded];
    let mut data = Vec::with_capacity(count.max(0) as usize * options.num_ceps);
    let n = samples.len() as i64;
    for frame in 0..count {
        let start = frame * shift + shift / 2 - length as i64 / 2;
        let mut values: Vec<f64> = (0..length as i64)
            .map(|s| {
                let mut i = start + s;
                while i < 0 || i >= n {
                    i = if i < 0 { -i - 1 } else { 2 * n - 1 - i };
                }
                samples[i as usize]
            })
            .collect();
        let mean = values.iter().sum::<f64>() / length as f64;
        values.iter_mut().for_each(|v| *v -= mean);
        for i in (1..length).rev() {
            values[i] -= options.preemphasis * values[i - 1];
        }
        values[0] -= options.preemphasis * values[0];

        for (i, slot) in buffer.iter_mut().enumerate() {
            *slot = Complex::new(if i < length { values[i] * window[i] } else { 0.0 }, 0.0);
        }
        fft.process(&mut buffer);
        let power: Vec<f64> = buffer[..padded / 2 + 1].iter().map(|c| c.norm_sqr()).collect();

        let log_energies: Vec<f64> = mel_banks
            .iter()
            .map(|(offset, weights)| {
                let energy: f64 = weights.iter().zip(&power[*offset..]).map(|(w, p)| w * p).sum();
                energy.max(f32::EPSILON as f64).ln()
            })
            .collect();
        for k in 0..options.num_ceps {
            let c: f64 = dct[k].iter().zip(&log_energies).map(|(d, e)| d * e).sum();
            data.push(c * lifter[k]);
        }
    }
    Matrix { rows: count.max(0) as usize, cols: options.num_ceps, data }
}

/// Triangular mel filters over the power spectrum's bins: (first bin,
/// weights) per filter, as Kaldi's MelBanks.
fn mel_banks(options: &MfccOptions, padded: usize) -> Vec<(usize, Vec<f64>)> {
    let num_fft_bins = padded / 2;
    let bin_width = options.sample_rate / padded as f64;
    let (mel_low, mel_high) = (mel_scale(options.low_frequency), mel_scale(options.high_frequency));
    let delta = (mel_high - mel_low) / (options.num_mel_bins as f64 + 1.0);
    (0..options.num_mel_bins)
        .map(|bin| {
            let left = mel_low + bin as f64 * delta;
            let center = mel_low + (bin as f64 + 1.0) * delta;
            let right = mel_low + (bin as f64 + 2.0) * delta;
            let weights: Vec<(usize, f64)> = (0..num_fft_bins)
                .filter_map(|i| {
                    let mel = mel_scale(bin_width * i as f64);
                    if mel > left && mel < right {
                        let weight = if mel <= center { (mel - left) / (center - left) } else { (right - mel) / (right - center) };
                        Some((i, weight))
                    } else {
                        None
                    }
                })
                .collect();
            let first = weights.first().map_or(0, |w| w.0);
            (first, weights.into_iter().map(|w| w.1).collect())
        })
        .collect()
}

/// Subtract each coefficient's mean over all frames (CMVN without variance
/// normalisation, over the whole recording).
pub fn cmvn(features: &mut Matrix) {
    for c in 0..features.cols {
        let mean = (0..features.rows).map(|r| features.data[r * features.cols + c]).sum::<f64>() / features.rows as f64;
        for r in 0..features.rows {
            features.data[r * features.cols + c] -= mean;
        }
    }
}

/// Each frame concatenated with its `context` neighbours on either side
/// (repeating the first and last frames at the edges).
pub fn splice(features: &Matrix, context: usize) -> Matrix {
    let width = features.cols * (2 * context + 1);
    let mut data = Vec::with_capacity(features.rows * width);
    for r in 0..features.rows as i64 {
        for offset in -(context as i64)..=context as i64 {
            let source = (r + offset).clamp(0, features.rows as i64 - 1) as usize;
            data.extend_from_slice(features.row(source));
        }
    }
    Matrix { rows: features.rows, cols: width, data }
}

/// `features` times the transpose of `transform`; with one column more than
/// the features have, its last column is an offset (Kaldi's affine form).
pub fn transform(features: &Matrix, transform: &Matrix) -> Matrix {
    let affine = transform.cols == features.cols + 1;
    assert!(affine || transform.cols == features.cols, "transform doesn't fit the features");
    let mut data = Vec::with_capacity(features.rows * transform.rows);
    for r in 0..features.rows {
        let row = features.row(r);
        for t in 0..transform.rows {
            let weights = transform.row(t);
            let mut value: f64 = row.iter().zip(weights).map(|(x, w)| x * w).sum();
            if affine {
                value += weights[features.cols];
            }
            data.push(value);
        }
    }
    Matrix { rows: features.rows, cols: transform.rows, data }
}

/// The features alignment uses: MFCC, CMVN, splice ±3, LDA.
pub fn alignment_features(samples: &[f64], options: &MfccOptions, lda: &Matrix) -> Matrix {
    let mut features = mfcc(samples, options);
    cmvn(&mut features);
    transform(&splice(&features, 3), lda)
}
