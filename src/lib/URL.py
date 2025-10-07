import atexit
import gzip
import socket
import ssl
from time import time
from pathlib import Path
from .Storage import Storage
from . import BASE_DIR, COOKIE_JAR
from email.utils import parsedate_to_datetime

DEFAULT_PAGE_PATH = Path(BASE_DIR) / "assets" / "html" / "home.html"
BOOKMARKS_PAGE_PATH = Path(BASE_DIR) / "assets" / "html" / "bookmarks.html"
REDIRECT_LIMIT = 20

class URL:
    def __init__(self, url: str):
        self.storage = Storage()
        self.is_valid = True
        self.redirect_count = 0
        self.saved_sockets: dict[tuple[str, str, int], socket.socket] = {}
        self.url: str = url
        # base values
        self.method: str = "GET"
        self.payload: str | None = None
        self.scheme: str = ""
        self.host: str = ""
        self.path: str = ""
        self.port: int = 0
        self.fragment: str | None = None
        self.view_source: bool = False
        self.is_safe: bool | None = None
        self.referrer_policy: str | None = None
        # data scheme specific
        self.content: str = ""
        self.type: str = ""
        # Cleanup
        atexit.register(self.cleanup)
        # Parsing
        if not url:
            self.is_valid = False
            return
        try:
            self.view_source = url.startswith("view-source:")
            if self.view_source:
                url = url[len("view-source:"):]
            if url == "about:blank": return
            if url == "about:bookmarks": return
            if url.startswith("data"):
                self.scheme, url = url.split(":", 1)
                self.type, self.content = url.split(",", 1)
                return
            self.scheme, url = url.split("://", 1)
            assert self.scheme in ["http", "https", "file"]
            if self.scheme == "file":
                self.path = url
                return
            elif self.scheme == "http":
                self.port = 80
                self.is_safe = False
            elif self.scheme == "https":
                self.port = 443
                self.is_safe = True
            if "#" in url:
                url, self.fragment = url.split("#", 1) 
            if "/" not in url and "?" not in url:
                url = url + "/"
            self.host, url = url.split("/", 1)
            self.path = "/" + url
            if ":" in self.host:
                self.host, port = self.host.split(":", 1)
                self.port = int(port)
        except:
            # Invalid url override
            self.valid_url = False
            query = self.url.replace(" ", "+")
            # Using `duckduckgo.com`, becouse it provides raw html without auth
            self.url = "https://lite.duckduckgo.com/lite?p={}".format(query) 
            self.scheme = "https"
            self.host = "lite.duckduckgo.com"
            self.port = 443
            self.path = "/lite?p={}".format(query)
            self.fragment = None

    def __str__(self) -> str:
        if not self.url:
            return ""
        if self.url.startswith("about:"):
            return self.url
        if self.scheme == "file":
            return self.scheme + "://" + self.path
        elif self.scheme == "data":
            return self.scheme + ":" + self.type  + "," + self.content
        port_part = ":" + str(self.port if hasattr(self, "port") else "")
        if port_part == ":":
            port_part= ""
        elif self.scheme == "https" and self.port == 443:
            port_part = ""
        elif self.scheme == "http" and self.port == 80:
            port_part = ""
        fragment_part = ""
        if self.fragment:
            fragment_part = "#" + self.fragment
        return self.scheme + "://" + self.host + port_part + self.path + fragment_part

    def cleanup(self) -> None:
        for k, s in self.saved_sockets.items():
            s.close()

    def origin(self) -> str:
        if not self.url \
        or self.url.startswith("about:") \
        or self.scheme not in ["http", "https"]:
            return ""
        return self.scheme + "://" + self.host + ":" + str(self.port)

    def resolve(self, url: str) -> 'URL':
        if (not url) or url.startswith(("about:", "data:", "file://")):
            return URL(url)
        if url.startswith("#"):
            return URL(self.scheme + "://" + self.host + ":" + str(self.port) + self.path + url)
        if "://" in  url: return URL(url)
        if url.startswith("./"): url = url.removeprefix("./")
        if not url.startswith("/") and "/" in self.path:
            dir, _ = self.path.rsplit("/", 1)
            while url.startswith("../"):
                _, url = url.rsplit("/", 1)
                if "/" in dir:
                    dir, _ = self.path.rsplit("/", 1)
            url = dir + "/" + url
        if url.startswith("//"):
            return URL(self.scheme + ":" + url)
        else:
            return URL(self.scheme + "://" + self.host + ":" + str(self.port) + url)

    def request(self, referrer: 'URL', payload: str | None = None) -> tuple[dict[str, str], str]:
        self.method = "POST" if payload else "GET"
        self.payload = payload
        # Base cases
        if not self.url:
            content = ""
            try: 
                file = open(DEFAULT_PAGE_PATH, "r")
                content = file.read()
                file.close()
            except:
                return {}, "<h1>404 Not Found</h1>"
            return {}, content
        elif self.url == "about:blank":
            return {}, ""
        elif self.url == "about:bookmarks":
            content = ""
            try:
                file = open(BOOKMARKS_PAGE_PATH, "r")
                content = file.read()
                file.close() 
            except:
                return {}, "<h1>404 Not Found</h1>"
            bookmarks = []
            for url, _ in self.storage.get_all_bookmarks():
                title = url 
                if not title: title = "(Home page)" 
                bookmarks.append('<li><a href="{}">{}</a></li>'.format(url, title))
            x_bookmarks = "<ul>{}</ul>".format("".join(bookmarks)) if bookmarks else '<small class="empty">There are no bookmarks!</small>'
            content = content.replace("<x-bookmarks>", x_bookmarks)
            return {}, content
        elif self.scheme == "file":
            content = ""
            try:
                file = open(self.path, "r")
                content = file.read()
                file.close()
            except:
                return {}, "<h1>404 Not Found</h1>"
            return {}, content
        elif self.scheme == "data":
            return {}, self.content
        # Cache
        if self.method == "GET":
            cached_response = self.storage.get_cache(self.url)
            if cached_response is not None: return {}, cached_response
        # Socket
        s: socket.socket
        socket_key = (self.scheme, self.host, self.port)
        if socket_key in self.saved_sockets and self.saved_sockets[socket_key].fileno() != -1:
            s = self.saved_sockets[socket_key]
        else:
            s = socket.socket(
                family=socket.AF_INET, 
                type=socket.SOCK_STREAM, 
                proto=socket.IPPROTO_TCP
            )
            if self.scheme == "https":
                ctx = ssl.create_default_context()
                s = ctx.wrap_socket(s, server_hostname=self.host)
            self.saved_sockets[(self.scheme, self.host, self.port)] = s
            try:
                s.connect((self.host, self.port))
            except (ssl.SSLCertVerificationError, ssl.SSLError) as e:
                self.is_safe = False
                self.is_valid = False
                s.close()
                self.saved_sockets.pop(socket_key)
                return {"x-ssl-error": str(e)}, "<h1>SSL error ocurred while connecting to host...</h1>"
            except:
                s.close()
                self.saved_sockets.pop(socket_key)
                return {}, "<h1>Error ocurred while connecting to host...</h1>"
        # Request
        request = "{} {} HTTP/1.1\r\n".format(self.method, self.path)
        request_headers = {
            "Host": self.host,
            "Connection": "keep-alive",
            "User-Agent": "StrangeBrows",
            "Accept-Encoding": "gzip",
        }
        if (referrer.referrer_policy is None) \
        or (referrer.referrer_policy == "same-origin" and self.origin() == referrer.origin()):
            request_headers["Referer"] = str(referrer)
        if referrer.origin() and self.origin() != referrer.origin():
            request_headers["Origin"] = referrer.origin()
        if self.payload:
            length = len(self.payload.encode())
            request_headers["Content-Length"] = str(length)
        for header in request_headers:
            request += "{}: {}\r\n".format(header, request_headers[header])
        if self.host in COOKIE_JAR:
            cookie, params  = COOKIE_JAR[self.host]
            allow_cookie = True
            # Handling Expires
            if "expires" in params and params["expires"] != "session":
                expires: float = parsedate_to_datetime(params["expires"]).astimezone().timestamp()
                if expires < time():
                    allow_cookie = False
                    COOKIE_JAR.pop(self.host)
            # Handling SameSite
            if allow_cookie and referrer and params.get("samesite", "none") == "lax":
                if self.method != "GET":
                    allow_cookie = self.host == referrer.host
            # ---
            if allow_cookie:
                request += "Cookie: {}\r\n".format(cookie)
        request += "\r\n"
        # Request payload
        if self.payload: request += self.payload
        s.send(request.encode())
        response = s.makefile("rb", encoding="utf-8", newline="\r\n")
        # Response status line
        statusline = response.readline().decode()
        try:
            version, status, explenation = statusline.split(" ", 2)
        except:
            if socket_key in self.saved_sockets:
                s = self.saved_sockets.pop(socket_key)
                s.close()
                return self.request(referrer, self.payload)
            print("Recived invalid response from '{}'...".format(self.url))
            return {}, ""
        status = int(status)
        # Headers
        response_headers: dict[str, str] = {}
        while True:
            line = response.readline().decode()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()
        # Referrer policy
        self.referrer_policy = response_headers.get("referrer-policy", None)
        # Cookies
        if "set-cookie" in response_headers:
            cookie = response_headers["set-cookie"]
            COOKIE_JAR[self.host] = parse_cookie(cookie)
        # Content
        content: str
        if "content-encoding" in response_headers and response_headers["content-encoding"] == "gzip":
            if "transfer-encoding" in response_headers and response_headers["transfer-encoding"] == "chunked":
                assert "content-length" not in response_headers
                encoded_content = bytearray()
                while True:
                    chunk_length = int(response.readline(), 16)
                    if chunk_length == 0: break
                    encoded_content.extend(response.read(chunk_length))
                    response.readline() # Pass \r\n on chunk end
                content = gzip.decompress(encoded_content).decode()
            else:
                content_length = int(response_headers["content-length"])
                encoded_content = response.read(content_length)
                content = gzip.decompress(encoded_content).decode()
        else:
            content_length = int(response_headers["content-length"]) \
                if "content-length" in response_headers else None
            content = response.read(content_length).decode()
        # Response handling
        if 300 <= status < 400:
            self.redirect_count += 1
            if self.redirect_count > REDIRECT_LIMIT:
                raise Exception("Reached redirection limit")
            assert "location" in response_headers
            location: str = response_headers["location"]
            new_url = self.resolve(location)
            new_url.redirect_count = self.redirect_count
            new_url.saved_sockets = self.saved_sockets
            return new_url.request(referrer)
        else:
            self.redirect_count = 0
        if status == 200 and "cache-control" in response_headers:
            cache_control: str = response_headers["cache-control"]
            if cache_control == "no-store":
                pass
            elif cache_control.startswith("max-age"):
                max_age = int(cache_control.split("=", 1)[1].split(",", 1)[0])
                assert max_age >= 0
                age = 0
                if "age" in response_headers:
                    age = int(response_headers["age"])
                    assert age >= 0
                expires = int(time()) + max_age - age
                if self.storage.get_cache(self.url):
                    self.storage.update_cache(self.url, expires, content)
                else:
                    self.storage.add_cache(self.url, expires, content)
        return response_headers, content
    
def parse_cookie(cookie: str) -> tuple[str, dict[str, str]]:
    params = {}
    if ";" in cookie:
        cookie, rest = cookie.split(";", 1)
        for param in rest.split(";"):
            if "=" in param:
                param, value = param.split("=", 1)
            else: 
                value = "true"
            params[param.strip().casefold()] = value.casefold()
    return cookie, params