//! Compare voicealign's features with kalpy's, stage by stage.
//!
//!     cargo run --release --example compare_features -- recording.wav lda.mat REFERENCE_DIR
//!
//! REFERENCE_DIR holds the output of reference/dump_kalpy.py for the same
//! recording.

use voicealign::features::{cmvn, mfcc, splice, transform, MfccOptions};
use voicealign::kaldi_io::{Matrix, Reader};

fn read_reference(path: &str) -> Matrix {
    let bytes = std::fs::read(path).expect("can't read reference");
    let rows = u32::from_le_bytes(bytes[0..4].try_into().unwrap()) as usize;
    let cols = u32::from_le_bytes(bytes[4..8].try_into().unwrap()) as usize;
    let data = bytes[8..].chunks_exact(4).map(|c| f32::from_le_bytes(c.try_into().unwrap()) as f64).collect();
    Matrix { rows, cols, data }
}

fn report(stage: &str, ours: &Matrix, reference: &Matrix) {
    if (ours.rows, ours.cols) != (reference.rows, reference.cols) {
        println!("{stage}: shape {}x{} vs kalpy {}x{}", ours.rows, ours.cols, reference.rows, reference.cols);
        return;
    }
    let scale = reference.data.iter().fold(0.0f64, |m, v| m.max(v.abs()));
    let mut differences: Vec<f64> = ours.data.iter().zip(&reference.data).map(|(a, b)| (a - b).abs()).collect();
    differences.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let largest = *differences.last().unwrap();
    println!(
        "{stage}: {}x{}; |difference| median {:.2e}, 99.9th pct {:.2e}, max {:.2e} (values up to {:.1})",
        ours.rows, ours.cols, differences[differences.len() / 2],
        differences[differences.len() * 999 / 1000], largest, scale
    );
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut reader = hound::WavReader::open(&args[1]).expect("can't read WAV");
    // kalpy feeds Kaldi samples on the 16-bit integer scale.
    let samples: Vec<f64> = reader.samples::<i16>().map(|s| s.unwrap() as f64).collect();
    let lda = Reader::new(&std::fs::read(&args[2]).unwrap()).unwrap().matrix().unwrap();
    let reference = &args[3];

    let mut features = mfcc(&samples, &MfccOptions::default());
    report("MFCC", &features, &read_reference(&format!("{reference}/mfcc.f32")));
    cmvn(&mut features);
    report("CMVN", &features, &read_reference(&format!("{reference}/cmvn.f32")));
    let features = transform(&splice(&features, 3), &lda);
    report("splice + LDA", &features, &read_reference(&format!("{reference}/features.f32")));
}
