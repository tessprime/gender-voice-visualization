//! Pitch analysis by autocorrelation, as described in Boersma (1993),
//! "Accurate short-term analysis of the fundamental frequency and the
//! harmonics-to-noise ratio of a sampled sound", and Praat's manual for
//! `Sound: To Pitch (ac)...`:
//!
//! 1. For each frame (3 periods of the pitch floor long), subtract the local
//!    mean, apply a Hanning window and compute the normalized autocorrelation
//!    r_a. Divide by the window's own autocorrelation r_w, which removes the
//!    window's tapering effect: r_x = r_a / r_w.
//! 2. Candidates: the maxima of r_x for periods between 1 / ceiling and
//!    1 / floor, refined by interpolation. Strength:
//!    r - octave cost * log2(floor * period). Plus an unvoiced candidate of
//!    strength voicing threshold + max(0, 2 - (local peak / global peak) /
//!    (silence threshold / (1 + voicing threshold))).
//! 3. Choose one candidate per frame by maximizing the total strength minus
//!    transition costs (Viterbi): voiced/unvoiced cost for switching
//!    between voiced and unvoiced, octave-jump cost * |log2(f1 / f2)|
//!    between voiced frames.

use crate::frames::frame_times;
use rustfft::{num_complex::Complex, FftPlanner};
use std::f64::consts::PI;

/// Settings; `Default` gives what textgrid-formants.praat uses
/// (`To Pitch: 0, 75, 600`, i.e. `To Pitch (ac)` with Praat's defaults).
#[derive(Clone, Debug)]
pub struct PitchSettings {
    /// Seconds between frames; 0 means 0.75 / pitch floor.
    pub time_step: f64,
    pub floor: f64,
    pub ceiling: f64,
    pub max_candidates: usize,
    pub silence_threshold: f64,
    pub voicing_threshold: f64,
    pub octave_cost: f64,
    pub octave_jump_cost: f64,
    pub voiced_unvoiced_cost: f64,
}

impl Default for PitchSettings {
    fn default() -> Self {
        PitchSettings {
            time_step: 0.0,
            floor: 75.0,
            ceiling: 600.0,
            max_candidates: 15,
            silence_threshold: 0.03,
            voicing_threshold: 0.45,
            octave_cost: 0.01,
            octave_jump_cost: 0.35,
            voiced_unvoiced_cost: 0.14,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct PitchFrame {
    pub time: f64,
    /// Fundamental frequency in Hz, or None where unvoiced.
    pub frequency: Option<f64>,
}

#[derive(Clone, Copy, Debug)]
struct Candidate {
    /// Hz; 0 for the unvoiced candidate.
    frequency: f64,
    strength: f64,
}

/// Pitch analysis of a mono sound sampled at `rate` Hz.
pub fn to_pitch(samples: &[f64], rate: f64, settings: &PitchSettings) -> Vec<PitchFrame> {
    let duration = samples.len() as f64 / rate;
    let window_length = 3.0 / settings.floor;
    let time_step = if settings.time_step > 0.0 { settings.time_step } else { 0.75 / settings.floor };
    let times = frame_times(duration, window_length, time_step);

    let window_samples = (window_length * rate).floor() as usize;
    let window: Vec<f64> = (0..window_samples)
        .map(|i| 0.5 - 0.5 * (2.0 * PI * (i as f64 + 1.0) / (window_samples as f64 + 1.0)).cos())
        .collect();
    let fft_size = (window_samples + window_samples / 2 + 1).next_power_of_two();
    let mut planner = FftPlanner::new();
    let forward = planner.plan_fft_forward(fft_size);
    let inverse = planner.plan_fft_inverse(fft_size);
    let autocorrelate = |values: &[f64]| -> Vec<f64> {
        let mut buffer: Vec<Complex<f64>> = values
            .iter()
            .map(|&v| Complex::new(v, 0.0))
            .chain(std::iter::repeat(Complex::new(0.0, 0.0)))
            .take(fft_size)
            .collect();
        forward.process(&mut buffer);
        for value in buffer.iter_mut() {
            *value = Complex::new(value.norm_sqr(), 0.0);
        }
        inverse.process(&mut buffer);
        let zero = buffer[0].re;
        buffer.iter().map(|c| if zero > 0.0 { c.re / zero } else { 0.0 }).collect()
    };
    let window_autocorrelation = autocorrelate(&window);

    let global_peak = samples.iter().fold(0.0f64, |m, x| m.max(x.abs()));
    let min_lag = rate / settings.ceiling;
    let max_lag = (rate / settings.floor).min(window_samples as f64 / 2.0);

    let candidates: Vec<Vec<Candidate>> = times
        .iter()
        .map(|&time| {
            // Sample i is at (i + 0.5) / rate; the window spans
            // centre - N/2 + 1 ..= centre + N/2, as for formants.
            let centre = (time * rate - 0.5).round() as i64;
            let start = centre - (window_samples / 2) as i64 + 1;
            let frame: Vec<f64> = (0..window_samples)
                .map(|i| {
                    let j = start + i as i64;
                    if j >= 0 && (j as usize) < samples.len() { samples[j as usize] } else { 0.0 }
                })
                .collect();
            let mean = frame.iter().sum::<f64>() / frame.len() as f64;
            // The local peak is measured after windowing. Not documented, but
            // it matches Praat 6.4.06's voicing decisions far better than the
            // raw frame's peak (99.1% vs 96.0% of frames on the test clip).
            let local_peak = frame.iter().zip(&window).fold(0.0f64, |m, (x, w)| m.max(((x - mean) * w).abs()));

            let unvoiced_strength = settings.voicing_threshold
                + (2.0
                    - (local_peak / global_peak)
                        / (settings.silence_threshold / (1.0 + settings.voicing_threshold)))
                    .max(0.0);
            let mut frame_candidates = vec![Candidate { frequency: 0.0, strength: unvoiced_strength }];

            if local_peak > 0.0 {
                let windowed: Vec<f64> = frame.iter().zip(&window).map(|(x, w)| (x - mean) * w).collect();
                let r_a = autocorrelate(&windowed);
                let r = |lag: usize| r_a[lag] / window_autocorrelation[lag];
                let mut voiced = Vec::new();
                let first = min_lag.floor().max(1.0) as usize;
                let last = max_lag.floor() as usize;
                for lag in first.max(1)..last {
                    let (previous, here, next) = (r(lag - 1), r(lag), r(lag + 1));
                    if here > 0.0 && here > previous && here >= next {
                        // Parabolic interpolation of the peak.
                        let curvature = previous - 2.0 * here + next;
                        let shift = if curvature != 0.0 { 0.5 * (previous - next) / curvature } else { 0.0 };
                        let peak_lag = lag as f64 + shift;
                        let height = here - 0.25 * (previous - next) * shift;
                        if peak_lag < min_lag || peak_lag > max_lag {
                            continue;
                        }
                        voiced.push(Candidate {
                            frequency: rate / peak_lag,
                            strength: height
                                - settings.octave_cost * (settings.floor * peak_lag / rate).log2(),
                        });
                    }
                }
                voiced.sort_by(|a, b| b.strength.partial_cmp(&a.strength).unwrap());
                voiced.truncate(settings.max_candidates - 1);
                frame_candidates.extend(voiced);
            }
            frame_candidates
        })
        .collect();

    let path = best_path(&candidates, settings, time_step);
    times
        .iter()
        .zip(path)
        .map(|(&time, candidate)| PitchFrame {
            time,
            frequency: if candidate.frequency > 0.0 { Some(candidate.frequency) } else { None },
        })
        .collect()
}

/// The sequence of candidates (one per frame) with the highest total
/// strength minus transition costs.
fn best_path(candidates: &[Vec<Candidate>], settings: &PitchSettings, time_step: f64) -> Vec<Candidate> {
    if candidates.is_empty() {
        return Vec::new();
    }
    // Costs are defined per 10 ms.
    let scale = 0.01 / time_step;
    let transition = |a: &Candidate, b: &Candidate| -> f64 {
        match (a.frequency > 0.0, b.frequency > 0.0) {
            (false, false) => 0.0,
            (true, true) => settings.octave_jump_cost * (a.frequency / b.frequency).log2().abs() * scale,
            _ => settings.voiced_unvoiced_cost * scale,
        }
    };
    let mut score: Vec<f64> = candidates[0].iter().map(|c| c.strength).collect();
    let mut back: Vec<Vec<usize>> = vec![vec![0; candidates[0].len()]];
    for frame in 1..candidates.len() {
        let mut new_score = Vec::with_capacity(candidates[frame].len());
        let mut pointers = Vec::with_capacity(candidates[frame].len());
        for b in &candidates[frame] {
            let (best, value) = candidates[frame - 1]
                .iter()
                .enumerate()
                .map(|(i, a)| (i, score[i] - transition(a, b)))
                .max_by(|x, y| x.1.partial_cmp(&y.1).unwrap())
                .unwrap();
            new_score.push(value + b.strength);
            pointers.push(best);
        }
        score = new_score;
        back.push(pointers);
    }
    let mut index = (0..score.len()).max_by(|&a, &b| score[a].partial_cmp(&score[b]).unwrap()).unwrap();
    let mut path = vec![candidates[0][0]; candidates.len()];
    for frame in (0..candidates.len()).rev() {
        path[frame] = candidates[frame][index];
        index = back[frame][index];
    }
    path
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tone(frequency: f64, rate: f64, seconds: f64) -> Vec<f64> {
        (0..(rate * seconds) as usize)
            .map(|i| {
                let t = (i as f64 + 0.5) / rate;
                // A few harmonics, like a voice.
                (2.0 * PI * frequency * t).sin() + 0.5 * (4.0 * PI * frequency * t).sin()
                    + 0.25 * (6.0 * PI * frequency * t).sin()
            })
            .collect()
    }

    #[test]
    fn finds_the_pitch_of_a_harmonic_tone() {
        for frequency in [90.0, 150.0, 220.0, 400.0] {
            let frames = to_pitch(&tone(frequency, 16000.0, 1.0), 16000.0, &PitchSettings::default());
            let middle = &frames[frames.len() / 2];
            let found = middle.frequency.expect("tone should be voiced");
            assert!((found - frequency).abs() < 0.5, "{} Hz tone found as {} Hz", frequency, found);
        }
    }

    #[test]
    fn silence_is_unvoiced() {
        let mut sound = tone(150.0, 16000.0, 1.0);
        sound.extend(std::iter::repeat(0.0).take(16000));
        let frames = to_pitch(&sound, 16000.0, &PitchSettings::default());
        assert!(frames.last().unwrap().frequency.is_none());
        assert!(frames[frames.len() / 4].frequency.is_some());
    }
}
