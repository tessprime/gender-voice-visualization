"""Transcription endpoints (ui/transcription.js): the editor in the settings
tab, and transcribing from the Add a Clip dialog. The server is faked with
Playwright routes."""

import json

from test_storage import reload

URL = 'http://whisper.test/v1/audio/transcriptions'
CORS = {'access-control-allow-origin': '*', 'access-control-allow-headers': '*',
        'access-control-allow-methods': 'GET, POST, OPTIONS'}


def fake_server(page, text='Hello there.', status=200, models=('fake/whisper-small', 'fake/tts'),
                words=None, verbose=True):
    """Answer like an OpenAI-style server; returns the transcription
    requests it got. words, [(word, probability)], go in verbose_json
    replies; with verbose=False the server rejects verbose_json as
    OpenAI's newer models do."""
    requests = []

    def handle(route):
        request = route.request
        if request.method == 'OPTIONS':
            return route.fulfill(status=204, headers=CORS)
        if request.url.endswith('/v1/models'):
            data = [{'id': m, 'task': 'automatic-speech-recognition' if 'whisper' in m else 'text-to-speech'}
                    for m in models]
            return route.fulfill(status=200, headers=CORS, content_type='application/json',
                                 body=json.dumps({'data': data, 'object': 'list'}))
        requests.append({'headers': request.headers, 'body': request.post_data_buffer})
        if status != 200:
            return route.fulfill(status=status, headers=CORS, content_type='application/json',
                                 body=json.dumps({'error': {'message': 'Invalid API key'}}))
        body = {'text': text}
        if field(request.post_data_buffer, 'response_format') == 'verbose_json':
            if not verbose:
                return route.fulfill(status=400, headers=CORS, content_type='application/json',
                                     body=json.dumps({'error': {'message': 'response_format not supported'}}))
            if words is not None:
                body['words'] = [{'word': w, 'start': 0, 'end': 0, 'probability': p} for w, p in words]
        return route.fulfill(status=200, headers=CORS, content_type='application/json',
                             body=json.dumps(body))

    page.route('http://whisper.test/**', handle)
    return requests


def open_settings(page):
    if page.is_enabled('.tab-set button.settings'):
        page.click('.tab-set button.settings')


def add_endpoint(page, name='Test Whisper', url=URL, model='', key=''):
    open_settings(page)
    page.click('#add-endpoint')
    page.fill('#endpoint-name', name)
    page.fill('#endpoint-url', url)
    page.fill('#endpoint-model', model)
    page.fill('#endpoint-key', key)
    page.click('#save-endpoint')


def open_dialog_with_file(page, example):
    page.click('button.new-clip')
    page.check('#upload-file')
    page.set_input_files('#audio-file-input', str(example['audio_path']))


def transcribe(page):
    page.click('#transcribe')
    page.wait_for_function("!$('#transcribe').disabled && $('#transcribe-status').textContent != ''")
    return page.text_content('#transcribe-status')


def field(body, name):
    """A multipart form field's value."""
    marker = f'name="{name}"'.encode()
    start = body.index(marker)
    value_start = body.index(b'\r\n\r\n', start) + 4
    return body[value_start:body.index(b'\r\n--', value_start)].decode(errors='replace')


def test_without_endpoints_the_dialog_links_to_the_editor(page):
    page.click('button.new-clip')
    assert not page.is_visible('#transcribe-row')
    page.click('#open-endpoint-editor')
    # The dialog closes, and the settings tab opens on a new endpoint.
    assert 'hidden' in page.get_attribute('.modal-shadow', 'class')
    assert page.is_visible('#endpoint-form')
    assert page.evaluate("document.activeElement.id") == 'endpoint-url'
    assert page.log.errors == []


def test_adding_checking_and_keeping_an_endpoint(page):
    fake_server(page)
    page.click('.tab-set button.settings')
    page.click('#add-endpoint')
    page.fill('#endpoint-url', URL)
    page.click('#check-endpoint')
    page.wait_for_function("$('#endpoint-status').textContent.startsWith('Connected')")
    # Speech models first.
    assert page.text_content('#endpoint-status') == 'Connected. Models: fake/whisper-small, fake/tts.'
    page.click('#save-endpoint')
    assert page.locator('#endpoint-list li strong').all_text_contents() == ['whisper.test']
    assert 'OpenAI' in page.text_content('#endpoint-list li small')

    reload(page)
    page.click('button.new-clip')
    assert page.is_visible('#transcribe-row')
    assert not page.is_visible('#no-transcription-endpoints')
    assert page.locator('#transcription-endpoint option').all_text_contents() == ['whisper.test']


def test_transcribing_fills_in_the_transcript(page, example):
    requests = fake_server(page, text='  That quick beige fox.  ')
    add_endpoint(page)
    open_dialog_with_file(page, example)
    assert transcribe(page).startswith('Done')
    assert page.input_value('#transcript') == 'That quick beige fox.'
    assert page.input_value('#script-select') == 'custom'
    assert page.evaluate("globalState.get('transcript')") == 'That quick beige fox.'

    [request] = requests
    body = request['body']
    # No model set: the server's first speech model.
    assert field(body, 'model') == 'fake/whisper-small'
    assert field(body, 'response_format') == 'verbose_json'
    assert field(body, 'timestamp_granularities[]') == 'word'
    assert b'filename="fern.wav"' in body
    assert 'authorization' not in request['headers']
    assert page.log.errors == []


def test_model_and_api_key_are_sent(page, example):
    requests = fake_server(page)
    add_endpoint(page, model='my-model', key='sk-test')
    open_dialog_with_file(page, example)
    transcribe(page)
    [request] = requests
    assert field(request['body'], 'model') == 'my-model'
    assert request['headers']['authorization'] == 'Bearer sk-test'
    # The panel doesn't show the key.
    assert 'sk-test' not in page.text_content('section.settings')


def test_errors_are_explained(page, example):
    fake_server(page, status=401)
    add_endpoint(page)
    page.click('button.new-clip')
    page.check('#upload-file')
    page.set_input_files('#audio-file-input', [])
    assert transcribe(page) == 'Record your voice or choose a file first.'

    page.set_input_files('#audio-file-input', str(example['audio_path']))
    assert transcribe(page) == 'whisper.test answered 401 (check the API key): Invalid API key'

    page.unroute('http://whisper.test/**')
    page.route('http://whisper.test/**', lambda route: route.abort())
    assert transcribe(page).startswith("Couldn't reach whisper.test:")
    # The transcript is left alone.
    assert page.input_value('#transcript') != ''


def test_editing_choosing_and_deleting_endpoints(page):
    add_endpoint(page, name='First')
    add_endpoint(page, name='Second', url='http://other.test/v1/audio/transcriptions')
    page.click('button.new-clip')
    page.select_option('#transcription-endpoint', label='Second')

    reload(page)
    page.click('button.new-clip')
    assert page.locator('#transcription-endpoint option:checked').text_content() == 'Second'
    page.evaluate("hideModal()")

    open_settings(page)
    page.locator('#endpoint-list li', has_text='First').locator('.edit-endpoint').click()
    assert page.input_value('#endpoint-name') == 'First'
    page.fill('#endpoint-name', 'Renamed')
    page.click('#save-endpoint')
    assert page.locator('#endpoint-list li strong').all_text_contents() == ['Renamed', 'Second']

    page.locator('#endpoint-list li', has_text='Second').locator('.delete-endpoint').click()
    assert page.locator('#endpoint-list li strong').all_text_contents() == ['Renamed']
    assert page.evaluate("localSettings.get('transcriptionEndpoint')") is None
    page.click('button.new-clip')
    assert page.locator('#transcription-endpoint option:checked').text_content() == 'Renamed'


QUINN_WORDS = [(' That', 0.59), (' quick', 0.98), ('-beach', 0.62), (' fox', 0.98), (' his', 0.74),
               (' full', 0.47), (' do', 0.75), (' again.', 0.99)]


def test_doubtful_words_are_marked(page, example):
    fake_server(page, text=' That quick-beach fox his full do again.', words=QUINN_WORDS)
    add_endpoint(page)
    open_dialog_with_file(page, example)
    assert transcribe(page) == ('Done: 5 words it was unsure of are marked below. '
                                'Check them against the recording and correct the transcript.')
    review = page.locator('#transcript-review')
    assert review.text_content() == 'That quick-beach fox his full do again.'
    assert review.locator('mark.check').all_text_contents() == ['That', '-beach', 'his', 'do']
    assert review.locator('mark.unsure').all_text_contents() == ['full']
    assert review.locator('mark.unsure').get_attribute('title') == '47% sure'

    # Editing the transcript removes the marks, which no longer match it.
    page.fill('#transcript', 'That quick beige fox, he\'s foiled you again.')
    assert 'hidden' in review.get_attribute('class')
    assert review.text_content() == ''
    assert page.log.errors == []


def test_no_marks_when_sure_or_not_told(page, example):
    fake_server(page, text='Hello there.', words=[(' Hello', 0.99), (' there.', 0.95)])
    add_endpoint(page)
    open_dialog_with_file(page, example)
    assert transcribe(page) == 'Done: check the transcript and correct anything it got wrong.'
    assert 'hidden' in page.get_attribute('#transcript-review', 'class')

    # A server that gives no probabilities (OpenAI's whisper-1).
    page.unroute('http://whisper.test/**')
    fake_server(page, text='Hello there.')
    assert "doesn't say which words" in transcribe(page)


def test_servers_without_verbose_json_still_work(page, example):
    requests = fake_server(page, text='Plain text.', verbose=False)
    add_endpoint(page)
    open_dialog_with_file(page, example)
    assert transcribe(page).startswith('Done')
    assert page.input_value('#transcript') == 'Plain text.'
    assert [field(r['body'], 'response_format') for r in requests] == ['verbose_json', 'json']
