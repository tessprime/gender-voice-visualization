//! Placement of analysis frames, as Praat does for short-term analyses: as
//! many frames as fit, spaced `time_step` apart, centred in the sound.

/// Times of the frame centres for a sound of `duration` seconds analysed
/// with windows `window_length` long, `time_step` apart.
pub fn frame_times(duration: f64, window_length: f64, time_step: f64) -> Vec<f64> {
    if duration < window_length {
        return Vec::new();
    }
    // A small tolerance so an exact fit isn't lost to rounding.
    let count = ((duration - window_length) / time_step + 1e-9).floor() as usize + 1;
    let first = 0.5 * (duration - (count - 1) as f64 * time_step);
    (0..count).map(|i| first + i as f64 * time_step).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_praat_frame_layout() {
        // From Praat 6.4.06 on a 26.378688 s recording.
        let formant = frame_times(26.378688, 0.05, 0.00625);
        assert_eq!(formant.len(), 4213);
        assert!((formant[0] - 0.026844).abs() < 1e-6);
        let pitch = frame_times(26.378688, 0.04, 0.01);
        assert_eq!(pitch.len(), 2634);
        assert!((pitch[0] - 0.024344).abs() < 1e-6);
    }
}
