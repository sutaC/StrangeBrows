#!/usr/bin/env python3
import re
import socket
import urllib.parse
import sqlite3
from pathlib import Path
from argparse import ArgumentParser

BASE_PATH = Path(__file__).parent.parent
DATABSE_PATH = BASE_PATH / "server.db"
COMMENT_JS_PATH = BASE_PATH / "assets" / "js" / "comment.js"
COMMENT_CSS_PATH = BASE_PATH / "assets" / "css" / "comment.css"

class Databse:
    def __init__(self) -> None:
        self.con = sqlite3.connect(DATABSE_PATH)

    def initialize(self) -> None:
        c = self.con.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(255) NOT NULL UNIQUE
            )       
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                content VARCHAR(255) NOT NULL,
                topic_id INTEGER NOT NULL,
                FOREIGN KEY(topic_id) REFERENCES topics(id)
            )       
        ''')
        self.con.commit()
        c.close()

    def get_all_topics(self) -> list[str]:
        c = self.con.cursor()
        c.execute("SELECT title FROM topics;")
        fetch: list[tuple[str]] = c.fetchall()
        c.close()
        data: list[str] = [x[0] for x in fetch]
        return data
    
    def has_topic(self, topic: str) -> bool:
        c = self.con.cursor()
        c.execute("SELECT id FROM topics WHERE title = ?;", [topic])
        fetch: tuple[int] | None = c.fetchone()
        c.close()
        return fetch is not None
    
    def add_topic(self, topic: str) -> None:
        c = self.con.cursor()
        c.execute("INSERT INTO topics (title) VALUES (?);", [topic])
        self.con.commit()
        c.close()
    
    def get_all_comments(self, topic: str) -> list[str]:
        c = self.con.cursor()
        c.execute('''
            SELECT c.content 
            FROM comments AS c
            JOIN topics AS t ON c.topic_id = t.id
            WHERE t.title = ?;
        ''', [topic])
        fetch: list[tuple[str]] = c.fetchall()
        data: list[str] = [x[0] for x in fetch]
        c.close()
        return data

    def add_comment(self, topic: str, comment: str) -> None:
        c = self.con.cursor()
        c.execute("SELECT id FROM topics WHERE title = ?;", [topic])
        fetch: tuple[int] | None = c.fetchone()
        tid: int | None = fetch[0] if fetch is not None else None
        if tid is None: raise Exception("Topic '{}' doesn't exist".format(topic))
        c.execute("INSERT INTO comments (content, topic_id) VALUES (?, ?);", [comment, tid])
        self.con.commit()
        c.close()

    def clear(self) -> None:
        c = self.con.cursor()
        c.execute("DELETE FROM topics;")
        c.execute("DELETE FROM comments;")
        self.con.commit()
        c.close()

    def close(self) -> None:
        self.con.close()

def show_topics() -> str:
    out = "<!doctype html>"
    out += '<link rel="stylesheet" href="/comment.css">'
    out += "<h1>Message board</h1>"
    out += "<form action=add method=post>"
    out += "<p><input name=topic required></p>"
    out += "<p><button>Add topic</button></p>"
    out += "</form>"
    out += "<strong></strong>"
    out += "<h2>Topics</h2>"
    db = Databse()
    topics = db.get_all_topics()
    db.close()
    for topic in topics:
        parsed = urllib.parse.quote(topic)
        out += '<p><a href="/topic/{}">{}</a></p>'.format(parsed, topic)
    out += '<script src="/comment.js"></script>'
    return out

def show_comments(topic: str) -> str:
    db = Databse()
    has_topic = db.has_topic(topic)
    if not has_topic: 
        db.close()
        return ""
    parsed = urllib.parse.quote(topic)
    out = "<!doctype html>"
    out += '<link rel="stylesheet" href="/comment.css">'
    out += "<h1>" + topic + "</h1>"
    out += '<a href="/">Home</a>'
    out += '<form action="/topic/' + parsed + '/add" method=post>'
    out += "<p><input name=comment required></p>"
    out += "<p><button>Add comment</button></p>"
    out += "</form>"
    out += "<strong></strong>"
    comments = db.get_all_comments(topic)
    db.close()
    for entry in comments:
        out += "<p>" + entry + "</p>"
    out += '<script src="/comment.js"></script>'
    return out

def form_decode(body: str | None) -> dict[str, str]:
    if not body: return {}
    params: dict[str, str] = {}
    for field in body.split("&"):
        name, value = field.split("=", 1)
        name = urllib.parse.unquote_plus(name)
        value = urllib.parse.unquote_plus(value)
        params[name] = value
    return params

def add_topic(params: dict[str, str]) -> str:
    if 'topic' not in params or not params["topic"]: return show_topics()
    topic = params['topic']
    if len(topic) > 100: return show_comments(topic) 
    db = Databse()
    has_topic = db.has_topic(topic)
    if has_topic: 
        db.close()
        return show_comments(topic)
    db.add_topic(topic)
    db.close()
    return show_comments(topic)
    

def add_entry(topic: str, params: dict[str, str]) -> str:
    if 'comment' in params and len(params["comment"]) > 100: return show_comments(topic) 
    db = Databse()
    has_topic = db.has_topic(topic)
    if not has_topic: 
        db.close()        
        return ""
    if 'comment' not in params or not params["comment"]:
        db.close()
        return show_topics()
    db.add_comment(topic, params["comment"])
    db.close()
    return show_comments(topic)

def not_found(url: str, method: str) -> str:
    out = "<!doctype html>"
    out += "<h1>{} {} not found!</h1>".format(method, url)
    return out

def do_request(
method: str, 
url: str, 
headers: dict[str, str], 
body: str | None
) -> tuple[str, str]:
    if url != "/": 
        url = url.rstrip("/")
    # Routes
    if method == "GET" and url == "/": # /
        return "200 OK", show_topics()
    elif method == "GET" and url == "/comment.js":
        with open(COMMENT_JS_PATH) as f:
            return "200 OK", f.read()
    elif method == "GET" and url == "/comment.css":
        with open(COMMENT_CSS_PATH) as f:
            return "200 OK", f.read()
    elif method == "POST" and url == "/add": # /add
        params = form_decode(body)
        return "200 OK", add_topic(params)
    elif method == "GET" and re.match(r"^\/topic\/[\w,%,+]+$", url): # /topic/[name]
        topic = url.removeprefix("/topic/")
        topic = urllib.parse.unquote_plus(topic)
        db = Databse()
        has_topic = db.has_topic(topic)
        db.close()
        if not has_topic: return "404 Not Found", not_found(url, method)
        return "200 OK", show_comments(topic)
    elif method == "POST" and re.match(r"^\/topic\/[\w,%,+]+\/add$", url): # /topic/[name]/add
        params = form_decode(body)
        topic = url.removeprefix("/topic/").removesuffix("/add")
        topic = urllib.parse.unquote_plus(topic)
        db = Databse()
        has_topic = db.has_topic(topic)
        db.close()
        if not has_topic: return "404 Not Found", not_found(url, method) 
        return "200 OK", add_entry(topic, params)
    else:
        return "404 Not Found", not_found(url, method)

def handle_connection(conx: socket.socket) -> None:
    req = conx.makefile("rb")
    reqline = req.readline().decode()
    method, url, version = reqline.split(" ", 2)
    assert method in ["GET", "POST"]
    headers: dict[str, str] = {}
    while True:
        line = req.readline().decode()
        if line == "\r\n": break
        header, value = line.split(":", 1)
        headers[header.casefold()] = value.strip()
    if 'content-length' in headers:
        length = int(headers['content-length'])
        body = req.read(length).decode()
    else:
        body = None
    status, body  = do_request(method, url, headers, body)
    response = "HTTP/1.0 {}\r\n".format(status)
    response += "Contrnt-Length: {}\r\n".format(len(body.encode()))
    response += "\r\n" + body
    conx.send(response.encode())
    conx.close()

def main() -> None:
    # Db init
    db = Databse()
    db.initialize()
    # Handling options
    parser = ArgumentParser("HTTP server for testing")
    parser.add_argument("-c", "--clear", action="store_true", help="clear server database")
    args = parser.parse_args()
    if args.clear:
        print("[INFO]: Clearing server database")
        db.clear()
    # ---
    db.close()
    # Handling Connections
    s = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP
    )
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    port = 8000
    s.bind(('', port))
    s.listen()
    print("[INFO]: Listening on http://127.0.0.1:{}".format(port))
    while True:
        conx, addr = s.accept()
        try:
            handle_connection(conx)
        except Exception as e:
            print("[ERROR]: {}".format(e))
            conx.close()

if __name__ == "__main__":
    main()