//! A minimal C-style interface for WebAssembly, needing no bindings
//! generator. From JavaScript:
//!
//! 1. `va_alloc(n)` returns a pointer to `n` bytes in the module's memory;
//!    copy inputs there (`va_free(pointer, n)` releases them).
//! 2. `va_new(model, model_len, tree, tree_len, lda, lda_len, phones,
//!    phones_len, dictionary, dictionary_len)` loads an aligner from the
//!    model files' bytes (phones.txt and the dictionary as UTF-8) and
//!    returns a handle, or 0 on error.
//! 3. `va_align(handle, samples, sample_count, transcript, transcript_len)`
//!    takes f32 samples (16 kHz, -1..1) and a UTF-8 transcript, and returns
//!    a pointer to a result: a little-endian u32 length, then that many
//!    bytes of JSON: `{"words": [[start, end, label], ...], "phones": [...],
//!    "likelihood": x}` or `{"error": "..."}`. Free it with
//!    `va_free(pointer, 4 + length)`.

use crate::Aligner;

#[no_mangle]
pub extern "C" fn va_alloc(len: usize) -> *mut u8 {
    let mut buffer = Vec::<u8>::with_capacity(len);
    let pointer = buffer.as_mut_ptr();
    std::mem::forget(buffer);
    pointer
}

/// # Safety
/// `pointer` must come from `va_alloc(len)` (or be a result of the given
/// length) and not have been freed.
#[no_mangle]
pub unsafe extern "C" fn va_free(pointer: *mut u8, len: usize) {
    drop(Vec::from_raw_parts(pointer, 0, len));
}

unsafe fn bytes<'a>(pointer: *const u8, len: usize) -> &'a [u8] {
    std::slice::from_raw_parts(pointer, len)
}

/// # Safety
/// Each pointer must point to the given number of readable bytes.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn va_new(
    model: *const u8, model_len: usize,
    tree: *const u8, tree_len: usize,
    lda: *const u8, lda_len: usize,
    phones: *const u8, phones_len: usize,
    dictionary: *const u8, dictionary_len: usize,
) -> *mut Aligner {
    let text = |p, n| String::from_utf8_lossy(bytes(p, n)).into_owned();
    match Aligner::new(bytes(model, model_len), bytes(tree, tree_len), bytes(lda, lda_len),
                       &text(phones, phones_len), &text(dictionary, dictionary_len)) {
        Ok(aligner) => Box::into_raw(Box::new(aligner)),
        Err(_) => std::ptr::null_mut(),
    }
}

fn json_string(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// # Safety
/// `aligner` must come from `va_new`; `samples` must point to
/// `sample_count` f32 values and `transcript` to `transcript_len` bytes.
#[no_mangle]
pub unsafe extern "C" fn va_align(
    aligner: *const Aligner,
    samples: *const f32, sample_count: usize,
    transcript: *const u8, transcript_len: usize,
) -> *mut u8 {
    let samples = std::slice::from_raw_parts(samples, sample_count);
    let transcript = String::from_utf8_lossy(bytes(transcript, transcript_len));
    let json = match (*aligner).align(samples, 16000, &transcript) {
        Ok(a) => {
            let list = |intervals: &[crate::Interval]| {
                intervals.iter().map(|i| format!("[{:.3},{:.3},{}]", i.start, i.end, json_string(&i.label))).collect::<Vec<_>>().join(",")
            };
            format!("{{\"words\":[{}],\"phones\":[{}],\"likelihood\":{}}}", list(&a.words), list(&a.phones), a.likelihood)
        }
        Err(e) => format!("{{\"error\":{}}}", json_string(&e.0)),
    };
    let mut out = (json.len() as u32).to_le_bytes().to_vec();
    out.extend_from_slice(json.as_bytes());
    let pointer = va_alloc(out.len());
    std::ptr::copy_nonoverlapping(out.as_ptr(), pointer, out.len());
    pointer
}
