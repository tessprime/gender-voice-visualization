//! Measure F0 and F1-F3 at given times, as the web app does at each phone's
//! midpoint (textgrid-formants.praat).
//!
//!     cargo run --release --example measure_at -- recording.wav times.txt
//!
//! times.txt has one time in seconds per line; prints `time f0 f1 f2 f3`
//! per line, tab-separated, with --undefined-- where there's no value.

use voicemeasure::measure_at;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: measure_at <recording.wav> <times.txt>");
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
    let times: Vec<f64> = std::fs::read_to_string(&args[2])
        .expect("can't read times")
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| l.trim().parse().expect("not a number"))
        .collect();

    let show = |v: Option<f64>| v.map_or("--undefined--".to_string(), |v| format!("{:.3}", v));
    for (time, m) in times.iter().zip(measure_at(&samples, spec.sample_rate as f64, &times)) {
        println!("{}\t{}\t{}\t{}\t{}", time, show(m.f0), show(m.f1), show(m.f2), show(m.f3));
    }
}
