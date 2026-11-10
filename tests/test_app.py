"""Tests met het verzonnen voorbeeldteam. Draaien met:  pip install -r requirements-dev.txt && pytest -q"""
import copy, io, json, os, tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["APP_PASSWORD"] = "geheim"
os.environ["SECRET_KEY"] = "test"

import openpyxl
from fastapi.testclient import TestClient
from app.main import app
from app.voorbeeld import voorbeeld_team, voorbeeld_maand
from app.solver import solve
from app.checker import check

client = TestClient(app)


def test_rekenkern_en_controle():
    t = voorbeeld_team(); m = voorbeeld_maand(t)
    r = solve(t, m, rekentijd=60)
    assert r["ok"] and r["open"] == []
    c = check(t, m, r["rooster"], None)
    assert c["totaal"] == 0, c["fouten"]
    # vakantie en vaste nachten zijn gerespecteerd
    ids = {e["naam"]: e["id"] for e in t["employees"]}
    assert all(x == "" for x in r["rooster"][ids["Chantal"]][:5])
    assert r["rooster"][ids["Jeroen"]][0] == "N"


def test_controle_ziet_fouten():
    t = voorbeeld_team(); m = voorbeeld_maand(t)
    r = solve(t, m, rekentijd=60)
    rooster = copy.deepcopy(r["rooster"])
    ids = {e["naam"]: e["id"] for e in t["employees"]}
    k = ids["Dewi"]
    rooster[k][9], rooster[k][10] = "L", "V"          # vroeg na laat
    rooster[ids["Chantal"]][0] = "V"                  # op een vakantiedag
    c = check(t, m, rooster, None)
    nr = {x["nr"]: x["fouten"] for x in c["regels"]}
    assert nr[4] >= 1 and nr[9] == 1


def test_inloggen_verplicht():
    c = TestClient(app)
    assert c.get("/api/team").status_code == 401
    assert c.post("/api/login", json={"wachtwoord": "fout"}).status_code == 401
    assert c.post("/api/login", json={"wachtwoord": "geheim"}).status_code == 200
    assert c.get("/api/team").status_code == 200


def test_hele_maand_via_de_server():
    c = TestClient(app)
    c.post("/api/login", json={"wachtwoord": "geheim"})
    key = c.post("/api/voorbeeld").json()["key"]
    r = c.post(f"/api/maanden/{key}/maken").json()
    assert r["ok"]
    ctrl = c.post(f"/api/maanden/{key}/controle", json={}).json()
    assert ctrl["totaal"] == 0
    x = c.get(f"/api/maanden/{key}/excel")
    assert x.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames == ["Rooster", "Uren", "Controle"]
    # volgende maand neemt de laatste 5 dagen en het saldo over
    y, mm = map(int, key.split("-"))
    volgende = f"{y}-{mm + 1:02d}"
    assert c.post("/api/maanden", json={"key": volgende}).status_code == 200
    nm = c.get(f"/api/maanden/{volgende}").json()["maand"]
    t = c.get("/api/team").json()
    jeroen = next(e["id"] for e in t["employees"] if e["naam"] == "Jeroen")
    assert nm["vorig"][jeroen] == r["maand"]["rooster"][jeroen][-5:]
    assert nm["saldo_bron"] == "berekend"
    # back-up en terugzetten
    b = c.get("/api/backup").content
    c.delete(f"/api/maanden/{volgende}")
    assert c.post("/api/restore", files={"bestand": ("b.json", b, "application/json")}).json()["ok"]
    assert any(m["key"] == volgende for m in c.get("/api/maanden").json())
