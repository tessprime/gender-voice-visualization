// SPDX-License-Identifier: MIT

//! The alignment graph for a transcript: the words in order, each with its
//! pronunciations, optional silence between them, expanded into triphones
//! (via the decision tree) and HMM states (via the transition model).
//!
//! Kaldi builds the same graph by FST composition (lexicon ∘ transcript ∘
//! context ∘ HMMs) and determinization; for one known word sequence it can
//! be built directly. Costs follow kalpy's lexicon (`create_fsts` and
//! `add_pronunciation` in kalpy/fstext/lexicon.py): tropical, -log p. The
//! HMM transition probabilities aren't in the graph; the aligner adds them,
//! as kalpy's compiler uses scale 0 for them.

use crate::lexicon::{Lexicon, Pronunciation};
use crate::model::{TransitionModel, Tuple};
use crate::tree::ContextDependency;
use std::collections::HashMap;

/// Silence settings from the acoustic model's metadata; `Default` gives
/// english_us_arpa's.
#[derive(Clone, Debug)]
pub struct SilenceSettings {
    pub silence_probability: f64,
    pub initial_silence_probability: f64,
    pub final_silence_correction: f64,
    pub final_non_silence_correction: f64,
}

impl Default for SilenceSettings {
    fn default() -> Self {
        SilenceSettings {
            silence_probability: 0.18,
            initial_silence_probability: 0.18,
            final_silence_correction: 0.99,
            final_non_silence_correction: 0.01,
        }
    }
}

/// The graph's final state, as an arc destination.
pub const FINAL: usize = usize::MAX;

#[derive(Clone, Debug)]
pub struct Arc {
    pub transition_id: usize,
    /// A node, or FINAL.
    pub to: usize,
    /// Lexicon cost of taking this arc (silence and pronunciation choices).
    pub cost: f64,
}

/// One HMM state of one phone in context.
#[derive(Clone, Debug)]
pub struct Node {
    pub arcs: Vec<Arc>,
    /// Which phone occurrence (triphone unit) the node belongs to.
    pub unit: usize,
    pub hmm_state: usize,
}

/// A phone occurrence in context.
#[derive(Clone, Debug)]
pub struct Unit {
    pub phone: usize,
    /// Index into the transcript's words, or None for silence.
    pub word: Option<usize>,
    /// Whether this is the first phone of its word.
    pub word_start: bool,
}

#[derive(Clone, Debug)]
pub struct Graph {
    pub nodes: Vec<Node>,
    pub units: Vec<Unit>,
    /// Nodes a path can start at, with their costs.
    pub start: Vec<(usize, f64)>,
    /// The transcript's words.
    pub words: Vec<String>,
}

#[derive(Debug)]
pub struct GraphError(pub String);

/// A phone arc of the word-level phone graph.
struct PhoneArc {
    from: usize,
    to: usize,
    phone: usize,
    cost: f64,
    word: Option<usize>,
    word_start: bool,
}

pub fn compile(
    words: &[String],
    lexicon: &Lexicon,
    phones: &HashMap<String, usize>,
    transitions: &TransitionModel,
    tree: &ContextDependency,
    settings: &SilenceSettings,
) -> Result<Graph, GraphError> {
    let phone_id = |name: &str| phones.get(name).copied().ok_or_else(|| GraphError(format!("unknown phone {}", name)));
    let silence = phone_id("sil")?;
    let cost = |p: f64| -p.ln();

    // --- Phone graph. Nodes: 0 start; before word i, 1 + 2i ("no silence
    // just before") and 2 + 2i ("silence just before"); then pronunciation
    // states.
    let n = words.len();
    let no_silence = |i: usize| 1 + 2 * i;
    let after_silence = |i: usize| 2 + 2 * i;
    let mut node_count = 1 + 2 * (n + 1);
    let mut phone_arcs: Vec<PhoneArc> = Vec::new();
    let mut epsilon_arcs: Vec<(usize, usize, f64)> = Vec::new();
    epsilon_arcs.push((0, no_silence(0), cost(1.0 - settings.initial_silence_probability)));
    phone_arcs.push(PhoneArc {
        from: 0, to: after_silence(0), phone: silence,
        cost: cost(settings.initial_silence_probability), word: None, word_start: false,
    });

    let unknown = Pronunciation {
        word: "<unk>".into(), phones: vec!["spn".into()], probability: None,
        silence_after_probability: None, silence_before_correction: None, non_silence_before_correction: None,
    };
    for (i, word) in words.iter().enumerate() {
        let pronunciations = lexicon.pronunciations.get(&word.to_lowercase()).map(|p| p.as_slice()).unwrap_or(std::slice::from_ref(&unknown));
        for pronunciation in pronunciations {
            let probability = pronunciation.probability.unwrap_or(1.0).max(0.01);
            let pronunciation_cost = probability.ln().abs();
            let correction = |c: Option<f64>| c.filter(|&v| v != 0.0).map_or(0.0, cost);
            let silence_after = pronunciation.silence_after_probability.filter(|&v| v != 0.0);
            let silence_following = silence_after.map_or(cost(settings.silence_probability), cost);
            let no_silence_following = silence_after.map_or(cost(1.0 - settings.silence_probability), |p| cost(1.0 - p));

            let ids = pronunciation.phones.iter().map(|p| phone_id(p)).collect::<Result<Vec<_>, _>>()?;
            let mut previous = None;
            for (k, &phone) in ids.iter().enumerate() {
                let to = node_count;
                node_count += 1;
                match previous {
                    None => {
                        for (from, extra) in [
                            (no_silence(i), correction(pronunciation.non_silence_before_correction)),
                            (after_silence(i), correction(pronunciation.silence_before_correction)),
                        ] {
                            phone_arcs.push(PhoneArc { from, to, phone, cost: pronunciation_cost + extra, word: Some(i), word_start: true });
                        }
                    }
                    Some(from) => phone_arcs.push(PhoneArc { from, to, phone, cost: 0.0, word: Some(i), word_start: false }),
                }
                previous = Some(to);
                let _ = k;
            }
            let last = previous.ok_or_else(|| GraphError(format!("empty pronunciation for {}", word)))?;
            epsilon_arcs.push((last, no_silence(i + 1), no_silence_following));
            phone_arcs.push(PhoneArc { from: last, to: after_silence(i + 1), phone: silence, cost: silence_following, word: None, word_start: false });
        }
    }
    let mut final_cost = vec![None; node_count];
    final_cost[no_silence(n)] = Some(cost(settings.final_non_silence_correction));
    final_cost[after_silence(n)] = Some(cost(settings.final_silence_correction));

    // Epsilon closure: nodes reachable from each node through epsilon arcs,
    // with the cheapest cost.
    let closure = |start: usize| -> Vec<(usize, f64)> {
        let mut best: HashMap<usize, f64> = HashMap::from([(start, 0.0)]);
        let mut stack = vec![start];
        while let Some(node) = stack.pop() {
            let here = best[&node];
            for &(from, to, c) in &epsilon_arcs {
                if from == node && best.get(&to).map_or(true, |&b| here + c < b) {
                    best.insert(to, here + c);
                    stack.push(to);
                }
            }
        }
        best.into_iter().collect()
    };
    let mut leaving: Vec<Vec<usize>> = vec![Vec::new(); node_count];
    for (index, arc) in phone_arcs.iter().enumerate() {
        leaving[arc.from].push(index);
    }
    // For each phone arc: following phone arcs (with the epsilon cost in
    // between) and, if the path can end after it, the cost of ending.
    let mut following: Vec<Vec<(usize, f64)>> = Vec::with_capacity(phone_arcs.len());
    let mut ending: Vec<Option<f64>> = Vec::with_capacity(phone_arcs.len());
    for arc in &phone_arcs {
        let mut next = Vec::new();
        let mut end: Option<f64> = None;
        for (node, c) in closure(arc.to) {
            next.extend(leaving[node].iter().map(|&b| (b, c)));
            if let Some(f) = final_cost[node] {
                end = Some(end.map_or(c + f, |e: f64| e.min(c + f)));
            }
        }
        following.push(next);
        ending.push(end);
    }
    let initial: Vec<(usize, f64)> = closure(0).into_iter().flat_map(|(node, c)| leaving[node].iter().map(move |&b| (b, c))).collect();
    let mut preceding: Vec<Vec<usize>> = vec![Vec::new(); phone_arcs.len()];
    for (a, next) in following.iter().enumerate() {
        for &(b, _) in next {
            preceding[b].push(a);
        }
    }
    let starts_here: Vec<bool> = (0..phone_arcs.len()).map(|a| initial.iter().any(|&(b, _)| b == a)).collect();

    // --- Triphone units: (phone arc, left phone, right phone), 0 at edges.
    let mut unit_index: HashMap<(usize, usize, usize), usize> = HashMap::new();
    let mut unit_keys: Vec<(usize, usize, usize)> = Vec::new();
    for a in 0..phone_arcs.len() {
        let mut lefts: Vec<usize> = preceding[a].iter().map(|&b| phone_arcs[b].phone).collect();
        if starts_here[a] {
            lefts.push(0);
        }
        let mut rights: Vec<usize> = following[a].iter().map(|&(b, _)| phone_arcs[b].phone).collect();
        if ending[a].is_some() {
            rights.push(0);
        }
        lefts.sort();
        lefts.dedup();
        rights.sort();
        rights.dedup();
        for &l in &lefts {
            for &r in &rights {
                unit_index.insert((a, l, r), unit_keys.len());
                unit_keys.push((a, l, r));
            }
        }
    }

    // --- HMM states: each unit's emitting states become nodes.
    let tuple_index: HashMap<Tuple, usize> = transitions.tuples.iter().enumerate().map(|(i, t)| (*t, i + 1)).collect();
    let mut graph = Graph { nodes: Vec::new(), units: Vec::new(), start: Vec::new(), words: words.to_vec() };
    let mut first_node = Vec::with_capacity(unit_keys.len());
    for (u, &(a, _, _)) in unit_keys.iter().enumerate() {
        let arc = &phone_arcs[a];
        graph.units.push(Unit { phone: arc.phone, word: arc.word, word_start: arc.word_start });
        first_node.push(graph.nodes.len());
        let topology = transitions.topology.for_phone(arc.phone);
        for state in 0..topology.len() {
            if !topology[state].transitions.is_empty() {
                graph.nodes.push(Node { arcs: Vec::new(), unit: u, hmm_state: state });
            }
        }
    }
    // Node of (unit, emitting state): emitting states are numbered first in
    // Kaldi topologies, so the node is first_node + state.
    for (u, &(a, left, right)) in unit_keys.iter().enumerate() {
        let arc = &phone_arcs[a];
        let context = [left, arc.phone, right];
        let topology = transitions.topology.for_phone(arc.phone);
        // Units this one can lead into, with their entry costs: only those
        // of the phone this unit assumed as its right context.
        let mut successors: Vec<(usize, f64)> = Vec::new();
        for &(b, between) in &following[a] {
            let next = &phone_arcs[b];
            if next.phone != right {
                continue;
            }
            for (&(b2, l2, _), &u2) in unit_index.iter() {
                if b2 == b && l2 == arc.phone {
                    successors.push((u2, between + next.cost));
                }
            }
        }
        let exit = if right == 0 { ending[a] } else { None };
        for state in 0..topology.len() {
            let s = &topology[state];
            if s.transitions.is_empty() {
                continue;
            }
            let pdf = |class: i64| tree.pdf(&context, class).ok_or_else(|| GraphError(format!("no pdf for context {:?} class {}", context, class)));
            let tuple = Tuple { phone: arc.phone, hmm_state: state, forward_pdf: pdf(s.forward_pdf_class)?, self_loop_pdf: pdf(s.self_loop_pdf_class)? };
            let transition_state = *tuple_index.get(&tuple).ok_or_else(|| GraphError(format!("no transition state for {:?}", tuple)))?;
            let mut arcs = Vec::new();
            for (index, &(destination, _)) in s.transitions.iter().enumerate() {
                let transition_id = transitions.transition_id(transition_state, index);
                if !topology[destination].transitions.is_empty() {
                    arcs.push(Arc { transition_id, to: first_node[u] + destination, cost: 0.0 });
                } else {
                    for &(u2, c) in &successors {
                        arcs.push(Arc { transition_id, to: first_node[u2], cost: c });
                    }
                    if let Some(c) = exit {
                        arcs.push(Arc { transition_id, to: FINAL, cost: c });
                    }
                }
            }
            graph.nodes[first_node[u] + state].arcs = arcs;
        }
    }
    for &(a, between) in &initial {
        for (&(a2, l, _), &u) in unit_index.iter() {
            if a2 == a && l == 0 {
                graph.start.push((first_node[u], between + phone_arcs[a].cost));
            }
        }
    }
    Ok(graph)
}
