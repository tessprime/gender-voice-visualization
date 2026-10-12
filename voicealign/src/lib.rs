// SPDX-License-Identifier: MIT

//! Forced alignment of a recording to its transcript, porting what
//! phonealign does through kalpy/Kaldi, for use in the browser
//! (WebAssembly). See README.md.
//!
//! ```ignore
//! let aligner = voicealign::Aligner::new(&model, &tree, &lda, &phones, &dictionary)?;
//! let alignment = aligner.align(&samples, 16000, "When the sunlight strikes...")?;
//! for word in &alignment.words { println!("{} {} {}", word.start, word.end, word.label); }
//! ```

pub mod align;
pub mod aligner;
pub mod features;
pub mod graph;
pub mod kaldi_io;
pub mod lexicon;
pub mod model;
pub mod tree;
#[cfg(target_arch = "wasm32")]
pub mod wasm;

pub use aligner::{Aligner, Alignment, Error, Interval};
