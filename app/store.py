"""Opslag: één SQLite-bestand in DATA_DIR (op Railway een volume op /data). Per sleutel een JSON-document, met de laatste 30 versies als vangnet."""
import json, os, sqlite3, threading, time

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB = os.path.join(DATA_DIR, "roostermaker.sqlite")
_lock = threading.Lock()
BEWAAR_VERSIES = 30


def _conn():
    c = sqlite3.connect(DB, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    return c


with _conn() as c:
    c.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL, t REAL NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS historie (id INTEGER PRIMARY KEY AUTOINCREMENT, k TEXT NOT NULL, v TEXT NOT NULL, t REAL NOT NULL)")


def get(k, default=None):
    with _conn() as c:
        r = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(r[0]) if r else default


def put(k, v):
    s = json.dumps(v, ensure_ascii=False)
    now = time.time()
    with _lock, _conn() as c:
        oud = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        if oud and oud[0] == s: return
        c.execute("INSERT INTO kv (k, v, t) VALUES (?, ?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, t=excluded.t", (k, s, now))
        if oud:
            laatste = c.execute("SELECT t FROM historie WHERE k=? ORDER BY id DESC LIMIT 1", (k,)).fetchone()
            # niet elke toetsaanslag bewaren: hooguit één versie per 2 minuten
            if not laatste or now - laatste[0] > 120:
                c.execute("INSERT INTO historie (k, v, t) VALUES (?, ?, ?)", (k, oud[0], now))
                c.execute("DELETE FROM historie WHERE k=? AND id NOT IN (SELECT id FROM historie WHERE k=? ORDER BY id DESC LIMIT ?)", (k, k, BEWAAR_VERSIES))


def delete(k):
    with _lock, _conn() as c:
        oud = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        if oud: c.execute("INSERT INTO historie (k, v, t) VALUES (?, ?, ?)", (k, oud[0], time.time()))
        c.execute("DELETE FROM kv WHERE k=?", (k,))


def keys(prefix=""):
    with _conn() as c:
        return [(r[0], r[1]) for r in c.execute("SELECT k, t FROM kv WHERE k LIKE ? ORDER BY k", (prefix + "%",))]


def history(k):
    with _conn() as c:
        return [{"id": r[0], "t": r[1]} for r in c.execute("SELECT id, t FROM historie WHERE k=? ORDER BY id DESC", (k,))]


def history_item(hid):
    with _conn() as c:
        r = c.execute("SELECT k, v FROM historie WHERE id=?", (hid,)).fetchone()
    return (r[0], json.loads(r[1])) if r else (None, None)


def dump():
    with _conn() as c:
        return {r[0]: json.loads(r[1]) for r in c.execute("SELECT k, v FROM kv")}
