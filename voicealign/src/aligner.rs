// SPDX-License-Identifier: MIT

//! The main entry point: load a model once, then align recordings.

use crate::align::{align, AlignOptions};
use crate::features::{alignment_features, MfccOptions};
use crate::graph::{compile, SilenceSettings};
use crate::kaldi_io::{Matrix, Reader};
use crate::lexicon::{normalize, read_phone_table, Lexicon};
use crate::model::AcousticModel;
use crate::tree::ContextDependency;
use std::collections::HashMap;

#[derive(Clone, Debug, PartialEq)]
pub struct Interval {
    pub start: f64, // seconds
    pub end: f64,
    pub label: String,
}

#[derive(Clone, Debug)]
pub struct Alignment {
    /// The transcript's words (as normalized), in order. Silence isn't
    /// listed: it's the time not covered.
    pub words: Vec<Interval>,
    /// Phones, without silence.
    pub phones: Vec<Interval>,
    pub likelihood: f64,
}

#[derive(Debug)]
pub struct Error(pub String);

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for Error {}

pub struct Aligner {
    model: AcousticModel,
    tree: ContextDependency,
    lda: Matrix,
    phones: HashMap<String, usize>,
    phone_names: HashMap<usize, String>,
    lexicon: Lexicon,
    pub silence: SilenceSettings,
    pub options: AlignOptions,
    /// Standard deviation of the noise added before computing features,
    /// in 16-bit sample units (Kaldi's dither; the model's is 1). Added from
    /// a fixed seed, so results are repeatable. 0 turns it off.
    pub dither: f64,
}

/// A small deterministic Gaussian generator (xorshift64* and Box-Muller),
/// so dither needs no dependencies and gives the same noise everywhere.
struct Noise(u64);

impl Noise {
    fn uniform(&mut self) -> f64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        ((self.0.wrapping_mul(0x2545F4914F6CDD1D) >> 11) as f64 + 0.5) / (1u64 << 53) as f64
    }

    fn gaussian(&mut self) -> f64 {
        (-2.0 * self.uniform().ln()).sqrt() * (2.0 * std::f64::consts::PI * self.uniform()).cos()
    }
}

impl Aligner {
    /// From the contents of an extracted MFA acoustic model's files
    /// (`final.alimdl`, `tree`, `lda.mat`, `phones.txt`) and a pronunciation
    /// dictionary.
    pub fn new(model: &[u8], tree: &[u8], lda: &[u8], phones: &str, dictionary: &str) -> Result<Self, Error> {
        let e = |what: &str, err: crate::kaldi_io::Error| Error(format!("{}: {}", what, err));
        let phones = read_phone_table(phones);
        let phone_names = phones.iter().map(|(name, &id)| (id, name.clone())).collect();
        Ok(Aligner {
            model: AcousticModel::read(model).map_err(|err| e("acoustic model", err))?,
            tree: ContextDependency::read(tree).map_err(|err| e("tree", err))?,
            lda: Reader::new(lda).and_then(|mut r| r.matrix()).map_err(|err| e("LDA matrix", err))?,
            phones,
            phone_names,
            lexicon: Lexicon::parse(dictionary),
            silence: SilenceSettings::default(),
            options: AlignOptions::default(),
            dither: 1.0,
        })
    }

    /// Align `transcript` to 16 kHz mono `samples` (floats in -1..1).
    pub fn align(&self, samples: &[f32], sample_rate: u32, transcript: &str) -> Result<Alignment, Error> {
        if sample_rate != 16000 {
            return Err(Error(format!("expected 16000 Hz audio, got {}", sample_rate)));
        }
        let words = normalize(transcript, &self.lexicon);
        if words.is_empty() {
            return Err(Error("the transcript has no words".into()));
        }
        // On Kaldi's 16-bit scale, rounded as kalpy does, plus dither.
        let mut noise = Noise(0x9E3779B97F4A7C15);
        let scaled: Vec<f64> = samples
            .iter()
            .map(|&s| (s as f64 * 32768.0).round() + if self.dither > 0.0 { self.dither * noise.gaussian() } else { 0.0 })
            .collect();
        let features = alignment_features(&scaled, &MfccOptions::default(), &self.lda);
        if features.rows == 0 {
            return Err(Error("the recording is too short".into()));
        }
        let graph = compile(&words, &self.lexicon, &self.phones, &self.model.transitions, &self.tree, &self.silence)
            .map_err(|e| Error(e.0))?;
        let result = align(&graph, &self.model, &features, &self.options)
            .ok_or_else(|| Error("the recording couldn't be matched to the transcript".into()))?;

        let duration = samples.len() as f64 / sample_rate as f64;
        let interval = |s: &crate::align::Segment, label: String| {
            let (start, end) = s.seconds(duration, features.rows);
            Interval { start, end, label }
        };
        let silence = self.phones.get("sil").copied();
        Ok(Alignment {
            words: result.words.iter().map(|s| interval(s, words[s.label].clone())).collect(),
            phones: result
                .phones
                .iter()
                .filter(|s| Some(s.label) != silence)
                .map(|s| interval(s, self.phone_names.get(&s.label).cloned().unwrap_or_default()))
                .collect(),
            likelihood: result.likelihood,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn noise_is_standard_normal_and_repeatable() {
        let mut a = Noise(1);
        let values: Vec<f64> = (0..100_000).map(|_| a.gaussian()).collect();
        let mean = values.iter().sum::<f64>() / values.len() as f64;
        let var = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / values.len() as f64;
        assert!(mean.abs() < 0.02 && (var - 1.0).abs() < 0.02, "mean {} variance {}", mean, var);
        let mut b = Noise(1);
        assert_eq!(b.gaussian(), values[0]);
    }
}
