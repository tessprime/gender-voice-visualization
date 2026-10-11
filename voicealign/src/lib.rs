//! Forced alignment of a recording to its transcript, porting what
//! phonealign does through kalpy/Kaldi, for use in the browser
//! (WebAssembly). See README.md.

pub mod features;
pub mod kaldi_io;
