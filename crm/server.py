"""CRM Taslak — ortak veri sunucusu.

Çalıştırma:
    pip install fastapi uvicorn
    python server.py

Ardından tarayıcıda http://localhost:8000 adresini açın.
Aynı ofis ağındaki arkadaşlarınız http://<sizin-ip-adresiniz>:8000 ile bağlanır.

Demo kullanıcılar: deniz / selin / emre  —  şifre hepsi için: 1234
Veriler bu klasördeki crm.db (SQLite) dosyasında saklanır.
"""
import hashlib
import os
import sqlite3
import uuid
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm.db")

app = FastAPI(title="CRM Taslak API")

# token -> görünen ad (sunucu yeniden başlarsa oturumlar düşer, tekrar giriş yeterli)
TOKENS: dict = {}


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


SEED_USERS = [
    ("deniz", "Deniz", "1234"),
    ("selin", "Selin", "1234"),
    ("emre",  "Emre",  "1234"),
]

SEED_CUSTOMERS = [
    ("Ahmet Yılmaz", "Yılmaz İnşaat",   "ahmet@yilmazinsaat.com", "0532 111 22 33", "Deniz", "Aktif",      "2026-01-15", "2026-07-25"),
    ("Zeynep Kaya",  "Kaya Tekstil",    "zeynep@kayatekstil.com", "0533 222 33 44", "Selin", "Potansiyel", "2026-02-03", "2026-07-10"),
    ("Mehmet Demir", "Demir Lojistik",  "mehmet@demirloj.com",    "0534 333 44 55", "Deniz", "Aktif",      "2026-03-21", "2026-08-01"),
    ("Elif Şahin",   "Şahin Gıda",      "elif@sahingida.com",     "0535 444 55 66", "Emre",  "Pasif",      "2026-04-10", ""),
    ("Can Öztürk",   "Öztürk Yazılım",  "can@ozturksoft.com",     "0536 555 66 77", "Selin", "Potansiyel", "2026-05-28", "2026-07-18"),
    ("Ayşe Çelik",   "Çelik Mobilya",   "ayse@celikmobilya.com",  "0537 666 77 88", "Deniz", "Aktif",      "2026-06-14", "2026-07-30"),
    ("Burak Arslan", "Arslan Otomotiv", "burak@arslanoto.com",    "0538 777 88 99", "Emre",  "Potansiyel", "2026-07-02", "2026-07-22"),
]


def init_db() -> None:
    con = db()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username  TEXT PRIMARY KEY,
            display   TEXT NOT NULL,
            pass_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS customers (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            company      TEXT DEFAULT '',
            email        TEXT DEFAULT '',
            phone        TEXT DEFAULT '',
            assignee     TEXT DEFAULT '',
            status       TEXT DEFAULT 'Potansiyel',
            date         TEXT NOT NULL,
            next_contact TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            author      TEXT NOT NULL,
            text        TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );
    """)
    if not con.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        con.executemany("INSERT INTO users VALUES (?,?,?)",
                        [(u, d, sha(p)) for u, d, p in SEED_USERS])
    if not con.execute("SELECT 1 FROM customers LIMIT 1").fetchone():
        con.executemany(
            "INSERT INTO customers (name, company, email, phone, assignee, status, date, next_contact) "
            "VALUES (?,?,?,?,?,?,?,?)", SEED_CUSTOMERS)
    con.commit()
    con.close()


init_db()


# ---------- Modeller ----------

class LoginIn(BaseModel):
    username: str
    password: str


class CustomerIn(BaseModel):
    name: str
    company: str = ""
    email: str = ""
    phone: str = ""
    assignee: str = ""
    status: str = "Potansiyel"
    date: str
    next_contact: str = ""


class NoteIn(BaseModel):
    text: str


# ---------- Kimlik doğrulama ----------

def current_user(authorization: str = Header("")) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    if token not in TOKENS:
        raise HTTPException(status_code=401, detail="Oturum geçersiz, lütfen tekrar giriş yapın.")
    return TOKENS[token]


@app.post("/api/login")
def login(body: LoginIn):
    con = db()
    row = con.execute("SELECT display, pass_hash FROM users WHERE username = ?",
                      (body.username.strip().lower(),)).fetchone()
    con.close()
    if not row or row["pass_hash"] != sha(body.password):
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı.")
    token = uuid.uuid4().hex
    TOKENS[token] = row["display"]
    return {"token": token, "display": row["display"]}


@app.get("/api/me")
def me(user: str = Depends(current_user)):
    return {"display": user}


# ---------- Müşteriler ----------

@app.get("/api/customers")
def list_customers(user: str = Depends(current_user)):
    con = db()
    rows = [dict(r) for r in con.execute("SELECT * FROM customers").fetchall()]
    con.close()
    return rows


@app.post("/api/customers", status_code=201)
def create_customer(body: CustomerIn, user: str = Depends(current_user)):
    con = db()
    cur = con.execute(
        "INSERT INTO customers (name, company, email, phone, assignee, status, date, next_contact) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (body.name, body.company, body.email, body.phone, body.assignee,
         body.status, body.date, body.next_contact))
    con.commit()
    new_id = cur.lastrowid
    con.close()
    return {"id": new_id}


@app.put("/api/customers/{cid}")
def update_customer(cid: int, body: CustomerIn, user: str = Depends(current_user)):
    con = db()
    cur = con.execute(
        "UPDATE customers SET name=?, company=?, email=?, phone=?, assignee=?, status=?, date=?, next_contact=? "
        "WHERE id=?",
        (body.name, body.company, body.email, body.phone, body.assignee,
         body.status, body.date, body.next_contact, cid))
    con.commit()
    con.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Müşteri bulunamadı.")
    return {"ok": True}


@app.delete("/api/customers/{cid}", status_code=204)
def delete_customer(cid: int, user: str = Depends(current_user)):
    con = db()
    con.execute("DELETE FROM customers WHERE id=?", (cid,))
    con.commit()
    con.close()


# ---------- Notlar ----------

@app.get("/api/customers/{cid}/notes")
def list_notes(cid: int, user: str = Depends(current_user)):
    con = db()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM notes WHERE customer_id=? ORDER BY id DESC", (cid,)).fetchall()]
    con.close()
    return rows


@app.post("/api/customers/{cid}/notes", status_code=201)
def create_note(cid: int, body: NoteIn, user: str = Depends(current_user)):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Not boş olamaz.")
    con = db()
    if not con.execute("SELECT 1 FROM customers WHERE id=?", (cid,)).fetchone():
        con.close()
        raise HTTPException(status_code=404, detail="Müşteri bulunamadı.")
    con.execute(
        "INSERT INTO notes (customer_id, author, text, created_at) VALUES (?,?,?,?)",
        (cid, user, text, datetime.now().strftime("%Y-%m-%d %H:%M")))
    con.commit()
    con.close()
    return {"ok": True}


# ---------- Arayüz ----------

@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    # 0.0.0.0: aynı ağdaki diğer bilgisayarlar da bağlanabilsin diye
    uvicorn.run(app, host="0.0.0.0", port=8000)
