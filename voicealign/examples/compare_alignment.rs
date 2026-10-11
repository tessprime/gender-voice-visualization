//! Align a recording end to end and compare with kalpy's alignment.
//!
//!     cargo run --release --example compare_alignment -- recording.wav MODEL_DIR REFERENCE_DIR
//!
//! REFERENCE_DIR holds the output of reference/dump_alignment.py (dither
//! off) for the same recording.

use std::time::Instant;
use voicealign::align::{align, AlignOptions};
use voicealign::features::{alignment_features, MfccOptions};
use voicealign::graph::{compile, SilenceSettings};
use voicealign::kaldi_io::Reader;
use voicealign::lexicon::{read_phone_table, Lexicon};
use voicealign::model::AcousticModel;
use voicealign::tree::ContextDependency;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let (wav, model_dir, reference) = (&args[1], &args[2], &args[3]);
    let read = |path: String| std::fs::read_to_string(path).unwrap();

    let clock = Instant::now();
    let model = AcousticModel::read(&std::fs::read(format!("{model_dir}/final.alimdl")).unwrap()).unwrap();
    let tree = ContextDependency::read(&std::fs::read(format!("{model_dir}/tree")).unwrap()).unwrap();
    let lda = Reader::new(&std::fs::read(format!("{model_dir}/lda.mat")).unwrap()).unwrap().matrix().unwrap();
    let phones = read_phone_table(&read(format!("{model_dir}/phones.txt")));
    let phone_names: std::collections::HashMap<usize, String> = phones.iter().map(|(n, &i)| (i, n.clone())).collect();
    println!("load model, tree, LDA: {:.0} ms", clock.elapsed().as_secs_f64() * 1000.0);

    let lexicon = Lexicon::parse(&read(format!("{reference}/dictionary.dict")));
    let words: Vec<String> = read(format!("{reference}/words.txt")).split_whitespace().map(String::from).collect();
    let samples: Vec<f64> = hound::WavReader::open(wav).unwrap().samples::<i16>().map(|s| s.unwrap() as f64).collect();

    let clock = Instant::now();
    let features = alignment_features(&samples, &MfccOptions::default(), &lda);
    let feature_ms = clock.elapsed().as_secs_f64() * 1000.0;
    let clock = Instant::now();
    let graph = compile(&words, &lexicon, &phones, &model.transitions, &tree, &SilenceSettings::default()).unwrap();
    let graph_ms = clock.elapsed().as_secs_f64() * 1000.0;
    let clock = Instant::now();
    let alignment = align(&graph, &model, &features, &AlignOptions::default()).expect("alignment failed");
    let align_ms = clock.elapsed().as_secs_f64() * 1000.0;
    println!("features {feature_ms:.0} ms, graph {graph_ms:.1} ms, alignment {align_ms:.0} ms{}", if alignment.retried { " (retried)" } else { "" });

    // Transition ids, frame by frame.
    let kalpy_ids: Vec<usize> = read(format!("{reference}/alignment.txt")).lines().map(|l| l.parse().unwrap()).collect();
    let same = alignment.transition_ids.iter().zip(&kalpy_ids).filter(|(a, b)| a == b).count();
    let first_difference = alignment.transition_ids.iter().zip(&kalpy_ids).position(|(a, b)| a != b);
    println!("transition ids: {same}/{} frames identical{}", kalpy_ids.len(),
        first_difference.map_or(String::new(), |f| format!(" (first difference at frame {f})")));

    let result = read(format!("{reference}/result.txt"));
    let kalpy_likelihood: f64 = result.lines().next().unwrap().split_whitespace().nth(1).unwrap().parse().unwrap();
    println!("likelihood: ours {:.3}, kalpy {:.3}", alignment.likelihood, kalpy_likelihood);

    // Phone and word intervals.
    let intervals = |kind: &str| -> Vec<(f64, f64, String)> {
        result.lines().filter(|l| l.starts_with(kind)).map(|l| {
            let f: Vec<&str> = l.split_whitespace().collect();
            (f[1].parse().unwrap(), f[2].parse().unwrap(), f[3].to_string())
        }).collect()
    };
    let duration = samples.len() as f64 / 16000.0;
    let ours_phones: Vec<(f64, f64, String)> = alignment.phones.iter()
        .map(|s| { let (a, b) = s.seconds(duration); (a, b, phone_names[&s.label].clone()) }).collect();
    let kalpy_phones = intervals("phone ");
    let same_phones = ours_phones.iter().zip(&kalpy_phones)
        .filter(|(a, b)| (a.0 - b.0).abs() < 1e-3 && (a.1 - b.1).abs() < 1e-3 && a.2 == b.2).count();
    println!("phones: ours {}, kalpy {}; identical (label and times) {same_phones}", ours_phones.len(), kalpy_phones.len());
    let ours_words: Vec<(f64, f64, String)> = alignment.words.iter()
        .map(|s| { let (a, b) = s.seconds(duration); (a, b, words[s.label].clone()) }).collect();
    let kalpy_words: Vec<(f64, f64, String)> = intervals("word ").into_iter().filter(|w| w.2 != "<eps>").collect();
    let same_words = ours_words.iter().zip(&kalpy_words)
        .filter(|(a, b)| (a.0 - b.0).abs() < 1e-3 && (a.1 - b.1).abs() < 1e-3 && a.2 == b.2).count();
    println!("words: ours {}, kalpy {}; identical {same_words}", ours_words.len(), kalpy_words.len());
    let close = |a: &(f64, f64, String), b: &(f64, f64, String)| (a.0 - b.0).abs() < 1e-3 && (a.1 - b.1).abs() < 1e-3 && a.2 == b.2;
    for (a, b) in ours_phones.iter().zip(&kalpy_phones).filter(|(a, b)| !close(a, b)).take(3) {
        println!("  phone differs: ours {:?}, kalpy {:?}", a, b);
    }
}
