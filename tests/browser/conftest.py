"""Shared setup for the browser tests.

The tests run the real page in real browsers with Playwright. By default
they serve the static build (dist/, from tools/build_static.py) with a plain
static file server, the way GitHub Pages does; set GVV_URL to test something
already running instead (e.g. http://127.0.0.1:8000/ for serve.py, or the
deployed site).

GVV_BROWSERS picks the engines, comma-separated (default: chromium; also
firefox and webkit).
"""

import base64
import functools
import http.server
import json
import os
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
DIST = REPO / 'dist'

# Example clip used as test input: 8 s, 23 words, a WAV file.
EXAMPLE = 'fern'

# Analysis loads a ~60 MB model the first time on each page.
ANALYSIS_TIMEOUT_MS = 120_000


def pytest_generate_tests(metafunc):
    if 'browser_name' in metafunc.fixturenames:
        names = os.environ.get('GVV_BROWSERS', 'chromium').split(',')
        metafunc.parametrize('browser_name', [n.strip() for n in names], scope='session')


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@pytest.fixture(scope='session')
def site_url():
    if os.environ.get('GVV_URL'):
        yield os.environ['GVV_URL'].rstrip('/') + '/'
        return
    if not (DIST / 'index.html').exists():
        pytest.exit('dist/ is missing: run tools/setup_browser_analysis.sh and '
                    'tools/build_static.py first, or set GVV_URL', returncode=2)
    handler = functools.partial(QuietHandler, directory=str(DIST))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}/'
    server.shutdown()


@pytest.fixture(scope='session')
def playwright_instance():
    with sync_playwright() as p:
        yield p


# Each engine's way of giving the page a fake microphone without asking.
LAUNCH_OPTIONS = {
    'chromium': {'args': ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream']},
    'firefox': {'firefox_user_prefs': {'media.navigator.streams.fake': True,
                                       'media.navigator.permission.disabled': True}},
    'webkit': {},
}


@pytest.fixture(scope='session')
def browser(playwright_instance, browser_name):
    browser = getattr(playwright_instance, browser_name).launch(**LAUNCH_OPTIONS[browser_name])
    yield browser
    browser.close()


class PageLog:
    """What happened on a page that a test may want to check."""

    def __init__(self):
        self.errors = []      # uncaught exceptions and console.error
        self.failed = []      # responses with status >= 400
        self.non_get = []     # requests other than GET (uploads)
        self.dialogs = []     # alert() messages; dismissed automatically


@pytest.fixture
def page(browser, browser_name, site_url):
    """The app, loaded, with its example clips. Fails the test on page errors."""
    context = browser.new_context(
        viewport={'width': 1400, 'height': 900},
        permissions=['microphone'] if browser_name == 'chromium' else [])
    page = context.new_page()
    log = PageLog()
    page.on('pageerror', lambda e: log.errors.append(f'pageerror: {e}'))
    page.on('console', lambda m: m.type == 'error' and log.errors.append(f'console.error: {m.text}'))
    page.on('response', lambda r: r.status >= 400 and log.failed.append(f'{r.status} {r.url}'))
    page.on('request', lambda r: r.method != 'GET' and log.non_get.append(f'{r.method} {r.url}'))
    page.on('dialog', lambda d: (log.dialogs.append(d.message), d.dismiss()))
    page.log = log

    page.goto(site_url)
    # all.json plus the six default examples.
    page.wait_for_function("globalState.get('clips').length >= 7", timeout=60_000)
    yield page
    context.close()


@pytest.fixture(scope='session')
def example(tmp_path_factory):
    """An example clip: its stored analysis, and its audio as a file."""
    clip = json.loads((REPO / 'resources' / f'{EXAMPLE}.json').read_text())
    audio = base64.b64decode(clip['audio'].split(',', 1)[1])
    path = tmp_path_factory.mktemp('audio') / f'{EXAMPLE}.wav'
    path.write_bytes(audio)
    clip['audio_path'] = path
    return clip


def add_clip(page, title, audio_path, transcript):
    """Add a clip through the "Add a Clip" dialog, uploading a file."""
    page.click('button.new-clip')
    page.fill('#title-input', title)
    page.fill('#transcript', transcript)
    page.dispatch_event('#transcript', 'change')
    page.check('#upload-file')
    page.set_input_files('#audio-file-input', str(audio_path))
    page.click('#submit')


def find_clip(page, title):
    """A clip's analysis (without its audio), or None."""
    return page.evaluate("""title => {
        const clip = globalState.get('clips').find(c => c.title == title);
        if (!clip) return null;
        const {audio, marker, indexedPhones, ...rest} = clip;
        return JSON.parse(JSON.stringify(rest));
    }""", title)


def wait_for_clip_or_alert(page, title):
    page.wait_for_function(
        "title => globalState.get('clips').some(c => c.title == title)"
        " || !$('button.new-clip').classList.contains('hidden')",
        arg=title, timeout=ANALYSIS_TIMEOUT_MS)
    return find_clip(page, title)
