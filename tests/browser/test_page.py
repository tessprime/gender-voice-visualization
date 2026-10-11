"""The page loads cleanly, with its example clips."""

import os

import pytest

DEFAULT_EXAMPLES = {'All Around', 'Quinn', 'Charlotte', 'Jenn', 'Lucy', 'Bob', 'Morgan'}


def test_loads_without_errors(page):
    page.wait_for_load_state('networkidle')
    assert page.log.errors == []
    assert page.log.failed == []
    assert page.log.non_get == []


def test_shows_the_example_clips(page):
    page.wait_for_function(f"globalState.get('clips').length >= {len(DEFAULT_EXAMPLES)}")
    titles = page.evaluate("globalState.get('clips').map(c => c.title)")
    assert DEFAULT_EXAMPLES <= set(titles)
    assert page.locator('.marker').count() >= len(DEFAULT_EXAMPLES)


def test_static_build_has_no_server_fallback(page):
    if os.environ.get('GVV_URL'):
        pytest.skip('testing another deployment, which may have a server')
    assert page.evaluate('serverAnalysisAvailable') is False
