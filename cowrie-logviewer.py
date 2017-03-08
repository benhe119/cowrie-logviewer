#: A simple log viewer for cowrie 
#: Copyright 2017 by Richard 'mindphluxnet' Kaemmerer (richard@richardkaemmerer.de)

from flask import Flask, render_template, send_from_directory
import sys
import json
import ipapi
import sqlite3
import dateutil.parser
import pycountry
from path import Path
from flask_compress import Compress

#: change stuff here
sqlite_file = 'ip2country.sqlite'
log_path = '../cowrie/log'
dl_path = '../cowrie/dl'
bind_host = '0.0.0.0'
bind_port = 5000
min_upload_size = 1024
debug = False
use_gzip = True
filter_events = [ 'cowrie.direct-tcpip.request', 'cowrie.direct-tcpip.data' ]

#: don't change stuff beyond this line

version = '0.1.2'

conn = sqlite3.connect(sqlite_file)
c = conn.cursor()

#: setup sqlite db

try:
	c.execute('CREATE TABLE ip2country (ipaddress TEXT, countrycode TEXT)')
except sqlite3.OperationalError:
	pass
try:
	c.execute('CREATE INDEX ipindex ON ip2country(ipaddress)')
except sqlite3.OperationalError:
	pass
try:
	c.execute('CREATE INDEX countryindex ON ip2country(countrycode)')
except sqlite3.OperationalError:
	pass

conn.commit()
conn.close()

#: flask routes

app = Flask(__name__, static_url_path = '')
if(use_gzip):
	Compress(app)
try:
	if(sys.argv[1] == 'test'):
		sys.exit(0)
except Exception:
	pass

@app.route('/images/<path:path>')
def send_image(path):
	return send_from_directory('images', path)

@app.route('/log/<string:logfile>')
def show_log(logfile):
	return render_log(logfile)

@app.route('/')
def index():
	return render_log('cowrie.json')

@app.route('/uploads')
def show_files():

	page = 'uploads'

	uploads = get_uploaded_files()


	return render_template('uploads.html', uploads = uploads, page = page, version = version)

@app.route('/download/<path:filename>')
def download_file(filename):
	return send_from_directory(dl_path, filename)

@app.route('/stats')
def show_stats():
	
	conn = sqlite3.connect(sqlite_file)
	c = conn.cursor()

	page = 'stats'

	c.execute("SELECT countrycode, count(countrycode) AS attack_count FROM ip2country GROUP BY countrycode ORDER BY attack_count DESC")
	countries = c.fetchall()		

	out = []

	for country in countries:
		tmp = [ pycountry.countries.get(alpha_2=country[0]).name, country[0], country[1] ]
		out.append(tmp)

	return render_template('stats.html', countries = out, version = version, page = page)

def get_log_files():
	
	#: find all json log files

	files = []
	d = Path(log_path)
	for f in d.files('*.json*'):
		files.append(str(f.name))
	
	return sorted(files)

def get_uploaded_files():

	#: find all uploaded files >= small_upload_size (likely actual payloads)

	uploaded_files = []
	d = Path(dl_path)
	for f in d.files('*'):
		tmp = []
		if(f.size >= min_upload_size and f.name != '.gitignore'):
			tmp.append(str(f.name))
			tmp.append(f.size)
			uploaded_files.append(tmp)

	return sorted(uploaded_files)

def render_log(current_logfile):

	page = 'log'

	logfiles = get_log_files()
	
	#: connect ip2country db

	conn = sqlite3.connect(sqlite_file)
	c = conn.cursor()

	#: parse json log
	data = []

	with open(log_path + '/' + current_logfile) as f:
		for line in f:
			j = json.loads(line)			
			
			#: filter out unwanted events
			if(j['eventid'] in filter_events):
				continue

			#: check if IP address is already in database first
			
			c.execute("SELECT countrycode FROM ip2country WHERE ipaddress='" + str(j['src_ip']) + "'")
			ip_exists = c.fetchone()
			if ip_exists:	
				j['country'] = ip_exists[0]
			else:
				#: look up IP via ipapi
				j['country'] = ipapi.location(j['src_ip'], None, 'country')			

				#: add ip/country pair to db
				c.execute("INSERT OR IGNORE INTO ip2country(ipaddress, countrycode) VALUES ('" + str(j['src_ip']) + "', '" + j['country'] + "')")
				conn.commit()

			#: fix date/time to remove milliseconds and other junk
			j['datetime'] = str(dateutil.parser.parse(j['timestamp']))
			tmp = j['datetime'].split('.')
			j['datetime'] = tmp[0]

			#: convert country code to human readable
			country = pycountry.countries.get(alpha_2=j['country'])
			j['country_name'] = str(country.name)

			data.append(j)
	
	conn.close();					
	return render_template('index.html', json = data, logfiles = logfiles, current_logfile = current_logfile, version = version, page = page)

if __name__ == '__main__':
	app.run(debug = debug, host = bind_host, port = bind_port)
