"""Clips and settings stored on the device (ui/storage.js), and the
"Stored on this device" panel in the settings tab."""

from conftest import add_clip, wait_for_clip_or_alert


def reload(page):
    page.reload()
    page.wait_for_function("globalState.get('clips').length >= 7", timeout=60_000)


def user_clips(page):
    """Titles of the clips on screen that aren't examples."""
    return page.evaluate("globalState.get('clips').filter(c => !c.example).map(c => c.title)")


def stored_titles(page):
    return page.evaluate("clipStore.records().then(rs => rs.map(r => r.clip.title))")


def add_stored_clip(page, title):
    """A clip as if it had just been analysed (a copy of an example), saved
    the way new-clip.html saves one."""
    page.evaluate("""async title => {
        const example = globalState.get('clips').find(c => c.title && c.example && c.phones);
        const {marker, example: _, ...data} = example;
        const clip = {...data, title, id: title};
        globalState.mutate('clips', clips => clips.push(clip));
        await clipStore.saveIfWanted(clip);
    }""", title)


def open_settings(page):
    page.click('.tab-set button.settings')
    return page.locator('#stored-data')


def panel_titles(page):
    return page.locator('#stored-clips tbody td:first-child').all_text_contents()


def test_a_new_clip_is_still_there_after_a_reload(page, example):
    add_clip(page, 'Kept clip', example['audio_path'], example['transcript'])
    assert wait_for_clip_or_alert(page, 'Kept clip') is not None
    page.wait_for_function("clipStore.records().then(rs => rs.length == 1)")

    reload(page)
    assert user_clips(page) == ['Kept clip']
    clip = page.evaluate("globalState.get('clips').find(c => c.title == 'Kept clip')")
    assert clip['audio'].startswith('data:audio/')
    assert clip['transcript'] == example['transcript']
    # It's on the graph and can be selected.
    page.wait_for_selector(f".marker[data-id='{clip['id']}']", state='attached')
    assert page.log.errors == []


def test_examples_are_not_stored(page):
    assert stored_titles(page) == []
    open_settings(page)
    assert page.locator('#stored-clips-empty').is_visible()


def test_the_panel_lists_and_deletes_stored_clips(page):
    add_stored_clip(page, 'First')
    add_stored_clip(page, 'Second <b>bold</b>')
    open_settings(page)
    page.wait_for_function("document.querySelectorAll('#stored-clips tbody tr').length == 2")
    # Titles are shown as text, never as markup.
    assert panel_titles(page) == ['First', 'Second <b>bold</b>']
    assert page.locator('#stored-usage').text_content().startswith('2 clips, about ')

    page.locator('#stored-clips tbody tr', has_text='First').locator('button').click()
    page.wait_for_function("document.querySelectorAll('#stored-clips tbody tr').length == 1")
    assert user_clips(page) == ['Second <b>bold</b>']
    reload(page)
    assert user_clips(page) == ['Second <b>bold</b>']
    assert page.log.errors == []


def test_deleting_from_the_details_tab_deletes_the_stored_copy(page):
    add_stored_clip(page, 'Doomed')
    page.evaluate("globalState.set('previewClip', globalState.get('clips').find(c => c.title == 'Doomed'))")
    page.click('section.details button.delete')
    page.click('section.details button.delete')  # confirms
    page.wait_for_function("clipStore.records().then(rs => rs.length == 0)")
    reload(page)
    assert user_clips(page) == []


def test_saving_can_be_turned_off(page):
    open_settings(page)
    page.uncheck('#save-clips')
    add_stored_clip(page, 'Not kept')
    assert stored_titles(page) == []
    assert page.evaluate("localSettings.get('saveClips')") is False

    # The setting is remembered, listed, and can be reset.
    reload(page)
    open_settings(page)
    assert not page.is_checked('#save-clips')
    assert 'Save new clips on this device: false' in page.locator('#stored-settings').text_content()
    page.locator('.stored-setting button').click()
    assert page.is_checked('#save-clips')
    assert page.evaluate("localSettings.keys()") == []


def test_delete_everything(page):
    add_stored_clip(page, 'One')
    add_stored_clip(page, 'Two')
    open_settings(page)
    page.uncheck('#save-clips')
    page.evaluate("window.confirm = () => true")
    page.click('#delete-stored')
    page.wait_for_function("clipStore.records().then(rs => rs.length == 0)")
    assert user_clips(page) == []
    assert page.evaluate("localSettings.keys()") == []
    assert page.is_checked('#save-clips')
    # The examples stay.
    assert page.evaluate("globalState.get('clips').length") >= 7


def test_the_app_works_without_storage(browser, site_url, example):
    """With storage blocked (some private windows), clips just aren't kept."""
    context = browser.new_context()
    context.add_init_script("""
        Object.defineProperty(window, 'indexedDB', {get() { throw new DOMException('blocked', 'SecurityError'); }});
        Object.defineProperty(window, 'localStorage', {get() { throw new DOMException('blocked', 'SecurityError'); }});
    """)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(site_url)
    page.wait_for_function("globalState.get('clips').length >= 7", timeout=60_000)
    add_stored_clip(page, 'Unkept')
    assert user_clips(page) == ['Unkept']
    open_settings(page)
    page.wait_for_selector('#stored-unavailable', state='visible')
    assert page.is_checked('#save-clips')
    assert errors == []
    context.close()


def body_var(page, name):
    return page.evaluate("n => document.body.style.getPropertyValue('--' + n)", name)


def test_the_theme_is_kept(page):
    open_settings(page)
    page.select_option('#theme-select', 'Light Blue')
    assert body_var(page, 'body-background') == '#ffffff'
    reload(page)
    assert page.input_value('#theme-select') == 'Light Blue'
    assert body_var(page, 'body-background') == '#ffffff'

    open_settings(page)
    setting = page.locator('.stored-setting', has_text='Theme')
    assert setting.locator('span').text_content() == 'Theme: "Light Blue"'
    setting.locator('button').click()
    assert page.input_value('#theme-select') == 'Deep Dark'
    assert body_var(page, 'body-background') != '#ffffff'
    assert page.evaluate("localSettings.get('theme')") is None


def test_a_customised_theme_is_kept(page):
    open_settings(page)
    page.click('#set-colors summary')
    page.fill('#body-background', '#123456')
    assert page.input_value('#theme-select') == 'custom'
    reload(page)
    assert page.input_value('#theme-select') == 'custom'
    assert body_var(page, 'body-background') == '#123456'
    assert page.input_value('#body-background') == '#123456'
    # Picking Custom again keeps it; picking a named theme replaces it.
    open_settings(page)
    page.select_option('#theme-select', 'custom')
    assert body_var(page, 'body-background') == '#123456'
    page.select_option('#theme-select', 'Light Red')
    reload(page)
    assert page.input_value('#theme-select') == 'Light Red'
    assert page.log.errors == []


def test_spectrogram_axes_are_kept(page):
    defaults = [page.input_value(f'#preview-{n}') for n in ('frequency-scale', 'min-frequency', 'max-frequency')]
    page.select_option('#preview-frequency-scale', 'linear')
    page.select_option('#preview-min-frequency', '0')
    page.select_option('#preview-max-frequency', '2000')
    reload(page)
    assert page.input_value('#preview-frequency-scale') == 'linear'
    assert page.input_value('#preview-max-frequency') == '2000'
    assert page.get_attribute('#preview-spectrogram', 'max-frequency') == '2000'
    # Only the details spectrogram; the recording one keeps its own.
    assert page.get_attribute('#live-spectrogram', 'max-frequency') == '1000'

    open_settings(page)
    page.locator('.stored-setting', has_text='Spectrogram axes').locator('button').click()
    assert [page.input_value(f'#preview-{n}') for n in ('frequency-scale', 'min-frequency', 'max-frequency')] == defaults
