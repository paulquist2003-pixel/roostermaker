"""Controle van een (eventueel met de hand aangepast) rooster: telt per harde regel de fouten en rekent de uren uit.

Onafhankelijk van de rekenkern geschreven, zodat een fout in het model hier zichtbaar wordt.
"""
from .model import S, DAGNAMEN, DAGKORT, num
from .solver import prepare

REGELS = {
    1: "Alleen V, T, L, N of leeg",
    2: "Niet meer dan {max_rij} dagen achter elkaar werken",
    3: "Geen werk-vrij-werk (los vrije dag)",
    4: "Geen vroege dienst direct na een late",
    5: "Na een nacht alleen nacht of vrij",
    6: "Bezetting klopt",
    7: "Niet te veel tussendiensten",
    8: "Eindsaldo binnen plus of min {saldogrens} uur",
    9: "Niet ingepland bij vakantie of sterke wens",
    10: "Nooit- en Moet-afspraken gehaald",
    11: "Niet meer dan {max_nacht_rij} nachten achter elkaar",
}


def check(team, month, rooster=None, verg=None):
    """rooster: {emp_id: [letters]} (standaard month['rooster']). verg: {emp_id: 0/1} wie bij de vergadering is.

    Als verg ontbreekt, wordt die afgeleid: iedereen die erbij hoort, tenzij nacht de dag ervoor of die dag.
    """
    P = prepare(team, month)
    info, st = P["info"], P["st"]
    ND, wd, MD = info["nd"], info["wd"], info["md"]
    rooster = rooster if rooster is not None else (month.get("rooster") or {})
    ids, namen = P["ids"], P["namen"]
    U_DAG, U_NACHT = num(st["u_dag"], 8), num(st["u_nacht"], 9)
    GRENS, MAX_RIJ, MAX_N, MAX_T = num(st["saldogrens"], 8), int(num(st["max_rij"], 5)), int(num(st["max_nacht_rij"], 7)), int(num(st["max_t"], 1))
    VV, VV_V, VV_L, VV_T = (num(st.get(k), 0) for k in ("verg_vrij", "verg_v", "verg_l", "verg_t"))
    UREN_FTE = num(st["uren_fte"], 36)
    OFFSET = info["first"].weekday()
    week = [(d + OFFSET) // 7 for d in range(ND)]
    NW = max(week) + 1
    dm = [d.day for d in info["days"]]

    def dstr(d): return f"{DAGNAMEN[wd[d]]} {dm[d]}"
    fouten = []

    def fout(regel, tekst, e=None, d=None):
        fouten.append({"regel": regel, "tekst": tekst, "emp": ids[e] if e is not None else None, "dag": d + 1 if d is not None else None})
    R = []
    for k, i in enumerate(ids):
        r = list(rooster.get(i) or [""] * ND)[:ND]
        r += [""] * (ND - len(r))
        R.append([(x or "").strip().upper() for x in r])
    personen = []
    for e in range(len(ids)):
        r, vorig = R[e], P["vorig"][e]
        n = namen[e]
        for d in range(ND):
            if r[d] and r[d] not in S: fout(1, f"{n}: '{r[d]}' op {dstr(d)} is geen dienst", e, d)
        bij_verg = False
        if MD >= 1 and P["naar_verg"][e] and not P["vast_nacht"][e] and not P["flex"][e]:
            if verg is not None and i_in(verg, ids[e]):
                bij_verg = bool(verg[ids[e]])
            else:
                bij_verg = r[MD] != "N" and r[MD - 1] != "N"
        rij = vorig + r
        wrk = [1 if x else 0 for x in rij]
        if bij_verg: wrk[5 + MD] = 1
        if not P["vast_nacht"][e] and not P["flex"][e]:
            run = 0
            for j, x in enumerate(wrk):
                run = run + 1 if x else 0
                if j >= 5 and run == MAX_RIJ + 1: fout(2, f"{n} werkt meer dan {MAX_RIJ} dagen achter elkaar (t/m {dstr(j - 5)})", e, j - 5)
            if P["reeksregels"][e]:
                for j in range(3, len(wrk) - 2):
                    if wrk[j] and not wrk[j + 1] and wrk[j + 2] and j + 1 >= 5:
                        fout(3, f"{n} heeft een losse vrije dag op {dstr(j + 1 - 5)}", e, j + 1 - 5)
        for j in range(4, len(rij) - 1):
            if rij[j] == "L" and rij[j + 1] == "V": fout(4, f"{n}: vroege dienst na een late op {dstr(j + 1 - 5)}", e, j + 1 - 5)
            if rij[j] == "N" and rij[j + 1] in ("V", "T", "L"): fout(5, f"{n}: dagdienst na een nacht op {dstr(j + 1 - 5)}", e, j + 1 - 5)
        run = 0
        for j, x in enumerate(rij):
            run = run + 1 if x == "N" else 0
            if j >= 5 and run == MAX_N + 1: fout(11, f"{n} heeft meer dan {MAX_N} nachten achter elkaar (t/m {dstr(j - 5)})", e, j - 5)
        for d in range(ND):
            if not r[d]: continue
            if (e, d) in P["sterk"]:
                fout(9, f"{n} staat ingepland op {dstr(d)}, maar heeft dan {'vakantie' if (e, d) in P['vakantie'] else 'een sterke wens vrij'}", e, d)
            if not P["vast_nacht"][e] and not P["flex"][e]:
                if P["dagpref"][e][wd[d]] == "Nooit": fout(10, f"{n} werkt nooit op {DAGNAMEN[wd[d]]}, maar staat op {dstr(d)}", e, d)
                if r[d] in ("V", "T", "L") and P["dienstpref"][e]["VTL".index(r[d])] == "Nooit": fout(10, f"{n} doet nooit {r[d]}, maar staat op {dstr(d)}", e, d)
                if r[d] == "N" and P["nachtpref"][e] == "Nooit": fout(10, f"{n} doet nooit nachten, maar staat op {dstr(d)}", e, d)
        uren_d = [(U_NACHT if x == "N" else U_DAG if x in S else 0.0) for x in r]
        if bij_verg: uren_d[MD] += {"V": VV_V, "L": VV_L, "T": VV_T}.get(r[MD], VV)
        gewerkt = sum(uren_d)
        eind = P["beginsaldo"][e] + gewerkt + P["verlof"][e] - P["contract"][e]
        if not P["flex"][e] and abs(eind) > GRENS + 0.001: fout(8, f"{n} eindigt op {eind:+.1f} uur (grens {GRENS:g})", e)
        weken = []
        for wk in range(NW):
            dagen = [d for d in range(ND) if week[d] == wk]
            doel = P["fte"][e] * UREN_FTE * sum(1 for d in dagen if (e, d) not in P["vakantie"]) / 7
            weken.append(round(sum(uren_d[d] for d in dagen) - doel, 1))
        personen.append({"emp": ids[e], "naam": n, "contract": round(P["contract"][e], 1), "verlof": P["verlof"][e], "beginsaldo": P["beginsaldo"][e],
                         "gewerkt": round(gewerkt, 1), "eindsaldo": round(eind, 1), "verg": bij_verg, "weken": weken,
                         "diensten": {s: r.count(s) for s in S}, "flex": P["flex"][e], "vast_nacht": P["vast_nacht"][e]})
    for (be, bwd, bweek, bs, a) in P["bijzonder"]:
        for d in range(ND):
            if wd[d] == bwd and (bweek is None or bweek == (dm[d] - 1) // 7 + 1):
                if a == "Nooit" and R[be][d] == S[bs]: fout(10, f"{namen[be]} doet nooit {S[bs]} op {DAGKORT[bwd]}, maar staat op {dstr(d)}", be, d)
                if a == "Moet" and R[be][d] != S[bs]: fout(10, f"{namen[be]} moet {S[bs]} op {dstr(d)}", be, d)
    bez, T_PRIO = P["bez"], P["t_prio"]
    dagtelling = []
    for d in range(ND):
        col = [R[e][d] for e in range(len(ids))]
        b = bez[wd[d]]
        tel = {s: col.count(s) for s in S}
        dagtelling.append(tel)
        for j, s in enumerate(S):
            nodig = int(b[j])
            if s == "T" and nodig == 0:
                mx = MAX_T if wd[d] <= 3 and T_PRIO.get(wd[d]) is not None else 0
                if tel["T"] > mx: fout(7, f"{dstr(d)}: {tel['T']} tussendiensten, maximaal {mx}", None, d)
                continue
            if tel[s] != nodig:
                fout(6, f"{dstr(d)}: {tel[s]}x {s} ingepland, nodig is {nodig}" + (" (open dienst)" if tel[s] < nodig else ""), None, d)
    telling = {k: 0 for k in REGELS}
    for f in fouten: telling[f["regel"]] += 1
    regels = [{"nr": k, "tekst": v.format(**{kk: (int(vv) if isinstance(vv, (int, float)) and float(vv).is_integer() else vv) for kk, vv in st.items()}), "fouten": telling[k]} for k, v in REGELS.items()]
    return {"totaal": len(fouten), "regels": regels, "fouten": fouten, "personen": personen, "dagtelling": dagtelling, "weken": NW}


def i_in(d, k):
    return isinstance(d, dict) and k in d
