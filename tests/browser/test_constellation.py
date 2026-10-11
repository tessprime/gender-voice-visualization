"""Hovering a clip fans it out into its vowels."""

CLIP = 'Morgan'


def open_constellation(page):
    page.wait_for_function("title => globalState.get('clips').some(c => c.title == title && c.marker)",
                           arg=CLIP)
    marker = page.evaluate_handle("title => globalState.get('clips').find(c => c.title == title).marker",
                                  CLIP)
    marker.as_element().hover()
    page.wait_for_selector('.constellation .vowel-dot')


def test_hovering_a_clip_shows_its_vowels(page):
    open_constellation(page)
    expected = page.evaluate("title => vowelGroups(globalState.get('clips').find(c => c.title == title)).length",
                             CLIP)
    assert page.locator('.constellation .vowel-dot').count() == expected > 0


def test_hovering_a_vowel_shows_each_instance(page):
    open_constellation(page)
    dot = page.locator('.constellation .vowel-dot').first
    dot.hover()
    page.wait_for_selector('.constellation .vowel-instance.shown')
    assert page.locator('.constellation .vowel-instance.shown').count() >= 1


def test_closes_after_the_pointer_leaves(page):
    open_constellation(page)
    page.mouse.move(5, 5)
    page.wait_for_selector('.constellation', state='detached', timeout=3000)

