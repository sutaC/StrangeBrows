import atexit
import gzip
import os
import socket
import sqlite3
import ssl
from time import time

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DEFAULT_PAGE_URL = "file://" + os.path.join(BASE_DIR, "assets", "home.html")
REDIRECT_LIMIT = 5

class Cache:
    def __init__(self, dir: str = ".") -> None:
        self.con = sqlite3.connect(dir)
        cursor = self.con.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS responses (url VARCHAR(255), expires INT, body TEXT);')
        self.con.commit()
        cursor.close()
        atexit.register(self.con.close)        

    def add(self, url: str, expires: int, body: str) -> None:
        cursor = self.con.cursor()
        cursor.execute('INSERT INTO responses (url, expires, body) VALUES (?, ?, ?);', [url, expires, body])
        self.con.commit()
        cursor.close()

    def get(self, url: str) -> str | None:
        cursor = self.con.cursor()
        cursor.execute("SELECT expires, body FROM responses WHERE url = ?;", [url])
        data = cursor.fetchone()
        cursor.close()
        if data is None:
            return None
        expires: int
        body: str
        expires, body = data
        now = int(time())
        if now > expires:
            self.delete(url)
            return None
        return body
        
    def delete(self, url: str) -> None:
        cursor = self.con.cursor()
        cursor.execute("DELETE FROM responses WHERE url = ?;", [url])
        self.con.commit()
        cursor.close()

    def clean(self) -> None:
        cursor = self.con.cursor()
        cursor.execute("DELETE FROM responses;")
        self.con.commit()
        cursor.close()

class URL:
    def __init__(self, url: str):
        self.cache = Cache(os.path.join(BASE_DIR, "cache.sqlite"))
        self.is_valid = True
        self.redirect_count = 0
        self.saved_sockets: dict[tuple[str, str, int], socket.socket] = {}
        if not url:
            url = DEFAULT_PAGE_URL
        self.url: str = url
        try:
            self.view_source = url.startswith("view-source:")
            if self.view_source:
                url = url[len("view-source:"):]
            if url == "about:blank": return
            if url.startswith("data"):
                self.scheme, url = url.split(":", 1)
                self.type, self.content = url.split(",", 1)
                return
            self.scheme, url = url.split("://", 1)
            assert self.scheme in ["http", "https", "file", "data"]
            if self.scheme == "http":
                self.port = 80
            elif self.scheme == "https":
                self.port = 443
            if self.scheme == "data": return
            self.fragment = None
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
        atexit.register(self.cleanup)

    def __str__(self) -> str:
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

    def resolve(self, url: str) -> 'URL':
        if url.startswith("#"):
            return URL(self.scheme + "://" + self.host + ":" + str(self.port) + self.path + url)
        if "://" in  url: return URL(url)
        if url.startswith("./"): url = url.removeprefix("./")
        if not url.startswith("/"):
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

    def request(self) -> str:
        # Base cases
        if self.url == "about:blank":
            return ""
        if self.scheme == "file":
            file = open(self.path, "r")
            content = file.read()
            file.close()
            return content
        elif self.scheme == "data":
            return self.content
        cached_response = self.cache.get(self.url)
        if cached_response is not None:
            return cached_response
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
            s.connect((self.host, self.port))
        # Request
        request_headers = {
            "Host": self.host,
            "Connection": "keep-alive",
            "User-Agent": "StrangeBrows",
            "Accept-Encoding": "gzip"
        }
        request = "GET {} HTTP/1.1\r\n".format(self.path)
        for header in request_headers:
            request += "{}: {}\r\n".format(header, request_headers[header])
        request += "\r\n"
        s.send(request.encode())
        response = s.makefile("rb", encoding="utf-8", newline="\r\n")
        # Status line
        statusline = response.readline().decode()
        try:
            version, status, explenation = statusline.split(" ", 2)
        except:
            print("Recived invalid response from '{}'...".format(self.url))
            return ""
        status = int(status)
        # Headers
        response_headers = {}
        while True:
            line = response.readline().decode()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()
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
            return new_url.request()
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
                self.cache.add(self.url, expires, content)
        return content