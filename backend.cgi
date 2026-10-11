#!/usr/bin/env python3

import os, json, hashlib, datetime
import cgi, cgitb   # I like cgi because it was popular when I was born
import maxminddb

import acousticgender
from acousticgender.library.analysis import analyze

settings = acousticgender.library.settings.settings

request_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

################## Form Handling ##################
cgitb.enable()

print("Content-type:text/plain\r\n\r\n")
	
form = cgi.FieldStorage()
uploaded_file = form.getvalue('recording')
transcript = form.getvalue('transcript')

id, data = analyze(uploaded_file, transcript)

print(json.dumps(data))

countries = None
if os.path.exists('./countries.mmdb'):
	countries = maxminddb.open_database('./countries.mmdb')

# Logging
if settings['logs'] and os.path.exists(settings['logs']):
	#try:

	ip = os.environ.get('REMOTE_ADDR')
	logfile = settings['logs'] + request_date.replace(' ', '_') + '_' + id + '.json'
	with open(logfile, 'w') as f:
		log_info = {
			# Hash the IP so that we can count use by a single user
			# without compromising their privacy.
			'country': countries.get(ip)['country']['iso_code'],
			'ua': os.environ.get('HTTP_USER_AGENT'),
			'date': request_date,
			'referrer': form.getvalue('referrer'),
			'lang': form.getvalue('lang'),
			'screen-dimensions' : {
				'width' : form.getvalue('screen-width'),
				'height' : form.getvalue('screen-height'),
			}
		}
		log_info['id'] = hashlib.sha256((
			ip + log_info['ua'] + str(log_info['screen-dimensions'])
		).encode('ascii')).hexdigest()
		f.write(json.dumps(log_info))

	#except:
	#	pass
