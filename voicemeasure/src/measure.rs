// SPDX-License-Identifier: MIT

//! Values at arbitrary times, as Praat's `Get value at time ... Hertz Linear`
//! gives them, and the measurement the web app makes at each phone's
//! midpoint (textgrid-formants.praat).

use crate::formant::{to_formant_burg, FormantFrame, FormantSettings};
use crate::pitch::{to_pitch, PitchFrame, PitchSettings};

/// Linear interpolation between the frames on either side of `time`; if one
/// of them has no value, the nearer frame's value (None if that one has
/// none either). Outside the first and last frames, None.
///
/// The fallback reproduces Praat 6.4.06's pitch values at all 266 phone
/// midpoints of the test recording; plain "both or nothing" matched 261.
/// No test-recording phone exercised it for formants.
fn value_at<T>(times: &[f64], frames: &[T], time: f64, get: impl Fn(&T) -> Option<f64>) -> Option<f64> {
    let after = times.partition_point(|&t| t <= time);
    if after == 0 || after >= times.len() {
        return None;
    }
    let before = after - 1;
    let weight = (time - times[before]) / (times[after] - times[before]);
    match (get(&frames[before]), get(&frames[after])) {
        (Some(a), Some(b)) => Some(a + weight * (b - a)),
        (a, b) => if weight < 0.5 { a } else { b },
    }
}

/// F0 at `time`, or None where unvoiced.
pub fn pitch_at(frames: &[PitchFrame], time: f64) -> Option<f64> {
    let times: Vec<f64> = frames.iter().map(|f| f.time).collect();
    value_at(&times, frames, time, |f| f.frequency)
}

/// Formant `number` (1 = F1) at `time`.
pub fn formant_at(frames: &[FormantFrame], time: f64, number: usize) -> Option<f64> {
    let times: Vec<f64> = frames.iter().map(|f| f.time).collect();
    value_at(&times, frames, time, |f| f.formants.get(number - 1).map(|x| x.frequency))
}

/// F0 and F1-F3 at one moment; None where undefined.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Measurement {
    pub f0: Option<f64>,
    pub f1: Option<f64>,
    pub f2: Option<f64>,
    pub f3: Option<f64>,
}

/// What textgrid-formants.praat measures: F0 (`To Pitch: 0, 75, 600`) and
/// F1-F3 (`To Formant (burg): 0, 5, 5000, 0.025, 50`) at each of `times`,
/// typically phone midpoints.
pub fn measure_at(samples: &[f64], rate: f64, times: &[f64]) -> Vec<Measurement> {
    let pitch = to_pitch(samples, rate, &PitchSettings::default());
    let formants = to_formant_burg(samples, rate, &FormantSettings::default());
    let pitch_times: Vec<f64> = pitch.iter().map(|f| f.time).collect();
    let formant_times: Vec<f64> = formants.iter().map(|f| f.time).collect();
    let formant = |time: f64, number: usize| {
        value_at(&formant_times, &formants, time, |f| f.formants.get(number - 1).map(|x| x.frequency))
    };
    times
        .iter()
        .map(|&time| Measurement {
            f0: value_at(&pitch_times, &pitch, time, |f| f.frequency),
            f1: formant(time, 1),
            f2: formant(time, 2),
            f3: formant(time, 3),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn interpolates_and_falls_back_to_the_nearer_frame() {
        let times = [0.0, 0.01, 0.02];
        let values = [Some(100.0), Some(200.0), None];
        let at = |t| value_at(&times, &values, t, |v| *v);
        assert_eq!(at(0.005), Some(150.0));
        assert_eq!(at(0.012), Some(200.0)); // nearer to the voiced frame
        assert_eq!(at(0.018), None); // nearer to the unvoiced frame
        assert_eq!(at(-0.001), None);
        assert_eq!(at(0.03), None);
    }
}
