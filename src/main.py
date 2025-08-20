#!/usr/bin/env python3
import socket
import ssl
import os
import sqlite3
import time
import atexit
import gzip

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
        now = int(time.time())
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
    def __init__(self, url: str | None):
        self.BASE_DIR = os.path.join(os.path.dirname(__file__), os.pardir)
        self.url = str(url)
        self.CACHE = Cache(os.path.join(self.BASE_DIR, "cache.sqlite"))
        self.REDIRECT_LIMIT = 5
        self.redirect_count = 0
        self.saved_socket: socket.socket | None = None
        if url is None:
            url = "file://" + os.path.join(self.BASE_DIR, "assets", "home.html")
        self.parse(url)
        atexit.register(self.cleanup)

    def cleanup(self) -> None:
        if self.saved_socket is not None:
            self.saved_socket.close()

    def parse(self, url: str) -> None:
        if url.startswith("data"):
            self.scheme, url = url.split(":", 1)
            self.type, self.content = url.split(",", 1)
            return            
        self.scheme, url = url.split("://", 1)
        self.view_source = self.scheme.startswith("view-source:")
        if self.view_source:
            self.scheme = self.scheme[len("view-source:"):]
        assert self.scheme in ["http", "https", "file", "data"]
        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443
        if self.scheme == "data": return
        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url
        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)


    def request(self) -> str:
        if self.scheme == "file":
            file = open(self.path, "r")
            content = file.read()
            file.close()
            return content
        elif self.scheme == "data":
            return self.content
        cached_response = self.CACHE.get(self.url)
        if cached_response is not None:
            return cached_response
        s: socket.socket
        if self.saved_socket is not None:
            s = self.saved_socket
        else:
            s = socket.socket(
                family=socket.AF_INET, 
                type=socket.SOCK_STREAM, 
                proto=socket.IPPROTO_TCP
            )
            if self.scheme == "https":
                ctx = ssl.create_default_context()
                s = ctx.wrap_socket(s, server_hostname=self.host)
            self.saved_socket = s
            s.connect((self.host, self.port))
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
        statusline = response.readline().decode()
        version, status, explenation = statusline.split(" ", 2)
        status = int(status)
        response_headers = {}
        while True:
            line = response.readline().decode()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()
        if 300 <= status < 400:
            self.redirect_count += 1
            if self.redirect_count > self.REDIRECT_LIMIT:
                raise Exception("Reached redirection limit")
            location: str = response_headers["location"]
            if location.startswith("/"):
                self.path = location
            else:
                self.parse(location)
            return self.request()
        else:
            self.redirect_count = 0
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
            content_length = int(response_headers["content-length"])
            content = response.read(content_length).decode()
        if status == 200 and "cache-control" in response_headers:
            cache_control: str = response_headers["cache-control"]
            if cache_control == "no-store":
                pass
            elif cache_control.startswith("max-age"):
                max_age = int(cache_control.split("=", 1)[1])
                assert max_age >= 0
                age = 0
                if "age" in response_headers:
                    age = int(response_headers["age"])
                    assert age >= 0
                expires = int(time.time()) + max_age - age
                self.CACHE.add(self.url, expires, content)
        return content

def show(body: str, view_source = False) -> None:
    if view_source:
        print(body, end="")
        return
    in_tag = False
    special_char = ""
    special_chars = {
        "lt": "<",
        "gt": ">",
    }
    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif c == "&":
            special_char += c
        elif special_char:
            special_char += c
            if c == " ":
                print(special_char, end="")
                special_char = ""
            elif c == ";":
                char_key = special_char[1:-1]
                if char_key in special_chars:
                    special_char = special_chars[char_key]
                print(special_char, end="")
                special_char = ""
        elif not in_tag:
            print(c, end="")

def load(url: URL) -> None:
    body = url.request()
    show(body, view_source=url.view_source)

# --- Start

if __name__ == "__main__":
    import sys
    url: str | None = None
    if len(sys.argv) > 1:
        url = sys.argv[1]
    load(URL(url))