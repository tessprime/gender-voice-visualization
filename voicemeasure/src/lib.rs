//! Pitch and formant analysis producing the same numbers as Praat's
//! `To Pitch` and `To Formant (burg)`, implemented from Praat's published
//! documentation (not its source). See README.md.
//!
//! Sounds are mono sample arrays. Like Praat, sample `i` of a sound with
//! sampling period `dt` sits at time `(i + 0.5) * dt`.

pub mod formant;
pub mod frames;
pub mod resample;

pub use formant::{to_formant_burg, Formant, FormantFrame, FormantSettings};
