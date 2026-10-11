//! Compare voicealign's model and tree loading with kalpy's.
//!
//!     cargo run --release --example compare_model -- MODEL_DIR REFERENCE_DIR
//!
//! MODEL_DIR holds final.alimdl and tree; REFERENCE_DIR the output of
//! reference/dump_kalpy.py and reference/dump_model.py.

use std::collections::{BTreeMap, BTreeSet};
use voicealign::model::AcousticModel;
use voicealign::tree::ContextDependency;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let (model_dir, reference) = (&args[1], &args[2]);
    let start = std::time::Instant::now();
    let model = AcousticModel::read(&std::fs::read(format!("{model_dir}/final.alimdl")).unwrap()).unwrap();
    let tree = ContextDependency::read(&std::fs::read(format!("{model_dir}/tree")).unwrap()).unwrap();
    println!("loaded model and tree in {:.0} ms", start.elapsed().as_secs_f64() * 1000.0);
    let t = &model.transitions;
    let gaussians: usize = model.gmms.iter().map(|g| g.num_components()).sum();
    println!(
        "ours:  transition_ids {} transition_states {} pdfs {} dim {} gaussians {}; tree width {} central {}",
        t.num_transition_ids(), t.tuples.len(), t.num_pdfs, model.dim, gaussians, tree.width, tree.central_position
    );

    // Per transition id.
    let text = std::fs::read_to_string(format!("{reference}/transitions.tsv")).unwrap();
    let mut lines = text.lines();
    println!("kalpy: {}", lines.next().unwrap().trim_start_matches("# "));
    let (mut checked, mut mismatched, mut largest_log_prob_difference) = (0, 0, 0.0f64);
    for line in lines {
        let f: Vec<&str> = line.split('\t').collect();
        let id: usize = f[0].parse().unwrap();
        let expected = (f[1].parse::<usize>().unwrap(), f[2].parse::<usize>().unwrap(), f[3].parse::<usize>().unwrap(), f[4] == "1", f[5] == "1");
        let ours = (t.pdf(id), t.phone(id), t.transition_state(id), t.is_self_loop(id), t.is_final(id));
        if ours != expected {
            mismatched += 1;
            if mismatched <= 3 {
                println!("  transition id {id}: ours {:?}, kalpy {:?}", ours, expected);
            }
        }
        largest_log_prob_difference = largest_log_prob_difference.max((t.log_prob(id) - f[6].parse::<f64>().unwrap()).abs());
        checked += 1;
    }
    println!("transition ids: {checked} checked, {mismatched} differ in pdf/phone/state/self-loop/final; largest log-prob difference {largest_log_prob_difference:.2e}");

    // GMM log-likelihoods on kalpy's features.
    let bytes = std::fs::read(format!("{reference}/features.f32")).unwrap();
    let cols = u32::from_le_bytes(bytes[4..8].try_into().unwrap()) as usize;
    let features: Vec<f64> = bytes[8..].chunks_exact(4).map(|c| f32::from_le_bytes(c.try_into().unwrap()) as f64).collect();
    let mut differences = Vec::new();
    for line in std::fs::read_to_string(format!("{reference}/loglikes.tsv")).unwrap().lines() {
        let f: Vec<&str> = line.split('\t').collect();
        let (frame, pdf, expected): (usize, usize, f64) = (f[0].parse().unwrap(), f[1].parse().unwrap(), f[2].parse().unwrap());
        let ours = model.gmms[pdf].log_likelihood(&features[frame * cols..(frame + 1) * cols]);
        differences.push((ours - expected).abs());
    }
    differences.sort_by(|a, b| a.partial_cmp(b).unwrap());
    println!(
        "log-likelihoods: {} (frame, pdf) pairs; |difference| median {:.2e}, max {:.2e}",
        differences.len(), differences[differences.len() / 2], differences.last().unwrap()
    );

    // Tree: for every pdf, which (central phone, pdf class) pairs reach it,
    // over every triphone context (0 = no phone, at utterance edges).
    let phones: BTreeSet<usize> = t.tuples.iter().map(|x| x.phone).collect();
    let mut ours: BTreeMap<usize, BTreeSet<(usize, i64)>> = BTreeMap::new();
    let contexts: Vec<usize> = std::iter::once(0).chain(phones.iter().cloned()).collect();
    let mut lookups = 0;
    for &central in &phones {
        let classes: BTreeSet<i64> = t.topology.for_phone(central).iter().map(|s| s.forward_pdf_class).filter(|&c| c >= 0).collect();
        for &left in &contexts {
            for &right in &contexts {
                for &class in &classes {
                    lookups += 1;
                    if let Some(pdf) = tree.pdf(&[left, central, right], class) {
                        ours.entry(pdf).or_default().insert((central, class));
                    }
                }
            }
        }
    }
    let (mut same, mut different) = (0, 0);
    for line in std::fs::read_to_string(format!("{reference}/pdf_info.tsv")).unwrap().lines() {
        let (pdf, pairs) = line.split_once('\t').unwrap();
        let expected: BTreeSet<(usize, i64)> = pairs
            .split_whitespace()
            .map(|p| {
                let (a, b) = p.split_once(',').unwrap();
                (a.parse().unwrap(), b.parse().unwrap())
            })
            .collect();
        if ours.get(&pdf.parse().unwrap()).cloned().unwrap_or_default() == expected { same += 1 } else { different += 1 }
    }
    println!("tree: {lookups} lookups; pdfs whose (phone, pdf class) sets match kalpy's: {same}, differ: {different}");
}
