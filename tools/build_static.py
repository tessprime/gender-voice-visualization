#!/usr/bin/env python3
"""Build the app as static files, for hosting without a server-side
backend: everything, including analysing recordings, runs in the browser.

    tools/setup_browser_analysis.sh   # once: WASM modules and models
    tools/build_static.py [OUT_DIR]   # default: dist/

Then serve OUT_DIR from any static web server over HTTPS (browsers only
allow microphone recording on HTTPS or localhost). See docs/STATIC.md.
"""
import json
import os
import shutil
import sys

from jinja2 import Environment, FileSystemLoader

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, 'dist'))
os.chdir(root)

# Files the in-browser analysis needs, made by tools/setup_browser_analysis.sh.
generated = ['ui/wasm/voicealign.wasm', 'ui/wasm/voicemeasure.wasm',
             'models/final.alimdl', 'models/tree', 'models/lda.mat', 'models/phones.txt', 'models/english.dict']
missing = [f for f in generated if not os.path.exists(f)]
if missing:
	sys.exit(f"missing {', '.join(missing)}: run tools/setup_browser_analysis.sh first")

if os.path.exists(out):
	shutil.rmtree(out)
os.makedirs(out)

# The page, with its scripts and styles inlined (dev=False), and no server
# to fall back on.
env = Environment(loader=FileSystemLoader(['./ui', './resources']))
themes = json.load(open('resources/themes.json'))
page = env.get_template('base.html').render(dev=False, theme=themes['Deep Dark'], server_analysis=False)
with open(os.path.join(out, 'index.html'), 'w') as f:
	f.write(page)

# Everything else the page loads.
files = generated + ['ui/analysis-worker.js', 'ui/scoring.js', 'cmudict.txt', 'stats.json',
                     'manifest.json', 'sw.js', 'offline.html',
                     'components/voice-spectrogram/voice-spectrogram.js',
                     'components/voice-spectrogram/spectrogram.js',
                     'components/voice-spectrogram/voice-live-spectrogram.js',
                     'components/voice-spectrogram/pitch.js']
for path in files:
	os.makedirs(os.path.dirname(os.path.join(out, path)) or out, exist_ok=True)
	shutil.copy2(path, os.path.join(out, path))
shutil.copytree('resources', os.path.join(out, 'resources'))

size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(out) for f in fs)
count = sum(len(fs) for _, _, fs in os.walk(out))
print(f'{out}: {count} files, {size / 1e6:.0f} MB')
