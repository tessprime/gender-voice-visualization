//! Align a WAV file (16 kHz mono) with the public API and print the words.
//!
//!     cargo run --release --example align_api -- MODEL_DIR dictionary.dict recording.wav transcript.txt [dither]
use voicealign::Aligner;
fn main() {
    let a: Vec<String> = std::env::args().collect();
    let read = |p: &str| std::fs::read(p).unwrap();
    let text = |p: &str| std::fs::read_to_string(p).unwrap();
    let start = std::time::Instant::now();
    let mut aligner = Aligner::new(&read(&format!("{}/final.alimdl", a[1])), &read(&format!("{}/tree", a[1])),
        &read(&format!("{}/lda.mat", a[1])), &text(&format!("{}/phones.txt", a[1])), &text(&a[2])).unwrap();
    if let Some(d) = a.get(5) { aligner.dither = d.parse().unwrap(); }
    eprintln!("loaded in {:.0} ms", start.elapsed().as_secs_f64() * 1000.0);
    let samples: Vec<f32> = hound::WavReader::open(&a[3]).unwrap().samples::<i16>().map(|s| s.unwrap() as f32 / 32768.0).collect();
    let start = std::time::Instant::now();
    let result = aligner.align(&samples, 16000, &text(&a[4])).unwrap();
    eprintln!("aligned in {:.0} ms", start.elapsed().as_secs_f64() * 1000.0);
    for w in &result.words { println!("{:.3}\t{:.3}\t{}", w.start, w.end, w.label); }
}
