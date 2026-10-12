"""<voice-live-spectrogram> on its own, fed from Web Audio streams (no
microphone needed)."""

import math
import subprocess

import pytest

from conftest import REPO

COMPONENT = REPO / 'components' / 'voice-spectrogram'


@pytest.fixture
def demo(browser, repo_url):
    page = browser.new_page(viewport={'width': 1000, 'height': 1100})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
    page.goto(repo_url + 'components/voice-spectrogram/demo.html')
    page.wait_for_function("!!customElements.get('voice-live-spectrogram')")
    page.errors = errors
    yield page
    page.evaluate("document.querySelector('#live').stream = null")
    page.close()


def test_loads_without_a_browser():
    subprocess.run(['node', '--input-type=module', '-e',
                    "await import('./voice-live-spectrogram.js'); await import('./pitch.js');"],
                   cwd=COMPONENT, check=True)


def test_tracks_a_gliding_pitch(demo):
    # The demo's test voice glides linearly 120 -> 280 Hz over 2 s, and back.
    pitches = demo.evaluate("""async () => {
        const live = document.querySelector('#live');
        const pitches = [];
        live.addEventListener('pitch', e => pitches.push([e.detail.time, e.detail.hz]));
        live.stream = startTestVoice();
        await new Promise(r => setTimeout(r, 3000));
        return pitches;
    }""")
    expected = lambda t: 120 + 160 * t / 2 if t <= 2 else 280 - 160 * (t - 2) / 2
    voiced = [(t, hz) for t, hz in pitches if hz and 0.2 < t < 2.8]
    assert len(voiced) > 0.9 * len([1 for t, _ in pitches if 0.2 < t < 2.8]) > 200
    errors = sorted(abs(hz / expected(t) - 1) for t, hz in voiced)
    assert errors[len(errors) // 2] < 0.02          # median within 2%
    assert errors[int(len(errors) * .95)] < 0.05     # 95% within 5%
    assert demo.errors == []


def test_a_tone_is_drawn_at_its_frequency(demo):
    row = demo.evaluate("""async () => {
        const live = document.querySelector('#live');
        const context = new AudioContext();
        const tone = context.createOscillator();
        tone.frequency.value = 300;
        const destination = context.createMediaStreamDestination();
        tone.connect(destination);
        tone.start();
        live.stream = destination.stream;
        await new Promise(r => setTimeout(r, 1500));
        live.stream = null;
        // The brightest row of the newest column, as a frequency.
        const {frequencyAt} = await import('./spectrogram.js');
        const h = live._history;
        const rows = h.image.height;
        const column = h.context.getImageData((h.write + h.columns - 2) % h.columns, 0, 1, rows).data;
        let best = 0, bestValue = -1;
        for (let y = 0; y < rows; y++) {
            const value = column[y * 4] + column[y * 4 + 1] + column[y * 4 + 2];
            if (value > bestValue) { bestValue = value; best = y; }
        }
        return frequencyAt(1 - (best + .5) / rows, live.frequencyScale);
    }""")
    assert row == pytest.approx(300, abs=10)


def test_log_axis_puts_octaves_at_equal_heights(demo):
    result = demo.evaluate("""async () => {
        const live = document.querySelector('#live');
        live.setAttribute('frequency-scale', 'log');
        live.setAttribute('min-frequency', '100');
        live.setAttribute('max-frequency', '800');
        const position = label => parseFloat(Array.from(live.shadowRoot.querySelectorAll('.axis span'))
            .find(s => s.textContent == label).style.top);
        return {scale: live.frequencyScale, gaps: [position('100 Hz') - position('200 Hz'),
                                                   position('200 Hz') - position('500 Hz')]};
    }""")
    assert result['scale'] == {'min': 100, 'max': 800, 'log': True}
    # 100-800 Hz is 3 octaves: an octave takes a third of the height, and
    # 200-500 Hz log2(2.5) thirds.
    assert result['gaps'][0] == pytest.approx(100 / 3, abs=0.5)
    assert result['gaps'][1] == pytest.approx(100 / 3 * math.log2(2.5), abs=0.5)


def test_changing_the_scale_keeps_the_picture(demo):
    result = demo.evaluate("""async () => {
        const live = document.querySelector('#live');
        live.stream = startTestVoice();
        await new Promise(r => setTimeout(r, 800));
        const before = live._history.write;
        live.setAttribute('max-frequency', '500');
        const labels = Array.from(live.shadowRoot.querySelectorAll('.axis span')).map(s => s.textContent);
        return {kept: live._history.write >= before, top: labels[labels.length - 1]};
    }""")
    assert result == {'kept': True, 'top': '500 Hz'}


def test_stopping_keeps_the_picture_until_cleared(demo):
    result = demo.evaluate("""async () => {
        const live = document.querySelector('#live');
        live.stream = startTestVoice();
        await new Promise(r => setTimeout(r, 800));
        live.stream = null;
        const afterStop = [live.pitch, !!live._history];
        live.clear();
        return [...afterStop, !!live._history];
    }""")
    assert result == [None, True, False]
