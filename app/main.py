"""Webserver van de roostermaker. Start lokaal met:  APP_PASSWORD=test uvicorn app.main:app --reload"""
import copy, hmac, os, secrets, threading, time, datetime as dt
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.concurrency import run_in_threadpool

from . import store
from .model import S, DAGNAMEN, MAANDEN, empty_team, empty_month, month_info, prev_key, new_employee, new_id, DEFAULT_SETTINGS
from .solver import solve
from .checker import check
from .importer import import_workbook, export_rooster
from .voorbeeld import voorbeeld_team, voorbeeld_maand, voorbeeld_met_rooster

PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
OP_RAILWAY = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("HTTPS_ONLY"))
STATIC = os.path.join(os.path.dirname(__file__), "static")
DEMO = os.environ.get("DEMO", "").lower() in ("1", "ja", "true", "yes")

if DEMO and store.get("team") is None:
    # demo zonder vaste opslag: na elke herstart begint de app met het verzonnen voorbeeldteam en een klaar rooster
    _t = voorbeeld_team()
    store.put("team", _t)
    store.put("month:2027-02", voorbeeld_met_rooster(_t))

app = FastAPI(title="Roostermaker", docs_url=None, redoc_url=None, openapi_url=None)
_solve_lock = threading.Lock()
_pogingen = {}


@app.middleware("http")
async def beveiliging(request: Request, call_next):
    p = request.url.path
    if p.startswith("/api/") and p not in ("/api/login", "/api/me", "/api/gezond") and not request.session.get("ok"):
        return JSONResponse({"detail": "Log eerst in."}, status_code=401)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
    if p.startswith("/api/"): resp.headers["Cache-Control"] = "no-store"
    return resp


# na de middleware hierboven toegevoegd, zodat de sessie er al is als die draait
app.add_middleware(SessionMiddleware, secret_key=SECRET, session_cookie="rm_sessie", max_age=7 * 24 * 3600,
                   same_site="strict", https_only=OP_RAILWAY)


# ---------- inloggen ----------
@app.get("/api/gezond")
def gezond():
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return {"ingelogd": bool(request.session.get("ok")), "wachtwoord_ingesteld": bool(PASSWORD), "demo": DEMO}


@app.post("/api/login")
async def login(request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    nu = time.time()
    lijst = [t for t in _pogingen.get(ip, []) if nu - t < 900]
    if len(lijst) >= 10:
        raise HTTPException(429, "Te vaak een verkeerd wachtwoord. Wacht een kwartier en probeer het opnieuw.")
    body = await request.json()
    if not PASSWORD:
        raise HTTPException(503, "Er is nog geen wachtwoord ingesteld op de server (APP_PASSWORD).")
    if not hmac.compare_digest(str(body.get("wachtwoord", "")).encode(), PASSWORD.encode()):
        lijst.append(nu); _pogingen[ip] = lijst
        time.sleep(1)
        raise HTTPException(401, "Dat wachtwoord klopt niet.")
    _pogingen.pop(ip, None)
    request.session["ok"] = True
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


# ---------- team ----------
def get_team():
    t = store.get("team")
    if t is None:
        t = empty_team()
    for k, v in DEFAULT_SETTINGS.items(): t["settings"].setdefault(k, v)
    return t


@app.get("/api/team")
def team_get():
    return get_team()


@app.put("/api/team")
async def team_put(request: Request):
    t = await request.json()
    if not isinstance(t, dict) or not isinstance(t.get("employees"), list) or not isinstance(t.get("bezetting"), list) or len(t["bezetting"]) != 7:
        raise HTTPException(400, "Onvolledige teamgegevens.")
    for e in t["employees"]:
        if not e.get("id"): e["id"] = new_id()
    store.put("team", t)
    return t


@app.get("/api/nieuwe-medewerker")
def nieuwe_medewerker():
    return new_employee()


# ---------- maanden ----------
def mkey(key):
    try:
        y, m = map(int, key.split("-"))
        assert 2020 <= y <= 2100 and 1 <= m <= 12
    except Exception:
        raise HTTPException(400, "Onbekende maand.")
    return f"{y}-{m:02d}"


def info_json(key, team):
    i = month_info(key, team["settings"])
    return {"label": i["label"], "nd": i["nd"], "wd": i["wd"], "md": i["md"], "y": i["y"], "m": i["m"],
            "vorig_dagen": [(i["first"] - dt.timedelta(5 - j)).day for j in range(5)],
            "vorig_wd": [(i["first"] - dt.timedelta(5 - j)).weekday() for j in range(5)]}


def status_van(m):
    if m.get("definitief"): return "definitief"
    if m.get("rooster"): return "rooster"
    return "voorbereiding"


@app.get("/api/maanden")
def maanden():
    uit = []
    for k, t in store.keys("month:"):
        m = store.get(k)
        key = k.split(":", 1)[1]
        y, mm = map(int, key.split("-"))
        uit.append({"key": key, "label": f"{MAANDEN[mm - 1]} {y}", "status": status_van(m), "gewijzigd": t})
    return sorted(uit, key=lambda x: x["key"], reverse=True)


@app.post("/api/maanden")
async def maand_nieuw(request: Request):
    body = await request.json()
    key = mkey(body.get("key", ""))
    if store.get("month:" + key) is not None:
        raise HTTPException(409, "Deze maand bestaat al.")
    team = get_team()
    m = empty_month(key)
    vorige = store.get("month:" + prev_key(key))
    if vorige and vorige.get("rooster"):
        # suggesties uit de vorige maand: laatste 5 dagen en het berekende eindsaldo (moet nog naast ORTEC gelegd worden)
        try:
            c = check(team, vorige)
            for p in c["personen"]:
                if not p["flex"]: m["saldo"][p["emp"]] = p["eindsaldo"]
            m["saldo_bron"] = "berekend"
        except Exception:
            pass
        for e in team["employees"]:
            r = vorige["rooster"].get(e["id"])
            if r: m["vorig"][e["id"]] = (["", "", "", "", ""] + list(r))[-5:]
        m["vorig_bron"] = "rooster"
    store.put("month:" + key, m)
    return {"key": key}


@app.get("/api/maanden/{key}")
def maand_get(key: str):
    key = mkey(key)
    m = store.get("month:" + key)
    if m is None: raise HTTPException(404, "Deze maand bestaat niet.")
    team = get_team()
    return {"maand": m, "info": info_json(key, team), "status": status_van(m)}


@app.put("/api/maanden/{key}")
async def maand_put(key: str, request: Request):
    key = mkey(key)
    m = await request.json()
    if not isinstance(m, dict): raise HTTPException(400, "Onvolledige maandgegevens.")
    m["key"] = key
    for f, leeg in (("vorig", {}), ("vast", {}), ("saldo", {}), ("verlof", {}), ("wensen", []), ("verg", {}), ("open", []), ("rapport", [])):
        m.setdefault(f, leeg)
    store.put("month:" + key, m)
    return {"ok": True, "status": status_van(m)}


@app.delete("/api/maanden/{key}")
def maand_weg(key: str):
    store.delete("month:" + mkey(key))
    return {"ok": True}


@app.post("/api/maanden/{key}/maken")
async def maand_maken(key: str):
    key = mkey(key)
    m = store.get("month:" + key)
    if m is None: raise HTTPException(404, "Deze maand bestaat niet.")
    team = get_team()
    if not [e for e in team["employees"] if (e.get("naam") or "").strip()]:
        raise HTTPException(400, "Er staan nog geen medewerkers in het team.")
    if not _solve_lock.acquire(blocking=False):
        raise HTTPException(409, "Er wordt al een rooster gemaakt. Wacht tot die klaar is.")
    try:
        res = await run_in_threadpool(solve, team, m)
    finally:
        _solve_lock.release()
    if not res["ok"]:
        return {"ok": False, "rapport": res["rapport"]}
    m = store.get("month:" + key) or m
    m["rooster"], m["verg"], m["open"], m["rapport"] = res["rooster"], res["verg"], res["open"], res["rapport"]
    m["gemaakt"] = time.time()
    m["definitief"] = False
    store.put("month:" + key, m)
    return {"ok": True, "maand": m}


@app.post("/api/maanden/{key}/controle")
async def maand_controle(key: str, request: Request):
    key = mkey(key)
    body = await request.json()
    m = body.get("maand") or store.get("month:" + key)
    if m is None: raise HTTPException(404, "Deze maand bestaat niet.")
    m["key"] = key
    if not m.get("rooster"): return {"leeg": True}
    return check(get_team(), m, m["rooster"], None)


@app.get("/api/maanden/{key}/excel")
def maand_excel(key: str):
    key = mkey(key)
    m = store.get("month:" + key)
    if m is None or not m.get("rooster"): raise HTTPException(404, "Er is nog geen rooster voor deze maand.")
    team = get_team()
    data = export_rooster(team, m, check(team, m, m["rooster"], None))
    i = month_info(key)
    naam = f"Rooster {i['label']}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{naam}"'})


@app.get("/api/maanden/{key}/versies")
def maand_versies(key: str):
    return store.history("month:" + mkey(key))


@app.post("/api/versies/{hid}/terugzetten")
def versie_terug(hid: int):
    k, v = store.history_item(hid)
    if k is None: raise HTTPException(404, "Deze versie bestaat niet meer.")
    store.put(k, v)
    return {"ok": True, "k": k}


# ---------- Excel inlezen, back-up ----------
@app.post("/api/import-excel")
async def import_excel(bestand: UploadFile = File(...), overschrijf_team: str = "ja"):
    data = await bestand.read()
    if len(data) > 15 * 1024 * 1024: raise HTTPException(400, "Dit bestand is te groot.")
    try:
        team, m = import_workbook(data)
    except KeyError as ex:
        raise HTTPException(400, f"Dit lijkt geen roostermaker-bestand: het blad {ex} ontbreekt.")
    except Exception as ex:
        raise HTTPException(400, f"Dit bestand kon niet gelezen worden ({ex}).")
    store.put("team", team)
    store.put("month:" + m["key"], m)
    return {"ok": True, "key": m["key"], "medewerkers": len(team["employees"])}


@app.post("/api/voorbeeld")
def voorbeeld():
    """Zet een verzonnen team en februari 2027 klaar om mee te oefenen. Vervangt het team; maanden blijven staan."""
    t = voorbeeld_team()
    store.put("team", t)
    key = "2027-02"
    if store.get("month:" + key) is not None: key = "2000-02"
    m = voorbeeld_maand(t, key)
    store.put("month:" + key, m)
    return {"ok": True, "key": key}


@app.get("/api/backup")
def backup():
    data = {"soort": "roostermaker-backup", "versie": 1, "gemaakt": time.time(), "gegevens": store.dump()}
    naam = f"roostermaker-backup-{dt.date.today().isoformat()}.json"
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{naam}"'})


@app.post("/api/restore")
async def restore(bestand: UploadFile = File(...)):
    import json
    try:
        data = json.loads(await bestand.read())
        assert data.get("soort") == "roostermaker-backup"
        geg = data["gegevens"]
        assert isinstance(geg, dict) and all(k == "team" or k.startswith("month:") for k in geg)
    except Exception:
        raise HTTPException(400, "Dit is geen back-up van de roostermaker.")
    for k, v in geg.items(): store.put(k, v)
    return {"ok": True, "aantal": len(geg)}


# ---------- pagina ----------
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/{pad:path}")
def index(pad: str):
    return FileResponse(os.path.join(STATIC, "index.html"), headers={"Cache-Control": "no-cache"})
