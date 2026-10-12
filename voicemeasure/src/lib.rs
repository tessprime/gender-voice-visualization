// SPDX-License-Identifier: MIT

//! Pitch and formant analysis producing the same numbers as Praat's
//! `To Pitch` and `To Formant (burg)`, implemented from Praat's published
//! documentation (not its source). See README.md.
//!
//! Sounds are mono sample arrays. Like Praat, sample `i` of a sound with
//! sampling period `dt` sits at time `(i + 0.5) * dt`.

pub mod formant;
pub mod frames;
pub mod measure;
pub mod pitch;
pub mod resample;
#[cfg(target_arch = "wasm32")]
pub mod wasm;

pub use formant::{to_formant_burg, Formant, FormantFrame, FormantSettings};
pub use measure::{formant_at, measure_at, pitch_at, Measurement};
pub use pitch::{to_pitch, PitchFrame, PitchSettings};
