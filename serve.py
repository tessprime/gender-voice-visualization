from http.server import HTTPServer, CGIHTTPRequestHandler
import os
import sys

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
