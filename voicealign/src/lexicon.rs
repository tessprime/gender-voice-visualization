//! Pronunciation dictionaries in MFA's format, and phone symbol tables.
//!
//! A dictionary line is a word, up to four probabilities, then phones:
//! pronunciation probability, probability of silence after the word, and
//! correction factors for silence and for no silence before it. Parsed as
//! kalpy's `parse_dictionary_file` does.

use std::collections::HashMap;

#[derive(Clone, Debug, PartialEq)]
pub struct Pronunciation {
    pub word: String,
    pub phones: Vec<String>,
    pub probability: Option<f64>,
    pub silence_after_probability: Option<f64>,
    pub silence_before_correction: Option<f64>,
    pub non_silence_before_correction: Option<f64>,
}

/// Pronunciations by word (lowercase), in file order.
#[derive(Clone, Debug, Default)]
pub struct Lexicon {
    pub pronunciations: HashMap<String, Vec<Pronunciation>>,
}

/// kalpy only treats a column as a probability if it looks like `\d+\.\d+`.
fn probability(text: &str) -> Option<f64> {
    let (whole, fraction) = text.split_once('.')?;
    if whole.is_empty() || fraction.is_empty() || !whole.bytes().chain(fraction.bytes()).all(|b| b.is_ascii_digit()) {
        return None;
    }
    text.parse().ok()
}

impl Lexicon {
    pub fn parse(text: &str) -> Lexicon {
        let mut lexicon = Lexicon::default();
        for line in text.lines() {
            let mut fields: Vec<&str> = line.split_whitespace().collect();
            if fields.len() < 2 {
                continue;
            }
            let word = fields.remove(0).to_lowercase();
            let mut values = [None; 4];
            for value in values.iter_mut() {
                match fields.first().and_then(|f| probability(f)) {
                    Some(v) if fields.len() > 1 => {
                        *value = Some(v);
                        fields.remove(0);
                    }
                    _ => break,
                }
            }
            let pronunciation = Pronunciation {
                word: word.clone(),
                phones: fields.iter().map(|s| s.to_string()).collect(),
                probability: values[0],
                silence_after_probability: values[1],
                silence_before_correction: values[2],
                non_silence_before_correction: values[3],
            };
            let entries = lexicon.pronunciations.entry(word).or_default();
            if !entries.iter().any(|p| p.phones == pronunciation.phones) {
                entries.push(pronunciation);
            }
        }
        lexicon
    }
}

/// Split a transcript into the words to align, as MFA's SimpleTokenizer
/// does for these models: lowercase, punctuation removed, apostrophes and
/// hyphens kept inside words. A word the lexicon doesn't have is split at
/// hyphens (compounds), then into stem + clitic ("arthur's" -> "arthur",
/// "'s"); words still unknown are kept as they are.
pub fn normalize(transcript: &str, lexicon: &Lexicon) -> Vec<String> {
    let known = |w: &str| lexicon.pronunciations.contains_key(w);
    let mut words = Vec::new();
    // MFA treats the typographic apostrophe as an apostrophe.
    let transcript = transcript.to_lowercase().replace('\u{2019}', "'");
    for token in transcript.split(|c: char| !(c.is_alphanumeric() || c == '\'' || c == '-')) {
        let token = token.trim_matches('-');
        // Keep a leading apostrophe only for a known clitic such as "'s".
        let token = if known(token) { token } else { token.trim_matches('\'') };
        if token.is_empty() {
            continue;
        }
        if known(token) {
            words.push(token.to_string());
            continue;
        }
        for part in token.split('-').filter(|p| !p.is_empty()) {
            match part.find('\'') {
                Some(i) if !known(part) && known(&part[i..]) && i > 0 => {
                    words.push(part[..i].to_string());
                    words.push(part[i..].to_string());
                }
                _ => words.push(part.to_string()),
            }
        }
    }
    words
}

/// Phone names to ids, from a Kaldi `phones.txt` ("name id" per line).
pub fn read_phone_table(text: &str) -> HashMap<String, usize> {
    text.lines()
        .filter_map(|line| {
            let mut parts = line.split_whitespace();
            Some((parts.next()?.to_string(), parts.next()?.parse().ok()?))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_probabilities_and_phones() {
        let lexicon = Lexicon::parse("'d\t0.99\t0.34\t0.62\t1.14\tD\nthe\t0.99\t0.16\tDH AH0\nA\tAH0\nthe\t0.5\tDH AH0\n");
        let d = &lexicon.pronunciations["'d"][0];
        assert_eq!(d.phones, vec!["D"]);
        assert_eq!((d.probability, d.silence_after_probability, d.silence_before_correction, d.non_silence_before_correction),
                   (Some(0.99), Some(0.34), Some(0.62), Some(1.14)));
        assert_eq!(lexicon.pronunciations["the"].len(), 1, "duplicate pronunciations are kept once");
        assert_eq!(lexicon.pronunciations["a"][0].probability, None);
    }
}
