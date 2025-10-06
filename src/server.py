#!/usr/bin/env python3
import re
import html
import socket
import random
import urllib.parse
import sqlite3
from pathlib import Path
from argparse import ArgumentParser
from collections import namedtuple

session_data = dict
Comment = namedtuple("Comment", ["content", "author"])
Topic = namedtuple("Topic", ["title", "author"])

BASE_PATH = Path(__file__).parent.parent
DATABSE_PATH = BASE_PATH / "server.db"
COMMENT_JS_PATH = BASE_PATH / "assets" / "js" / "comment.js"
COMMENT_CSS_PATH = BASE_PATH / "assets" / "css" / "comment.css"

SESSIONS: dict[str, session_data] = {}

class Databse:
    def __init__(self) -> None:
        self.con = sqlite3.connect(DATABSE_PATH)

    def initialize(self) -> None:
        c = self.con.cursor()
        c.executescript('''
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(255) NOT NULL UNIQUE,
                author VARCHAR(255) NOT NULL,
                FOREIGN KEY(author) REFERENCES users(username)
            );       
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                content VARCHAR(255) NOT NULL,
                author VARCHAR(255) NOT NULL,
                topic_id INTEGER NOT NULL,
                FOREIGN KEY(author) REFERENCES users(username),
                FOREIGN KEY(topic_id) REFERENCES topics(id)
            );
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(255) NOT NULL PRIMARY KEY,
                password VARCHAR(255) NOT NULL
            );
        ''')
        self.con.commit()
        # Dummy data
        c.execute("SELECT username FROM users LIMIT 1;")
        if not bool(c.fetchone()):
            c.execute('''
                INSERT INTO users 
                    (username, password)
                VALUES
                    ("crashoverride", "0cool"),
                    ("cerealkiller", "emmanuel");
            ''')
            self.con.commit()
        c.close()

    def get_all_topics(self) -> list[Topic]:
        c = self.con.cursor()
        c.execute("SELECT title, author FROM topics;")
        fetch: list[Topic] = c.fetchall()
        c.close()
        return fetch
    
    def has_topic(self, topic: str) -> bool:
        c = self.con.cursor()
        c.execute("SELECT id FROM topics WHERE title = ?;", [topic])
        fetch: tuple[int] | None = c.fetchone()
        c.close()
        return fetch is not None
    
    def add_topic(self, topic: str, author: str) -> None:
        c = self.con.cursor()
        c.execute("INSERT INTO topics (title, author) VALUES (?, ?);", [topic, author])
        self.con.commit()
        c.close()
    
    def get_all_comments(self, topic: str) -> list[Comment]:
        c = self.con.cursor()
        c.execute('''
            SELECT c.content, c.author
            FROM comments AS c
            JOIN topics AS t ON c.topic_id = t.id
            WHERE t.title = ?;
        ''', [topic])
        fetch: list[Comment] = c.fetchall()
        c.close()
        return fetch

    def add_comment(self, topic: str, comment: str, author: str) -> None:
        c = self.con.cursor()
        c.execute("SELECT id FROM topics WHERE title = ?;", [topic])
        fetch: tuple[int] | None = c.fetchone()
        tid: int | None = fetch[0] if fetch is not None else None
        if tid is None: raise Exception("Topic '{}' doesn't exist".format(topic))
        c.execute("INSERT INTO comments (content, author, topic_id) VALUES (?, ?, ?);", [comment, author, tid])
        self.con.commit()
        c.close()

    def validate_user(self, username: str, password: str) -> bool:
        c = self.con.cursor()
        c.execute("SELECT username FROM users WHERE username = ? AND password = ?;", [username, password])
        fetch = c.fetchone()
        c.close()
        return bool(fetch)

    def clear(self) -> None:
        c = self.con.cursor()
        c.execute("DELETE FROM topics;")
        c.execute("DELETE FROM comments;")
        self.con.commit()
        c.close()

    def close(self) -> None:
        self.con.close()

def show_topics(session: session_data) -> str:
    out = "<!doctype html>"
    out += '<link rel="stylesheet" href="/comment.css">'
    out += "<h1>Message board</h1>"
    if "user" in session:
        nonce = str(random.random())[2:]
        session["nonce"] = nonce
        out += "<p><b>Hello, {}</b></p>".format(
            html.escape(session["user"])
        )
        out += "<form action=add method=post>"
        out += "<p><input name=topic required></p>"
        out += "<p><button>Add topic</button></p>"
        out += "<strong></strong>"
        out += '<input name="nonce" type="hidden" value="{}">'.format(nonce)
        out += "</form>"
    else:
        out += '<a href="/login">Sing in to add topics</a>'
    out += "<h2>Topics</h2>"
    db = Databse()
    topics = db.get_all_topics()
    db.close()
    for title, author in topics:
        parsed = urllib.parse.quote_plus(title)
        out += '<p><a href="/topic/{}">{}</a> <i>by {}</i></p>'.format(
            parsed, 
            html.escape(title), 
            html.escape(author)
        )
    out += '<script src="/comment.js"></script>'
    return out

def show_comments(session: session_data, topic: str) -> str:
    db = Databse()
    has_topic = db.has_topic(topic)
    if not has_topic: 
        db.close()
        return ""
    parsed = urllib.parse.quote(topic)
    out = "<!doctype html>"
    out += '<link rel="stylesheet" href="/comment.css">'
    out += "<h1>{}</h1>".format(
        html.escape(topic)
    )
    out += '<a href="/">Home</a>'
    if "user" in session:
        nonce = str(random.random())[2:]
        session["nonce"] = nonce
        out += '<form action="/topic/' + parsed + '/add" method=post>'
        out += "<p><input name=comment required></p>"
        out += "<p><button>Add comment</button></p>"
        out += "<strong></strong>"
        out += '<input name="nonce" type="hidden" value="{}">'.format(nonce)
        out += "</form>"
    else:
        out += '<br><a href="/login">Sing in to add comments</a>'
    comments = db.get_all_comments(topic)
    db.close()
    for content, author in comments:
        out += "<p>{} <i>by {}</i></p>".format(
            html.escape(content), 
            html.escape(author)
        )
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

def add_topic(session: session_data, params: dict[str, str]) -> str:
    if "nonce" not in session or "nonce" not in params: return ""
    if session["nonce"] != params["nonce"]: return ""
    if 'user' not in session: return ""
    if 'topic' not in params or not params["topic"]: return ""
    topic = params['topic']
    if len(topic) > 100: return show_comments(session, topic) 
    db = Databse()
    has_topic = db.has_topic(topic)
    if has_topic: 
        db.close()
        return show_comments(session, topic)
    db.add_topic(topic, session["user"])
    db.close()
    return show_comments(session, topic)
    

def add_entry(session: session_data, topic: str, params: dict[str, str]) -> str:
    if "nonce" not in session or "nonce" not in params: return ""
    if session["nonce"] != params["nonce"]: return ""
    if 'user' not in session: return ""
    if 'comment' in params and len(params["comment"]) > 100: "" 
    db = Databse()
    has_topic = db.has_topic(topic)
    if not has_topic:
        db.close()     
        return ""
    if 'comment' not in params or not params["comment"]:
        db.close()
        return show_topics(session)
    db.add_comment(topic, params["comment"], session["user"])
    db.close()
    return show_comments(session, topic)

def login_form(session: session_data) -> str:
    nonce = str(random.random())[2:]
    session["nonce"] = nonce
    body = "<!doctype html>"
    body += '<form action="/" method="post">'
    body += '<p>Username: <input name="username"></p>'
    body += '<p>Password: <input name="password" type="password"></p>'
    body += '<p><button>Log in</button></p>'
    body += '<input name="nonce" type="hidden" value="{}">'.format(nonce)
    body += '</form>'
    return body

def do_login(session: session_data, params: dict) -> tuple[str, str]:
    if "nonce" not in session or "nonce" not in params: return "401 Unauthorized", "<h1>Invalid nonce</h1>"
    if session["nonce"] != params["nonce"]: return "401 Unauthorized", "<h1>Invalid nonce</h1>"
    username = params.get("username", "")
    password = params.get("password", "")
    db = Databse()
    valid_user = db.validate_user(username, password)
    db.close()
    if valid_user:
        session["user"] = username
        return "200 OK", show_topics(session)
    else:
        out = '<!doctype html>'
        out += '<h1>Invalid password for {}</h1>'.format(username)
        return "401 Unauthorized", out

def not_found(url: str, method: str) -> str:
    out = "<!doctype html>"
    out += "<h1>{} {} not found!</h1>".format(method, url)
    return out

def do_request(
session: session_data,
method: str, 
url: str, 
headers: dict[str, str], 
body: str | None
) -> tuple[str, str]:
    if url != "/": 
        url = url.rstrip("/")
    # Routes
    if method == "GET" and url == "/": # /
        return "200 OK", show_topics(session)
    elif method == "POST" and url == "/": # /
        params = form_decode(body)
        return do_login(session, params)
    elif method == "GET" and url == "/comment.js": # /comment.js
        with open(COMMENT_JS_PATH) as f:
            return "200 OK", f.read()
    elif method == "GET" and url == "/comment.css": # /comment.css
        with open(COMMENT_CSS_PATH) as f:
            return "200 OK", f.read()
    elif method == "GET" and url == "/login": # /login
        return "200 OK", login_form(session)
    elif method == "POST" and url == "/add": # /add
        params = form_decode(body)
        return "200 OK", add_topic(session, params)
    elif method == "GET" and re.match(r"^\/topic\/[\w,%,+]+$", url): # /topic/[name]
        topic = url.removeprefix("/topic/")
        topic = urllib.parse.unquote_plus(topic)
        db = Databse()
        has_topic = db.has_topic(topic)
        db.close()
        if not has_topic: return "404 Not Found", not_found(url, method)
        return "200 OK", show_comments(session, topic)
    elif method == "POST" and re.match(r"^\/topic\/[\w,%,+]+\/add$", url): # /topic/[name]/add
        params = form_decode(body)
        topic = url.removeprefix("/topic/").removesuffix("/add")
        topic = urllib.parse.unquote_plus(topic)
        db = Databse()
        has_topic = db.has_topic(topic)
        db.close()
        if not has_topic: return "404 Not Found", not_found(url, method) 
        return "200 OK", add_entry(session, topic, params)
    else:
        return "404 Not Found", not_found(url, method)

def handle_connection(conx: socket.socket) -> None:
    req = conx.makefile("rb")
    # Reqline parsing
    reqline = req.readline().decode()
    method, url, version = reqline.split(" ", 2)
    assert method in ["GET", "POST"]
    # Header parsing
    headers: dict[str, str] = {}
    while True:
        line = req.readline().decode()
        if line == "\r\n": break
        header, value = line.split(":", 1)
        headers[header.casefold()] = value.strip()
    # Header handling
    if 'content-length' in headers:
        length = int(headers['content-length'])
        body = req.read(length).decode()
    else:
        body = None
    # Handling sessions
    if 'cookie' in headers:
        token = headers["cookie"][len("token="):]
    else:
        token = str(random.random())[2:]
    session = SESSIONS.setdefault(token, {})
    # Response generation
    status, body  = do_request(session, method, url, headers, body)
    response = "HTTP/1.0 {}\r\n".format(status)
    # Response Headers
    response += "Contrnt-Length: {}\r\n".format(len(body.encode()))
    csp = "default-src http://localhost:8000"
    response += "Content-Security-Policy: {}\r\n".format(csp)
    if "cookie" not in headers:
        template = "Set-Cookie: token={}; SameSite=Lax; HttpOnly\r\n"
        response += template.format(token)
    # Sending response
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
            import traceback
            print("[ERROR]: {}".format(e))
            traceback.print_exc()
            conx.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[INFO]: KeyboardInterrupt detected, exiting...")