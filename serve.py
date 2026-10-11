from http.server import HTTPServer, CGIHTTPRequestHandler
import email.parser
import email.policy
import json
import os
import sys
import time
import traceback

# Load phonealign once, so each upload is aligned in this process instead
# of running backend.cgi (which starts `mfa align` per request). If it can't
# load, uploads go through backend.cgi as before.
aligner = None
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'phonealign', 'src'))
    from phonealign import Aligner
    from acousticgender.library.analysis import analyze
    models = os.path.join(os.environ.get('MFA_ROOT_DIR', os.path.expanduser('~/Documents/MFA')), 'pretrained_models')
    start = time.perf_counter()
    # Loading unpacks the model under $MFA_ROOT_DIR. This server runs as
    # root but backend.cgi's `mfa align` runs as nobody, so keep anything
    # created there writable by everyone, as the Dockerfile does.
    old_umask = os.umask(0)
    try:
        aligner = Aligner(os.path.join(models, 'acoustic', 'english.zip'),
                          os.path.join(models, 'dictionary', 'english.dict'))
    finally:
        os.umask(old_umask)
    print("phonealign loaded in %.1f s" % (time.perf_counter() - start))
except Exception:
    traceback.print_exc()
    print("phonealign unavailable; uploads will run backend.cgi with mfa align")
sys.stdout.flush()

def parse_form(content_type, body):
    """{field name: bytes} from a multipart/form-data request body.
    cgi.FieldStorage took ~750 ms on a 400 KB upload, reading the
    unbuffered request line by line."""
    message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
    return {
        part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
        for part in message.iter_parts()
    }

class MyHandler(CGIHTTPRequestHandler):
    # List of exact CGI filenames
    allowed_cgi = {"backend.cgi"}

    def is_cgi(self):
        # Extract file being requested
        path = self.path.split("?", 1)[0]
        filename = path.rsplit("/", 1)[-1]
        print(filename)
        sys.stdout.flush()
        if filename in self.allowed_cgi:
            self.cgi_info = "", path.lstrip("/")
            return True

        return False

    def do_POST(self):
        filename = self.path.split("?", 1)[0].rsplit("/", 1)[-1]
        if aligner is None or filename != "backend.cgi":
            return super().do_POST()

        # Same work as backend.cgi, without its per-request process (and
        # without its request logging, which needs production files).
        start = time.perf_counter()
        try:
            form = parse_form(self.headers["Content-Type"], self.read_body())
            parsed = time.perf_counter()
            id, data = analyze(form["recording"], form["transcript"].decode("utf-8"), aligner)
            analyzed = time.perf_counter()
            body, status = json.dumps(data).encode(), 200
            print("clip %s processed in %.0f ms (upload parsing %.0f, analysis %.0f, JSON %.0f)" % (
                id, (time.perf_counter() - start) * 1000, (parsed - start) * 1000,
                (analyzed - parsed) * 1000, (time.perf_counter() - analyzed) * 1000))
        except Exception as e:
            traceback.print_exc()
            body, status = ("Processing failed: %r" % e).encode(), 500
        sys.stdout.flush()

        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        # CGIHTTPRequestHandler makes rfile unbuffered (so it can hand the
        # body to a CGI process), so a single read() can return part of it.
        length = int(self.headers["Content-Length"])
        chunks = []
        while length > 0:
            chunk = self.rfile.read(length)
            if not chunk:
                raise ConnectionError("request body ended early")
            chunks.append(chunk)
            length -= len(chunk)
        return b"".join(chunks)

    def end_headers(self):
        # Without Cache-Control, browsers cache files heuristically and can
        # keep serving an old ui/*.js next to a newly edited one. Make them
        # revalidate every time (unchanged files just get a 304).
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()
print("hello!")
print(os.environ)
sys.stdout.flush()
server = HTTPServer(("0.0.0.0", 8000), MyHandler)
server.serve_forever()
