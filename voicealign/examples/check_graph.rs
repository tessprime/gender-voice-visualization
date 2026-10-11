//! Build the alignment graph for kalpy's reference transcript and check
//! that kalpy's alignment is a path through it, with the same score.
//!
//!     cargo run --release --example check_graph -- MODEL_DIR REFERENCE_DIR
//!
//! REFERENCE_DIR holds the output of reference/dump_kalpy.py and
//! reference/dump_alignment.py.

use voicealign::graph::{compile, SilenceSettings, FINAL};
use voicealign::lexicon::{read_phone_table, Lexicon};
use voicealign::model::AcousticModel;
use voicealign::tree::ContextDependency;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let (model_dir, reference) = (&args[1], &args[2]);
    let read = |path: String| std::fs::read_to_string(path).unwrap();
    let model = AcousticModel::read(&std::fs::read(format!("{model_dir}/final.alimdl")).unwrap()).unwrap();
    let tree = ContextDependency::read(&std::fs::read(format!("{model_dir}/tree")).unwrap()).unwrap();
    let phones = read_phone_table(&read(format!("{model_dir}/phones.txt")));
    let lexicon = Lexicon::parse(&read(format!("{reference}/dictionary.dict")));
    let words: Vec<String> = read(format!("{reference}/words.txt")).split_whitespace().map(String::from).collect();

    let start = std::time::Instant::now();
    let graph = compile(&words, &lexicon, &phones, &model.transitions, &tree, &SilenceSettings::default()).unwrap();
    let arcs: usize = graph.nodes.iter().map(|n| n.arcs.len()).sum();
    println!(
        "graph for {} words: {} units, {} nodes, {} arcs, {} start nodes; built in {:.1} ms",
        words.len(), graph.units.len(), graph.nodes.len(), arcs, graph.start.len(), start.elapsed().as_secs_f64() * 1000.0
    );

    // Follow kalpy's transition ids through the graph, keeping the cheapest
    // cost (lexicon + transitions: scale 1 forward, 0.1 for self-loops) of
    // reaching each node.
    let t = &model.transitions;
    // kalpy labels HMM-state stays "reordered" (forward transition first);
    // the graph uses the natural order.
    let reordered: Vec<usize> = read(format!("{reference}/alignment.txt")).lines().map(|l| l.parse().unwrap()).collect();
    let alignment = t.from_reordered(&reordered);
    assert_eq!(t.to_reordered(&alignment), reordered, "reordering doesn't round-trip");
    assert!(alignment.iter().zip(&reordered).all(|(a, b)| t.pdf(*a) == t.pdf(*b)), "reordering changed a frame's pdf");
    let transition_cost = |id: usize| -t.scaled_log_prob(id, 1.0, 0.1);
    let mut current: Vec<(usize, f64)> = graph.start.clone(); // (node, cost) before consuming a frame
    let mut final_cost = None;
    for (frame, &id) in alignment.iter().enumerate() {
        let mut next: std::collections::HashMap<usize, f64> = std::collections::HashMap::new();
        let mut reached_final = None;
        for &(node, cost) in &current {
            for arc in graph.nodes[node].arcs.iter().filter(|a| a.transition_id == id) {
                let c = cost + arc.cost + transition_cost(id);
                if arc.to == FINAL {
                    reached_final = Some(reached_final.map_or(c, |r: f64| r.min(c)));
                } else if next.get(&arc.to).map_or(true, |&b| c < b) {
                    next.insert(arc.to, c);
                }
            }
        }
        if frame + 1 == alignment.len() {
            final_cost = reached_final;
        }
        if next.is_empty() && frame + 1 < alignment.len() {
            println!("kalpy's alignment leaves the graph at frame {frame} (transition id {id}, phone {})", t.phone(id));
            return;
        }
        current = next.into_iter().collect();
    }
    let Some(graph_cost) = final_cost else {
        println!("kalpy's alignment doesn't end in a final state");
        return;
    };

    // Acoustic log-likelihood of the path, on kalpy's features.
    let bytes = std::fs::read(format!("{reference}/features.f32")).unwrap();
    let cols = u32::from_le_bytes(bytes[4..8].try_into().unwrap()) as usize;
    let features: Vec<f64> = bytes[8..].chunks_exact(4).map(|c| f32::from_le_bytes(c.try_into().unwrap()) as f64).collect();
    let acoustic: f64 = alignment
        .iter()
        .enumerate()
        .map(|(f, &id)| model.gmms[t.pdf(id)].log_likelihood(&features[f * cols..(f + 1) * cols]))
        .sum();
    // Kaldi reports -(graph cost + 0.1 * acoustic cost) / 0.1.
    let likelihood = acoustic - graph_cost / 0.1;
    let kalpy: f64 = read(format!("{reference}/result.txt")).lines().next().unwrap().split_whitespace().nth(1).unwrap().parse().unwrap();
    println!("kalpy's alignment is a path through the graph: {} frames", alignment.len());
    println!("  graph + transition cost {graph_cost:.4}, acoustic log-likelihood {acoustic:.2}");
    println!("  likelihood: ours {likelihood:.3}, kalpy {kalpy:.3}, difference {:.3}", likelihood - kalpy);
}
