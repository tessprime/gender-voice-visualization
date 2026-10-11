//! Time each stage of the analysis on a WAV file.
//!
//!     cargo run --release --example bench -- recording.wav

use std::time::Instant;
use voicemeasure::{resample::resample, to_formant_burg, to_pitch, FormantSettings, PitchSettings};

fn main() {
    let path = std::env::args().nth(1).expect("usage: bench <recording.wav>");
    let mut reader = hound::WavReader::open(path).expect("can't read WAV file");
    let rate = reader.spec().sample_rate as f64;
    let samples: Vec<f64> = reader.samples::<i16>().map(|s| s.unwrap() as f64 / 32768.0).collect();
    println!("audio: {:.1} s at {} Hz", samples.len() as f64 / rate, rate);

    let time = |label: &str, f: &mut dyn FnMut()| {
        let start = Instant::now();
        f();
        println!("{:>8.0} ms  {}", start.elapsed().as_secs_f64() * 1000.0, label);
    };
    time("resample to 10 kHz", &mut || { resample(&samples, rate, 10000.0); });
    time("formants (incl. resampling)", &mut || { to_formant_burg(&samples, rate, &FormantSettings::default()); });
    time("pitch", &mut || { to_pitch(&samples, rate, &PitchSettings::default()); });
}
