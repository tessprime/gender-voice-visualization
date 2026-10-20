"""The player (ui/player.html) plays clips from a WAV of their decoded
audio, so seeking lands where it says: browsers seek compressed audio
approximately, a VBR MP3 by up to several seconds."""

import base64
import shutil
import subprocess

import pytest


@pytest.fixture(scope='session')
def vbr_mp3(tmp_path_factory):
    """Ten minutes of noise (20 s in every minute) and near-silence as a
    VBR MP3 (with a Xing seek table, as encoders write), as a data URI. The
    bitrate swings over spans longer than the table's steps (1% of the
    file), which is what throws seeking off."""
    if not shutil.which('ffmpeg'):
        pytest.skip('needs ffmpeg to make a VBR MP3')
    path = tmp_path_factory.mktemp('audio') / 'vbr.mp3'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'anoisesrc=d=600:c=white:a=0.5:seed=1',
        '-af', "volume='if(lt(mod(t,60),20),1,0.002)':eval=frame",
        '-ac', '1', '-ar', '44100', '-codec:a', 'libmp3lame', '-q:a', '6', str(path),
    ], check=True)
    return 'data:audio/mpeg;base64,' + base64.b64encode(path.read_bytes()).decode()


# Where audio really is after seeking: plays from `time`, records a moment
# of what comes out, and finds it in the decoded audio. Returns, per time,
# [reported, actual] (seconds) and how well it matched (1 = exactly). element is a selector, or null for a new
# <audio> playing `audio` directly.
WHERE_IT_LANDS = r"""
async ({audio, element, times}) => {
    const context = new AudioContext();
    await context.resume();
    const decoded = await fetch(audio).then(r => r.arrayBuffer()).then(b => context.decodeAudioData(b));
    const full = decoded.getChannelData(0), rate = context.sampleRate;
    let el = element && document.querySelector(element);
    if (!el) {
        el = new Audio(audio);
        await new Promise(r => el.addEventListener('canplaythrough', r, {once: true}));
    }
    const recorder = context.createScriptProcessor(1024, 1, 1);
    context.createMediaElementSource(el).connect(recorder);
    recorder.connect(context.destination);
    let chunks = [];
    recorder.onaudioprocess = e => {
        if (!el.paused) chunks.push({time: el.currentTime, samples: new Float32Array(e.inputBuffer.getChannelData(0))});
    };
    const results = [];
    // Each time up to three tries: on a busy machine the recorder can drop
    // a block, and then the recording matches nowhere.
    const measure = async time => {
        // Listening first: play() resolves after 'playing' has fired.
        const started = new Promise(r => el.addEventListener('playing', r, {once: true}));
        if (element) {
            playClipFrom(globalState.get('playingClip'), time);
        } else {
            el.currentTime = time;
            el.play();
        }
        await started;
        chunks = [];
        await new Promise(r => setTimeout(r, 600));
        el.pause();
        if (element) globalState.set('playing', false);
        const use = chunks.slice(4, 10);
        const segment = new Float32Array(use.length * 1024);
        use.forEach((c, i) => segment.set(c.samples, i * 1024));
        const reported = use[0].time;
        let energy = 0;
        for (const v of segment) energy += v * v;
        const score = k => {
            if (k < 0 || k + segment.length > full.length) return -1;
            let s = 0, e = 0;
            for (let i = 0; i < segment.length; i += 2) { s += segment[i] * full[k + i]; e += full[k + i] ** 2; }
            return s / Math.sqrt(e * energy / 2 + 1e-12);
        };
        // Every offset within half a second (white noise matches only at
        // the exact sample).
        const center = Math.round(reported * rate), span = Math.round(rate / 2);
        let best = -2, at = 0;
        for (let k = center - span; k <= center + span; k++) { const v = score(k); if (v > best) { best = v; at = k; } }
        return [reported, at / rate, best];
    };
    for (const time of times) {
        let result;
        for (let attempt = 0; attempt < 3; attempt++) {
            result = await measure(time);
            if (result[2] > .8) break;
        }
        results.push(result);
    }
    return results;
}
"""
# Inside the noise (the first 20 s of every minute), where the recorded
# moment is distinctive.
TIMES = [133.3, 255.7, 371.9, 492.4]


def errors(results):
    """How far off each seek landed (seconds), or None where what played
    wasn't found within half a second of where it should be."""
    return [round(actual - reported, 3) if match > .8 else None for reported, actual, match in results]


def test_compressed_clips_play_from_a_wav(page):
    page.evaluate("globalState.set('playingClip', globalState.get('clips').find(c => c.title == 'Bob'))")
    page.wait_for_function("$('audio.clip').src.startsWith('blob:')")
    # Already a WAV: played as it is.
    page.evaluate("globalState.set('playingClip', globalState.get('clips').find(c => c.title == 'Quinn'))")
    assert page.evaluate("$('audio.clip').src.startsWith('data:')")
    assert page.log.errors == []


def test_wav_encoding(page):
    header = page.evaluate("""async () => {
        const buffer = new AudioBuffer({numberOfChannels: 2, length: 4, sampleRate: 22050});
        buffer.copyToChannel(new Float32Array([0, 1, -1, .5]), 0);
        buffer.copyToChannel(new Float32Array([0, 1, 1, -2]), 1);
        const bytes = new DataView(await (await audioBufferToWav(buffer)).arrayBuffer());
        const text = (o, n) => String.fromCharCode(...Array.from({length: n}, (_, i) => bytes.getUint8(o + i)));
        return {riff: text(0, 4), wave: text(8, 4), channels: bytes.getUint16(22, true),
                rate: bytes.getUint32(24, true), bits: bytes.getUint16(34, true), size: bytes.byteLength,
                samples: [0, 1, 2, 3].map(i => bytes.getInt16(44 + i * 2, true))};
    }""")
    # Mono: the channels averaged (and clipped).
    assert header == {'riff': 'RIFF', 'wave': 'WAVE', 'channels': 1, 'rate': 22050, 'bits': 16,
                      'size': 44 + 8, 'samples': [0, 32767, 0, -24576]}


def test_seeking_lands_where_it_says(page, vbr_mp3):
    # The problem: an <audio> element playing the MP3 itself lands well off.
    direct = errors(page.evaluate(WHERE_IT_LANDS, {'audio': vbr_mp3, 'element': None, 'times': TIMES}))
    assert any(e is None for e in direct), f'this MP3 seeks accurately ({direct}): no test'

    page.evaluate("""audio => {
        const clip = {title: 'VBR', audio, phones: []};
        globalState.set('playingClip', clip);
    }""", vbr_mp3)
    page.wait_for_function("$('audio.clip').src.startsWith('blob:')", timeout=30_000)
    played = errors(page.evaluate(WHERE_IT_LANDS, {'audio': vbr_mp3, 'element': 'audio.clip', 'times': TIMES}))
    # What's left is the recorder's own delay, under a buffer or two.
    assert all(e is not None and abs(e) < .25 for e in played), played


def test_switching_keeps_the_position_and_playing(page):
    page.evaluate("""() => {
        const clip = globalState.get('clips').find(c => c.title == 'Morgan');
        playClipFrom(clip, 12);
    }""")
    page.wait_for_function("$('audio.clip').src.startsWith('blob:') && !$('audio.clip').paused")
    page.wait_for_timeout(300)
    time = page.evaluate("$('audio.clip').currentTime")
    assert 12 < time < 14
    assert page.evaluate("globalState.get('playing')")
    assert abs(page.evaluate("globalState.get('playbackTime')") - time) < .2
    assert page.log.errors == []
