//! Viterbi alignment of features to an alignment graph with beam pruning,
//! as Kaldi's gmm-align-compiled (FasterDecoder via AlignUtteranceWrapper):
//! try with `beam`, and if no path reaches the end, again with
//! `retry_beam`.
//!
//! An arc's cost is its lexicon cost, plus the scaled transition cost, plus
//! `acoustic_scale` times the negated GMM log-likelihood of the frame for
//! the arc's pdf. As in Kaldi, the reported likelihood is
//! -(total cost) / acoustic_scale.

use crate::graph::{Graph, FINAL};
use crate::kaldi_io::Matrix;
use crate::model::AcousticModel;
use std::collections::HashMap;

/// `Default` gives kalpy's (KalpyAligner's) settings.
#[derive(Clone, Debug)]
pub struct AlignOptions {
    pub beam: f64,
    pub retry_beam: f64,
    pub acoustic_scale: f64,
    pub transition_scale: f64,
    pub self_loop_scale: f64,
}

impl Default for AlignOptions {
    fn default() -> Self {
        AlignOptions { beam: 10.0, retry_beam: 40.0, acoustic_scale: 0.1, transition_scale: 1.0, self_loop_scale: 0.1 }
    }
}

/// A run of frames `start..end` (10 ms each).
#[derive(Clone, Debug, PartialEq)]
pub struct Segment {
    pub start: usize,
    pub end: usize,
    /// A phone id (for phone segments) or a word index (for word segments).
    pub label: usize,
}

/// Seconds per frame.
pub const FRAME_SHIFT: f64 = 0.01;

impl Segment {
    /// Start and end in seconds. The last frame can extend past the end of
    /// the recording; like kalpy, end times are clipped to `duration`.
    pub fn seconds(&self, duration: f64) -> (f64, f64) {
        (self.start as f64 * FRAME_SHIFT, (self.end as f64 * FRAME_SHIFT).min(duration))
    }
}

#[derive(Clone, Debug)]
pub struct Alignment {
    /// One transition id per frame, in Kaldi's (reordered) labelling.
    pub transition_ids: Vec<usize>,
    pub likelihood: f64,
    /// Including silence (phone `sil`).
    pub phones: Vec<Segment>,
    /// Words of the transcript, by index; silence isn't a word.
    pub words: Vec<Segment>,
    /// Whether it only succeeded with the retry beam.
    pub retried: bool,
}

/// One token: the best way found to reach a node after some frames.
#[derive(Clone, Copy)]
struct Token {
    cost: f64,
    /// Index of the previous frame's token, or usize::MAX at the start.
    previous: usize,
    transition_id: usize,
    node: usize,
}

pub fn align(graph: &Graph, model: &AcousticModel, features: &Matrix, options: &AlignOptions) -> Option<Alignment> {
    if let Some(alignment) = viterbi(graph, model, features, options, options.beam) {
        return Some(alignment);
    }
    let mut alignment = viterbi(graph, model, features, options, options.retry_beam)?;
    alignment.retried = true;
    Some(alignment)
}

fn viterbi(graph: &Graph, model: &AcousticModel, features: &Matrix, options: &AlignOptions, beam: f64) -> Option<Alignment> {
    let t = &model.transitions;
    let transition_cost: Vec<f64> = (0..=t.num_transition_ids())
        .map(|id| if id == 0 { 0.0 } else { -t.scaled_log_prob(id, options.transition_scale, options.self_loop_scale) })
        .collect();

    // Tokens per frame boundary: frames[f] holds the tokens after f frames.
    let mut frames: Vec<Vec<Token>> = Vec::with_capacity(features.rows + 1);
    let mut start: HashMap<usize, Token> = HashMap::new();
    for &(node, cost) in &graph.start {
        if start.get(&node).map_or(true, |t| cost < t.cost) {
            start.insert(node, Token { cost, previous: usize::MAX, transition_id: 0, node });
        }
    }
    frames.push(start.into_values().collect());

    for f in 0..features.rows {
        let x = features.row(f);
        let current = &frames[f];
        let best = current.iter().map(|t| t.cost).fold(f64::INFINITY, f64::min);
        let cutoff = best + beam;
        let mut acoustic: HashMap<usize, f64> = HashMap::new();
        let mut next: HashMap<usize, Token> = HashMap::new();
        let mut next_cutoff = f64::INFINITY;
        let last_frame = f + 1 == features.rows;
        for (index, token) in current.iter().enumerate() {
            if token.cost > cutoff || token.node == FINAL {
                continue;
            }
            for arc in &graph.nodes[token.node].arcs {
                if arc.to == FINAL && !last_frame {
                    continue; // the path must use every frame
                }
                let pdf = t.pdf(arc.transition_id);
                let ac = *acoustic.entry(pdf).or_insert_with(|| -options.acoustic_scale * model.gmms[pdf].log_likelihood(x));
                let cost = token.cost + arc.cost + transition_cost[arc.transition_id] + ac;
                if cost > next_cutoff {
                    continue;
                }
                next_cutoff = next_cutoff.min(cost + beam);
                if next.get(&arc.to).map_or(true, |t| cost < t.cost) {
                    next.insert(arc.to, Token { cost, previous: index, transition_id: arc.transition_id, node: arc.to });
                }
            }
        }
        let survivors: Vec<Token> = next.into_values().filter(|t| t.cost <= next_cutoff).collect();
        if survivors.is_empty() {
            return None;
        }
        frames.push(survivors);
    }

    // The path must end in the final state.
    let last = frames.last()?;
    let mut index = last.iter().position(|t| t.node == FINAL)?;
    let total_cost = last[index].cost;
    // Trace back: each frame's transition id, and the node it was emitted
    // from (the previous token's node), which gives its phone occurrence.
    let mut ids = vec![0; features.rows];
    let mut units = vec![0; features.rows];
    for f in (0..features.rows).rev() {
        let token = frames[f + 1][index];
        ids[f] = token.transition_id;
        units[f] = graph.nodes[frames[f][token.previous].node].unit;
        index = token.previous;
    }

    let mut phones: Vec<Segment> = Vec::new();
    let mut words: Vec<Segment> = Vec::new();
    for (f, &unit) in units.iter().enumerate() {
        let new_unit = f == 0 || units[f - 1] != unit;
        let u = &graph.units[unit];
        if new_unit {
            phones.push(Segment { start: f, end: f + 1, label: u.phone });
        } else {
            phones.last_mut().unwrap().end = f + 1;
        }
        if let Some(word) = u.word {
            match words.last_mut() {
                Some(w) if w.label == word && !(new_unit && u.word_start) => w.end = f + 1,
                _ => words.push(Segment { start: f, end: f + 1, label: word }),
            }
        }
    }

    Some(Alignment {
        transition_ids: t.to_reordered(&ids),
        likelihood: -total_cost / options.acoustic_scale,
        phones,
        words,
        retried: false,
    })
}
