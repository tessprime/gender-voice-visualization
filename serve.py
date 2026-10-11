from http.server import ThreadingHTTPServer, CGIHTTPRequestHandler
import email.parser
import email.policy
import json
import posixpath
import secrets
import sys
import threading
import time
import traceback
import urllib.parse

# Only these are served. The server's root is the whole checkout, which also
# holds every uploaded recording (rec/), .git/, settings.json, etc.
ALLOWED_FILES = {"/", "/index.html", "/manifest.json", "/sw.js", "/offline.html",
                 # Data the in-browser analysis (ui/analysis-worker.js) loads.
                 "/cmudict.txt", "/stats.json"}
ALLOWED_DIRECTORIES = ("/ui/", "/resources/", "/models/")

# Recordings from the browser are well under 1 MB per minute.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Uploads are processed one at a time: the aligner and MFA's working
# directory aren't safe to share. Page loads run in parallel.
processing_lock = threading.Lock()

# Load phonealign once, so each upload is aligned in this process instead
# of running backend.cgi (which starts `mfa align` per request). If it can't
# load, uploads go through backend.cgi as before.
aligner = None
try:
    from acousticgender.library.analysis import ProcessingError, analyze, load_aligner
    start = time.perf_counter()
    aligner = load_aligner()
    print("phonealign loaded in %.1f s" % (time.perf_counter() - start))
except Exception:
    traceback.print_exc()
    print("phonealign unavailable; uploads will run backend.cgi with mfa align")
sys.stdout.flush()

class BadRequest(Exception):
    """The request itself is malformed; the message is meant for the client."""

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

def request_path(raw_path):
    """The path as it will be resolved: query removed, %-escapes decoded,
    and "." / ".." applied, so /ui/../rec/ can't slip past the allowlist."""
    path = urllib.parse.unquote(raw_path.split("?", 1)[0].split("#", 1)[0])
    return posixpath.normpath(path) if path not in ("", "/") else "/"

def is_allowed(raw_path):
    path = request_path(raw_path)
    return path in ALLOWED_FILES or (
        path.startswith(ALLOWED_DIRECTORIES) and not path.endswith("/"))

class MyHandler(CGIHTTPRequestHandler):
    # List of exact CGI filenames
    allowed_cgi = {"backend.cgi"}

    # Seconds a connection may sit idle mid-request before it's dropped, so
    # slow or stalled clients can't hold a thread forever.
    timeout = 60

    def is_cgi(self):
        path = self.path.split("?", 1)[0]
        if path.rsplit("/", 1)[-1] in self.allowed_cgi:
            self.cgi_info = "", path.lstrip("/")
            return True
        return False

    def do_GET(self):
        if not is_allowed(self.path):
            return self.send_error(404)
        super().do_GET()

    def do_HEAD(self):
        if not is_allowed(self.path):
            return self.send_error(404)
        super().do_HEAD()

    def list_directory(self, path):
        # Never list directories (e.g. /ui/), even within the allowlist.
        self.send_error(404)
        return None

    def do_POST(self):
        if request_path(self.path) != "/backend.cgi":
            return self.send_error(404)
        try:
            length = int(self.headers["Content-Length"])
        except (TypeError, ValueError):
            return self.send_error(411)
        if not 0 < length <= MAX_UPLOAD_BYTES:
            return self.send_error(413)
        if aligner is None:
            with processing_lock:
                return super().do_POST()

        # Same work as backend.cgi, without its per-request process (and
        # without its request logging, which needs production files). Errors
        # carry a reference that matches the server log, but no internals.
        reference = secrets.token_hex(4)
        start = time.perf_counter()
        try:
            form = parse_form(self.headers.get("Content-Type", ""), self.read_body(length))
            recording, transcript = form.get("recording"), form.get("transcript")
            if not recording or transcript is None:
                raise BadRequest("The upload must include a recording and a transcript.")
            parsed = time.perf_counter()
            with processing_lock:
                waited = time.perf_counter()
                id, data = analyze(recording, transcript.decode("utf-8"), aligner)
            analyzed = time.perf_counter()
            body, status = json.dumps(data).encode(), 200
            print("[%s] clip %s processed in %.0f ms (upload parsing %.0f, waiting %.0f, analysis %.0f)" % (
                reference, id, (time.perf_counter() - start) * 1000, (parsed - start) * 1000,
                (waited - parsed) * 1000, (analyzed - waited) * 1000))
        except BadRequest as e:
            print("[%s] bad request: %s" % (reference, e))
            body, status = str(e).encode(), 400
        except ProcessingError as e:
            print("[%s] processing failed: %s" % (reference, e))
            body, status = ("%s (reference %s)" % (e, reference)).encode(), 422
        except Exception:
            print("[%s] error processing upload:" % reference)
            traceback.print_exc(file=sys.stdout)
            body, status = ("Processing failed (reference %s)." % reference).encode(), 500
        sys.stdout.flush()

        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self, length):
        # CGIHTTPRequestHandler makes rfile unbuffered (so it can hand the
        # body to a CGI process), so a single read() can return part of it.
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
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

server = ThreadingHTTPServer(("0.0.0.0", 8000), MyHandler)
print("serving on port 8000")
sys.stdout.flush()
server.serve_forever()
