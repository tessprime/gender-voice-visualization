"""<voice-spectrogram> on its own (components/voice-spectrogram/)."""

import subprocess

import pytest

from conftest import REPO

COMPONENT = REPO / 'components' / 'voice-spectrogram'


@pytest.fixture
def demo(browser, repo_url):
    page = browser.new_page(viewport={'width': 1000, 'height': 800})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(repo_url + 'components/voice-spectrogram/demo.html')
    page.wait_for_function("document.querySelector('#dark').duration > 0")
    page.errors = errors
    yield page
    page.close()


def test_loads_without_a_browser():
    # As in server-side rendering (e.g. Next.js): importing must not throw.
    subprocess.run(['node', '--input-type=module', '-e',
                    "await import('./voice-spectrogram.js'); await import('./spectrogram.js');"],
                   cwd=COMPONENT, check=True)


def test_a_tone_shows_at_its_frequency(demo):
    peak = demo.evaluate("""async () => {
        const {computeSpectrogram} = await import('./spectrogram.js');
        const rate = 16000, samples = new Float32Array(rate);
        for (let i = 0; i < samples.length; i++) samples[i] = Math.sin(2 * Math.PI * 1000 * i / rate);
        const s = computeSpectrogram(samples, rate);
        const middle = Math.floor(s.columns / 2) * s.bins;
        let best = 0;
        for (let k = 0; k < s.bins; k++) if (s.data[middle + k] > s.data[middle + best]) best = k;
        return best * s.binHz;
    }""")
    assert abs(peak - 1000) <= 70


def test_draws_the_spectrogram(demo):
    demo.wait_for_function("document.querySelector('#dark')._image")
    lit = demo.evaluate("""() => {
        const canvas = document.querySelector('#dark').shadowRoot.querySelector('canvas');
        const {data} = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
        let lit = 0;
        for (let i = 0; i < data.length; i += 4) if (data[i] + data[i + 1] + data[i + 2] > 300) lit++;
        return lit / (data.length / 4);
    }""")
    assert 0.05 < lit < 0.9
    assert demo.errors == []


def test_highlights_the_word_and_phone_at_the_cursor(demo):
    current = demo.evaluate("""() => {
        const view = document.querySelector('#dark');
        view.currentTime = 1.3;
        return Array.from(view.shadowRoot.querySelectorAll('.segment.current')).map(s => s.textContent);
    }""")
    assert current == ['/i/', 'I']


def test_clicking_a_word_seeks_to_its_start(demo):
    demo.evaluate("""() => {
        window.seeks = [];
        document.querySelector('#dark').addEventListener('seek', e => window.seeks.push(e.detail));
    }""")
    demo.locator('#dark').locator('.words .segment', has_text='/u/').click()
    seeks = demo.evaluate('window.seeks')
    assert seeks[0]['time'] == pytest.approx(1.8)
    assert seeks[0]['segment']['tier'] == 'word'
    assert seeks[0]['segment']['label'] == '/u/'


def test_clicking_the_spectrogram_seeks_there(demo):
    demo.evaluate("""() => {
        window.seeks = [];
        document.querySelector('#dark').addEventListener('seek', e => window.seeks.push(e.detail));
    }""")
    plot = demo.locator('#dark').locator('.plot')
    box = plot.bounding_box()
    plot.click(position={'x': box['width'] / 4, 'y': box['height'] / 2})
    duration = demo.evaluate("document.querySelector('#dark').duration")
    assert demo.evaluate('window.seeks')[0]['time'] == pytest.approx(duration / 4, abs=0.02)


def test_properties_set_before_the_element_is_defined_apply(browser, repo_url):
    # As when a framework renders the tag first and loads the module later.
    page = browser.new_page()
    page.goto(repo_url + 'components/voice-spectrogram/')
    labels = page.evaluate("""async () => {
        const view = document.createElement('voice-spectrogram');
        document.body.appendChild(view);
        view.words = [{start: 0, end: 1, label: 'early'}];
        view.currentTime = .5;
        await import('./voice-spectrogram.js');
        return Array.from(view.shadowRoot.querySelectorAll('.segment.current')).map(s => s.textContent);
    }""")
    page.close()
    assert labels == ['early']


def test_computes_only_once_visible(browser, repo_url):
    page = browser.new_page()
    page.goto(repo_url + 'components/voice-spectrogram/')
    result = page.evaluate("""async () => {
        await import('./voice-spectrogram.js');
        const view = document.createElement('voice-spectrogram');
        view.hidden = true;
        document.body.appendChild(view);
        let renders = 0;
        view.addEventListener('render', () => renders++);
        for (const hz of [200, 300, 400]) {    // several recordings in a row
            const samples = new Float32Array(16000).map((_, i) => Math.sin(2 * Math.PI * hz * i / 16000));
            view.audio = {samples, sampleRate: 16000};
        }
        await new Promise(r => setTimeout(r, 100));
        const whileHidden = renders;
        view.hidden = false;
        await new Promise(r => view.addEventListener('render', r, {once: true}));
        return {whileHidden, afterShowing: renders, duration: view.duration};
    }""")
    page.close()
    assert result == {'whileHidden': 0, 'afterShowing': 1, 'duration': 1}


def test_view_duration_shows_part_and_follows_the_cursor(demo):
    view = demo.evaluate("""() => {
        const view = document.querySelector('#dark');
        view.setAttribute('view-duration', '1');
        const initial = [view.viewStart, view.viewEnd];
        view.currentTime = 2.0;
        const shown = Array.from(view.shadowRoot.querySelectorAll('.words .segment'))
            .filter(s => s.style.display != 'none').map(s => s.textContent);
        return {initial, after: [view.viewStart, view.viewEnd], shown};
    }""")
    assert view['initial'] == [0, 1]
    assert view['after'][0] < 2.0 < view['after'][1]
    assert view['shown'] == ['/u/']


def test_dragging_scrolls_without_seeking(demo):
    demo.evaluate("""() => {
        const view = document.querySelector('#dark');
        view.setAttribute('view-duration', '1');
        window.seeks = [];
        view.addEventListener('seek', e => window.seeks.push(e.detail));
    }""")
    box = demo.locator('#dark').locator('.plot').bounding_box()
    y = box['y'] + box['height'] / 2
    demo.mouse.move(box['x'] + box['width'] * .8, y)
    demo.mouse.down()
    demo.mouse.move(box['x'] + box['width'] * .3, y, steps=5)
    demo.mouse.up()
    start = demo.evaluate("document.querySelector('#dark').viewStart")
    assert start == pytest.approx(0.5, abs=0.05)
    assert demo.evaluate('window.seeks') == []


def test_ctrl_wheel_zooms_around_the_pointer(demo):
    box = demo.locator('#dark').locator('.plot').bounding_box()
    demo.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    before = demo.evaluate("[document.querySelector('#dark').viewStart, document.querySelector('#dark').viewEnd]")
    demo.keyboard.down('Control')
    demo.mouse.wheel(0, -100)
    demo.keyboard.up('Control')
    after = demo.evaluate("[document.querySelector('#dark').viewStart, document.querySelector('#dark').viewEnd]")
    assert after[1] - after[0] < (before[1] - before[0]) / 2
    assert (after[0] + after[1]) / 2 == pytest.approx((before[0] + before[1]) / 2, abs=0.05)


def test_scale_changes_only_compute_what_is_missing(demo):
    result = demo.evaluate("""async () => {
        const view = document.querySelector('#dark');
        await new Promise(r => view._image ? r() : view.addEventListener('render', r, {once: true}));
        let renders = 0;
        view.addEventListener('render', () => renders++);
        const settle = () => new Promise(r => setTimeout(r, 50));
        const steps = {};
        for (const scale of ['3000', '1000', '500', '4000', '1000']) {
            view.setAttribute('max-frequency', scale);
            await settle();
            steps[scale] = renders;
        }
        const labels = Array.from(view.shadowRoot.querySelectorAll('.axis span')).map(s => s.textContent);
        return {steps, top: labels[labels.length - 1]};
    }""")
    # 3000 redraws the broadband one; 1000 computes the narrowband one (and
    # the pitch); 500, 4000 and back to 1000 reuse what's computed.
    assert result == {'steps': {'3000': 0, '1000': 1, '500': 1, '4000': 1}, 'top': '1 kHz'}


def test_low_scales_resolve_harmonics(demo):
    # A 150 Hz buzz: at 1 kHz the narrowband spectrogram separates its
    # harmonics (peaks at 150, 300, 450 Hz with dips between); broadband
    # blurs them together.
    contrast = demo.evaluate("""async () => {
        const rate = 16000, samples = new Float32Array(rate);
        for (let i = 0; i < samples.length; i++)
            for (let h = 1; h <= 6; h++) samples[i] += Math.sin(2 * Math.PI * 150 * h * i / rate) / h;
        const view = document.querySelector('#dark');
        const result = {};
        for (const scale of ['5000', '1000']) {
            view.setAttribute('max-frequency', scale);
            view.audio = {samples, sampleRate: rate};
            await new Promise(r => view.addEventListener('render', r, {once: true}));
            const a = view._current().spectrogram;
            const middle = Math.floor(a.columns / 2) * a.bins;
            const at = hz => a.data[middle + Math.round(hz / a.binHz)];
            result[scale] = at(300) - at(225);   // harmonic vs between two
        }
        return result;
    }""")
    assert contrast['1000'] > 15     # dB: clearly separated
    assert contrast['5000'] < 6      # blurred


def test_pitch_track_drawn_at_low_scales(demo):
    track = demo.evaluate("""async () => {
        const view = document.querySelector('#dark');
        await new Promise(r => view._image ? r() : view.addEventListener('render', r, {once: true}));
        const before = view.showPitch;
        view.setAttribute('max-frequency', '1000');
        await new Promise(r => view.addEventListener('render', r, {once: true}));
        const voiced = view.pitchTrack.filter(p => p.hz);
        return {before, after: view.showPitch, median: voiced.map(p => p.hz).sort((a, b) => a - b)[voiced.length >> 1]};
    }""")
    # The demo's synthetic vowels have a 140 Hz pitch.
    assert track['before'] is False and track['after'] is True
    assert track['median'] == pytest.approx(140, rel=0.02)


def test_host_pitch_track_replaces_the_computed_one(demo):
    hz = demo.evaluate("""() => {
        const view = document.querySelector('#dark');
        view.pitchTrack = [{time: 1.0, hz: 222}];
        return view.pitchTrack.map(p => p.hz);
    }""")
    assert hz == [222]


def test_ctrl_wheel_over_the_axis_changes_the_scale(demo):
    demo.evaluate("""() => {
        window.scales = [];
        document.querySelector('#dark').addEventListener('scalechange', e => window.scales.push(e.detail.maxFrequency));
    }""")
    axis = demo.locator('#dark').locator('.axis').bounding_box()
    demo.mouse.move(axis['x'] + axis['width'] / 2, axis['y'] + axis['height'] / 2)
    demo.keyboard.down('Control')
    demo.mouse.wheel(0, -100)
    demo.keyboard.up('Control')
    scales = demo.evaluate('window.scales')
    assert len(scales) == 1 and scales[0] < 5000
    assert demo.evaluate("document.querySelector('#dark').maxFrequency") == scales[0]
    # Time zoom is unchanged.
    assert demo.evaluate("[document.querySelector('#dark').viewStart, document.querySelector('#dark').viewEnd]") \
        == [0, pytest.approx(2.6)]


def test_log_axis_from_a_minimum(demo):
    result = demo.evaluate("""async () => {
        const view = document.querySelector('#dark');
        view.setAttribute('max-frequency', '1000');
        await new Promise(r => view.addEventListener('render', r, {once: true}));
        let renders = 0;
        view.addEventListener('render', () => renders++);
        view.setAttribute('frequency-scale', 'log');
        view.setAttribute('min-frequency', '75');
        await new Promise(r => setTimeout(r, 50));
        const labels = Array.from(view.shadowRoot.querySelectorAll('.axis span')).map(s => s.textContent);
        return {renders, scale: view.frequencyScale, labels};
    }""")
    assert result['renders'] == 0          # repainted, not recomputed
    assert result['scale'] == {'min': 75, 'max': 1000, 'log': True}
    # 75 Hz would crowd 100 Hz, so the axis starts labelling at 100.
    assert result['labels'][0] == '100 Hz' and result['labels'][-1] == '1 kHz'
    assert '150 Hz' in result['labels'] and '75 Hz' not in result['labels']


def test_log_axis_defaults_its_minimum(demo):
    scale = demo.evaluate("""() => {
        const view = document.querySelector('#dark');
        view.setAttribute('frequency-scale', 'log');
        return view.frequencyScale;
    }""")
    assert scale == {'min': 75, 'max': 5000, 'log': True}
