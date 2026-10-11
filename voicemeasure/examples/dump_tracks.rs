//! Write voicemeasure's formant frames for a WAV file in the same format as
//! reference/dump_tracks.praat, for comparison with Praat.
//!
//!     cargo run --release --example dump_tracks -- recording.wav out/recording
//!
//! writes out/recording-formant.tsv.

use std::io::Write;
use voicemeasure::{to_formant_burg, FormantSettings};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: dump_tracks <recording.wav> <output prefix>");
        std::process::exit(2);
    }
    let mut reader = hound::WavReader::open(&args[1]).expect("can't read WAV file");
    let spec = reader.spec();
    assert_eq!(spec.channels, 1, "expected a mono WAV file");
    let samples: Vec<f64> = match spec.sample_format {
        hound::SampleFormat::Int => {
            let scale = (1i64 << (spec.bits_per_sample - 1)) as f64;
            reader.samples::<i32>().map(|s| s.unwrap() as f64 / scale).collect()
        }
        hound::SampleFormat::Float => reader.samples::<f32>().map(|s| s.unwrap() as f64).collect(),
    };

    let frames = to_formant_burg(&samples, spec.sample_rate as f64, &FormantSettings::default());
    let mut out = std::io::BufWriter::new(
        std::fs::File::create(format!("{}-formant.tsv", args[2])).expect("can't write output"),
    );
    write!(out, "frame\ttime(s)\tnformants").unwrap();
    for k in 1..=5 {
        write!(out, "\tF{k}(Hz)\tB{k}(Hz)").unwrap();
    }
    writeln!(out).unwrap();
    for (i, frame) in frames.iter().enumerate() {
        write!(out, "{}\t{:.6}\t{}", i + 1, frame.time, frame.formants.len()).unwrap();
        for k in 0..5 {
            match frame.formants.get(k) {
                Some(f) => write!(out, "\t{:.3}\t{:.3}", f.frequency, f.bandwidth).unwrap(),
                None => write!(out, "\t--undefined--\t--undefined--").unwrap(),
            }
        }
        writeln!(out).unwrap();
    }
}
