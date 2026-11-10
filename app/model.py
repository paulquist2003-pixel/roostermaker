"""Gedeelde gegevensvorm en hulpfuncties.

team = {
  "settings": {...},              # zie DEFAULT_SETTINGS
  "bezetting": [[V,T,L,N] x 7],   # maandag..zondag
  "employees": [ {id, naam, fte, vast_nacht, nachten, vergadering, reeksregels,
                  dagen[7], diensten{V,T,L}, liefst_max_rij, min_nacht_rij, max_aandeel_t, min_dd, opmerking} ],
  "afspraken": [ {emp, weekdag(0-6), week(None|1-5), dienst, soort} ],
}
month = {
  "key": "2027-03",
  "vorig": {emp: [5 letters]},        # laatste 5 dagen vorige maand
  "vast":  {emp: {"dag": letter}},    # vaste diensten (o.a. nachten), dag = "1".."31"
  "saldo": {emp: uren}, "verlof": {emp: uren},
  "wensen": [ {emp, dag, soort: "sterk"|"gewoon", reden} ],
  "rooster": {emp: [letters]} | None, "verg": {emp: 0/1}, "open": [...], "rapport": [[a, b]], ...
}
"""
import calendar, datetime as dt, uuid

S = ["V", "T", "L", "N"]
DAGNAMEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
DAGKORT = ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"]
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"]

DEFAULT_SETTINGS = {
    "uren_fte": 36, "u_dag": 8, "u_nacht": 9, "saldogrens": 8,
    "max_rij": 5, "max_nacht_rij": 7, "max_t": 1,
    "t_prio": [1, 2, 3, 1],               # extra tussendienst ma, di, wo, do: 1 = eerst ... None = nooit
    "vergadering": True, "verg_vrij": 4, "verg_v": 2, "verg_l": 2, "verg_t": 0,
    "rekentijd": 60,
}
DEFAULT_BEZETTING = [[2, 0, 2, 1], [2, 0, 2, 1], [2, 0, 2, 1], [2, 0, 2, 1], [2, 1, 1, 1], [1, 0, 1, 1], [1, 0, 2, 1]]


def new_id():
    return uuid.uuid4().hex[:8]


def empty_team():
    return {"settings": dict(DEFAULT_SETTINGS), "bezetting": [list(r) for r in DEFAULT_BEZETTING], "employees": [], "afspraken": []}


def new_employee(naam="", fte=0.0):
    return {"id": new_id(), "naam": naam, "fte": fte, "vast_nacht": False, "nachten": "Neutraal", "vergadering": True, "reeksregels": True,
            "dagen": [""] * 7, "diensten": {"V": "", "T": "", "L": ""}, "liefst_max_rij": None, "min_nacht_rij": None,
            "max_aandeel_t": None, "min_dd": None, "opmerking": ""}


def month_info(key, settings=None):
    y, m = map(int, key.split("-"))
    nd = calendar.monthrange(y, m)[1]
    first = dt.date(y, m, 1)
    days = [first + dt.timedelta(d) for d in range(nd)]
    md = -1
    if settings is None or settings.get("vergadering", True):
        first_mon = (7 - first.weekday()) % 7
        md = first_mon + 7
        if md >= nd: md = -1
    return {"y": y, "m": m, "nd": nd, "first": first, "days": days, "wd": [d.weekday() for d in days], "md": md,
            "label": f"{MAANDEN[m - 1]} {y}"}


def prev_key(key):
    y, m = map(int, key.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def empty_month(key):
    return {"key": key, "vorig": {}, "vast": {}, "saldo": {}, "verlof": {}, "wensen": [], "rooster": None, "verg": {}, "open": [], "rapport": []}


def num(v, default=0.0):
    try:
        if v is None or v == "": return default
        return float(v)
    except (TypeError, ValueError):
        return default
