import os
import atexit
import sqlite3
from time import time
from . import BASE_DIR

STORAGE_DIR = os.path.join(BASE_DIR, "storage.db")

class Storage:
    def __init__(self) -> None:
        self.con = sqlite3.connect(STORAGE_DIR)
        cursor = self.con.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER NOT NULL PRIMARY KEY,
                url VARCHAR(255) NOT NULL, 
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                url VARCHAR(255) NOT NULL PRIMARY KEY, 
                expires INT NOT NULL, 
                body TEXT NOT NULL
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookmarks (
                url VARCHAR(255) NOT NULL PRIMARY KEY,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        self.con.commit()
        cursor.close()
        atexit.register(self.con.close)

    # --- History
    def add_history(self, url: str) -> None:
        cursor = self.con.cursor()
        cursor.execute("INSERT INTO history (url) VALUES (?);", [url])
        self.con.commit()
        cursor.close()

    def get_history(self, url: str) -> tuple[int, str, str] | None:
        cursor = self.con.cursor()
        cursor.execute("SELECT * FROM history WHERE url = ?;", [url])
        data = cursor.fetchone()
        cursor.close()
        return data
    
    def delete_history(self, url: str) -> None:
        cursor = self.con.cursor()
        cursor.execute("DELETE FROM history WHERE url = ?;", [url])
        self.con.commit()
        cursor.close()

    def clear_history(self) -> None:
        cursor = self.con.cursor()
        cursor.execute("DELETE FROM history;")
        self.con.commit()
        cursor.close()

    # --- Cache
    def add_cache(self, url: str, expires: int, body: str) -> None:
        cursor = self.con.cursor()
        cursor.execute('INSERT INTO cache (url, expires, body) VALUES (?, ?, ?);', [url, expires, body])
        self.con.commit()
        cursor.close()

    def get_cache(self, url: str) -> str | None:
        cursor = self.con.cursor()
        cursor.execute("SELECT expires, body FROM cache WHERE url = ?;", [url])
        data = cursor.fetchone()
        cursor.close()
        if data is None:
            return None
        expires: int
        body: str
        expires, body = data
        now = int(time())
        if now > expires:
            self.delete_cache(url)
            return None
        return body
        
    def delete_cache(self, url: str) -> None:
        cursor = self.con.cursor()
        cursor.execute("DELETE FROM cache WHERE url = ?;", [url])
        self.con.commit()
        cursor.close()

    def clean_cache(self) -> None:
        cursor = self.con.cursor()
        cursor.execute("DELETE FROM cache;")
        self.con.commit()
        cursor.close()

    # --- Bookmarks
    def add_bookmark(self, url: str) -> None:
        cursor = self.con.cursor()
        cursor.execute("INSERT INTO bookmarks (url) VALUES (?);", [url])
        self.con.commit()
        cursor.close()

    def get_bookmark(self, url: str) -> tuple[str, str] | None:
        cursor = self.con.cursor()
        cursor.execute("SELECT * FROM bookmarks WHERE url = ?;", [url])
        data = cursor.fetchone()
        cursor.close()
        return data

    def get_all_bookmarks(self) -> list[tuple[str, str]]:
        cursor = self.con.cursor()
        cursor.execute("SELECT * FROM bookmarks")
        data = cursor.fetchall()
        cursor.close()
        return data

    def delete_bookmark(self, url: str) -> None:
        cursor = self.con.cursor()
        cursor.execute("DELETE FROM bookmarks WHERE url = ?;", [url])
        self.con.commit()
        cursor.close()

    def clear_bookmarks(self) -> None:
        cursor = self.con.cursor()
        cursor.execute("DELETE FROM bookmarks;")
        self.con.commit()
        cursor.close()
