"""Inlezen van het oude Excel-bestand (Roostermaker_*.xlsx) en wegschrijven van een rooster naar Excel."""
import datetime as dt
import io
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .model import S, DAGKORT, DAGNAMEN, empty_team, empty_month, new_employee, month_info, num


def _t(v):
    return "" if v is None else str(v).strip()


def _n(v):
    if v is None or _t(v) == "": return None
    try: return float(v)
    except (TypeError, ValueError): return None


def _date(v):
    if isinstance(v, dt.datetime): return v.date()
    if isinstance(v, dt.date): return v
    return None


def import_workbook(data, rooster_blad="Rooster_waarden"):
    """Leest team, maand en (als aanwezig) het rooster uit een Roostermaker-werkboek. Geeft (team, month)."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    I, M, V, B, C, W = (wb[n] for n in ("Instellingen", "Medewerkers", "Voorkeuren", "Bezetting", "Conceptrooster", "Wensen"))
    first = _date(I["B4"].value)
    if first is None: raise ValueError("In Instellingen!B4 staat geen datum.")
    key = f"{first.year}-{first.month:02d}"
    team = empty_team()
    st = team["settings"]
    for k, cel in (("uren_fte", "B8"), ("u_dag", "B9"), ("u_nacht", "B10"), ("saldogrens", "B11"), ("max_rij", "B12"),
                   ("max_nacht_rij", "B13"), ("max_t", "B14"), ("verg_vrij", "B23"), ("verg_v", "B24"), ("verg_l", "B25"),
                   ("verg_t", "B26"), ("rekentijd", "B28")):
        x = _n(I[cel].value)
        if x is not None: st[k] = int(x) if float(x).is_integer() else x
    st["t_prio"] = [(int(x) if x is not None else None) for x in (_n(I.cell(17 + k, 2).value) for k in range(4))]
    st["vergadering"] = _t(I["B22"].value) == "Ja"
    team["bezetting"] = [[int(num(B.cell(4 + d, 2 + s).value)) for s in range(4)] for d in range(7)]
    info = month_info(key, st)
    month = empty_month(key)
    rijen, naam2id = [], {}
    for i in range(15):
        naam = _t(M.cell(5 + i, 1).value)
        if not naam: continue
        e = new_employee(naam, num(M.cell(5 + i, 2).value))
        e["vast_nacht"] = _t(M.cell(5 + i, 3).value) == "Ja"
        e["nachten"] = _t(M.cell(5 + i, 4).value) or "Neutraal"
        e["vergadering"] = _t(M.cell(5 + i, 5).value) == "Ja"
        e["reeksregels"] = _t(M.cell(5 + i, 6).value) != "Nee"
        e["dagen"] = [_t(V.cell(5 + i, 2 + k).value) for k in range(7)]
        e["diensten"] = {s: _t(V.cell(5 + i, 9 + k).value) for k, s in enumerate("VTL")}
        for k, f in enumerate(("liefst_max_rij", "min_nacht_rij", "max_aandeel_t", "min_dd")):
            e[f] = _n(V.cell(5 + i, 12 + k).value)
        team["employees"].append(e)
        naam2id[naam] = e["id"]
        rijen.append((i, e["id"]))
        month["saldo"][e["id"]] = num(M.cell(5 + i, 7).value)
        month["verlof"][e["id"]] = num(M.cell(5 + i, 8).value)
        month["vorig"][e["id"]] = [(_t(C.cell(6 + i, 2 + j).value).upper() if _t(C.cell(6 + i, 2 + j).value).upper() in S else "") for j in range(5)]
        vast = {}
        for d in range(info["nd"]):
            x = _t(C.cell(6 + i, 7 + d).value).upper()
            if x in S: vast[str(d + 1)] = x
        month["vast"][e["id"]] = vast
    for r in range(24, 44):
        n = _t(V.cell(r, 1).value)
        wdk = _t(V.cell(r, 2).value)
        if n in naam2id and wdk in DAGKORT and _t(V.cell(r, 4).value).upper() in S:
            wk = _n(V.cell(r, 3).value)
            team["afspraken"].append({"emp": naam2id[n], "weekdag": DAGKORT.index(wdk), "week": None if wk is None else int(wk),
                                      "dienst": _t(V.cell(r, 4).value).upper(), "soort": _t(V.cell(r, 5).value) or "Graag"})
    for r in range(5, 301):
        n, d = _t(W.cell(r, 1).value), _date(W.cell(r, 2).value)
        if n in naam2id and d and d.year == first.year and d.month == first.month:
            month["wensen"].append({"emp": naam2id[n], "dag": d.day, "soort": "sterk" if _t(W.cell(r, 3).value).lower() == "sterk" else "gewoon",
                                    "reden": _t(W.cell(r, 4).value)})
    if rooster_blad in wb.sheetnames:
        R = wb[rooster_blad]
        rooster = {}
        for i, eid in rijen:
            rooster[eid] = [(_t(R.cell(2 + i, 2 + d).value).upper() if _t(R.cell(2 + i, 2 + d).value).upper() in S else "") for d in range(info["nd"])]
        if any(any(r) for r in rooster.values()): month["rooster"] = rooster
    return team, month


DIENSTTIJD = {"V": "07:30-15:30", "T": "11:00-19:00", "L": "15:00-23:00", "N": "22:45-07:45"}
KLEUR = {"V": "DDEBF7", "T": "E2EFDA", "L": "FCE4D6", "N": "D9D2E9"}


def export_rooster(team, month, controle=None):
    """Maakt een Excel-bestand met het rooster (om over te nemen in ORTEC) en een blad met de uren."""
    info = month_info(month["key"], team["settings"])
    nd, wd, md = info["nd"], info["wd"], info["md"]
    rooster = month.get("rooster") or {}
    emps = [e for e in team["employees"] if (e.get("naam") or "").strip()]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rooster"
    dun = Side(style="thin", color="BBBBBB")
    rand = Border(left=dun, right=dun, top=dun, bottom=dun)
    vet = Font(bold=True)
    mid = Alignment(horizontal="center", vertical="center")
    ws.cell(1, 1, f"Rooster {info['label']}").font = Font(bold=True, size=14)
    ws.cell(2, 1, "Medewerker").font = vet
    for d in range(nd):
        c = ws.cell(2, 2 + d, f"{DAGKORT[wd[d]]}\n{d + 1}")
        c.font, c.alignment, c.border = vet, Alignment(horizontal="center", wrap_text=True), rand
        if wd[d] >= 5: c.fill = PatternFill("solid", fgColor="EEEEEE")
        ws.column_dimensions[openpyxl.utils.get_column_letter(2 + d)].width = 4.5
    ws.row_dimensions[2].height = 30
    ws.column_dimensions["A"].width = 16
    verg = {p["emp"]: p["verg"] for p in (controle or {}).get("personen", [])}
    for k, e in enumerate(emps):
        r = 3 + k
        ws.cell(r, 1, e["naam"]).border = rand
        rij = rooster.get(e["id"]) or [""] * nd
        for d in range(nd):
            x = rij[d] if d < len(rij) else ""
            tekst = x
            if d == md and verg.get(e["id"]): tekst = (x + "+") if x else "VG"
            c = ws.cell(r, 2 + d, tekst)
            c.alignment, c.border = mid, rand
            if x in KLEUR: c.fill = PatternFill("solid", fgColor=KLEUR[x])
    r = 4 + len(emps)
    for s in S:
        ws.cell(r, 1, f"Open {s}")
        for d in range(nd):
            if controle:
                n = int(team["bezetting"][wd[d]][S.index(s)]) - controle["dagtelling"][d][s]
            else:
                n = sum(o["aantal"] for o in month.get("open") or [] if o["dag"] == d + 1 and o["dienst"] == s)
            if n > 0: ws.cell(r, 2 + d, n).fill = PatternFill("solid", fgColor="FF9999")
        r += 1
    r += 1
    ws.cell(r, 1, "Uitleg").font = vet
    for s in S:
        r += 1
        ws.cell(r, 1, s).fill = PatternFill("solid", fgColor=KLEUR[s])
        ws.cell(r, 2, {"V": "vroeg", "T": "tussen", "L": "laat", "N": "nacht"}[s] + " " + DIENSTTIJD[s])
    if md >= 0:
        r += 1
        ws.cell(r, 1, "VG / +")
        ws.cell(r, 2, f"teamvergadering {DAGNAMEN[wd[md]]} {md + 1} 13:00-17:00 (VG = vrij, alleen vergadering; + = dienst en vergadering)")
    ws.freeze_panes = "B3"
    if controle:
        u = wb.create_sheet("Uren")
        kop = ["Medewerker", "Contract", "Verlof", "Beginsaldo", "Gewerkt", "Eindsaldo"] + [f"Week {i + 1}" for i in range(controle["weken"])]
        for j, h in enumerate(kop): u.cell(1, 1 + j, h).font = vet
        for k, p in enumerate(controle["personen"]):
            vals = [p["naam"], p["contract"], p["verlof"], p["beginsaldo"], p["gewerkt"], p["eindsaldo"]] + p["weken"]
            for j, v in enumerate(vals): u.cell(2 + k, 1 + j, v)
        u.column_dimensions["A"].width = 16
        c = wb.create_sheet("Controle")
        c.cell(1, 1, "Regel").font = vet; c.cell(1, 2, "Fouten").font = vet
        for k, reg in enumerate(controle["regels"]):
            c.cell(2 + k, 1, f"{reg['nr']}. {reg['tekst']}"); c.cell(2 + k, 2, reg["fouten"])
        rr = 3 + len(controle["regels"])
        for f in controle["fouten"]:
            c.cell(rr, 1, f["tekst"]); rr += 1
        c.column_dimensions["A"].width = 70
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
