"""Rekenkern: zoekt het rooster dat alle harde regels haalt en zo veel mogelijk voorkeuren (scipy milp).

Zelfde model als roostermaker_code.txt (Python in Excel), maar met de gegevens als JSON in plaats van uit Excel-bladen.
"""
import time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix

from .model import S, DAGNAMEN, DAGKORT, month_info, num

# Gewichten (zachte regels)
K_DAG = {"Vrij": 80.0, "Liever niet": 30.0}
K_DIENST = {"Graag": -3.0, "Liever niet": 20.0}
K_NACHT = {"Graag": 4.0, "Neutraal": 150.0}
K_BIJZ = {"Graag": -60.0, "Liever niet": 30.0}
W_SALDO, W_WEEK, WEEK_MARGE = 1000.0, 25.0, 4.0
W_EERLIJK = [(4, 5.0), (4, 20.0), (8, 120.0), (1e3, 400.0)]
W_WENS_GEWOON, W_START = 20.0, 2.0
W_OPEN = 100000.0


def prepare(team, month):
    """Zet team + maand om in de vorm die het model en de controle gebruiken."""
    st = team["settings"]
    info = month_info(month["key"], st)
    emps = [e for e in team["employees"] if (e.get("naam") or "").strip()]
    P = {"info": info, "emps": emps, "st": st}
    ND = info["nd"]
    P["ids"] = [e["id"] for e in emps]
    P["namen"] = [e["naam"].strip() for e in emps]
    P["fte"] = [num(e.get("fte")) for e in emps]
    P["vast_nacht"] = [bool(e.get("vast_nacht")) for e in emps]
    P["nachtpref"] = [e.get("nachten") or "Neutraal" for e in emps]
    P["naar_verg"] = [bool(e.get("vergadering", True)) for e in emps]
    P["reeksregels"] = [e.get("reeksregels", True) is not False for e in emps]
    P["beginsaldo"] = [num(month.get("saldo", {}).get(e["id"])) for e in emps]
    P["verlof"] = [num(month.get("verlof", {}).get(e["id"])) for e in emps]
    P["contract"] = [P["fte"][k] * num(st["uren_fte"], 36) * ND / 7 for k in range(len(emps))]
    P["flex"] = [P["fte"][k] == 0 and not P["vast_nacht"][k] for k in range(len(emps))]
    P["te_werken"] = [P["contract"][k] - P["verlof"][k] - P["beginsaldo"][k] for k in range(len(emps))]
    P["dagpref"] = [list((e.get("dagen") or [""] * 7))[:7] for e in emps]
    P["dienstpref"] = [[(e.get("diensten") or {}).get(s, "") for s in "VTL"] + [""] for e in emps]
    P["liefst_max_rij"] = [e.get("liefst_max_rij") for e in emps]
    P["min_nacht_rij"] = [e.get("min_nacht_rij") for e in emps]
    P["max_aandeel_t"] = [e.get("max_aandeel_t") for e in emps]
    P["min_dd"] = [e.get("min_dd") for e in emps]
    idx = {i: k for k, i in enumerate(P["ids"])}
    P["idx"] = idx
    P["bijzonder"] = []
    for a in team.get("afspraken", []):
        if a.get("emp") in idx and a.get("dienst") in S and a.get("weekdag") is not None:
            wk = a.get("week")
            P["bijzonder"].append((idx[a["emp"]], int(a["weekdag"]), None if wk in (None, "") else int(wk), S.index(a["dienst"]), a.get("soort") or "Graag"))
    P["bez"] = np.array([[num(x) for x in r] for r in team["bezetting"]])
    P["vorig"] = [[(x if x in S else "") for x in (month.get("vorig", {}).get(i) or [""] * 5)][:5] for i in P["ids"]]
    vast = {}
    for i in P["ids"]:
        for dstr_, x in (month.get("vast", {}).get(i) or {}).items():
            d = int(dstr_) - 1
            if 0 <= d < ND and x in S: vast[(idx[i], d)] = x
    P["vast"] = vast
    sterk, gewoon, vakantie = set(), set(), set()
    for w in month.get("wensen", []):
        if w.get("emp") not in idx: continue
        d = int(w["dag"]) - 1
        if not (0 <= d < ND): continue
        key = (idx[w["emp"]], d)
        (sterk if w.get("soort") == "sterk" else gewoon).add(key)
        if "vakantie" in (w.get("reden") or "").lower(): vakantie.add(key)
    P["sterk"], P["gewoon"], P["vakantie"] = sterk, gewoon, vakantie
    tp = list(st.get("t_prio") or [None] * 4)
    P["t_prio"] = {k: (None if tp[k] in (None, "") else num(tp[k])) for k in range(4)}
    return P


def solve(team, month, rekentijd=None):
    P = prepare(team, month)
    info, st = P["info"], P["st"]
    ND, wd, MD = info["nd"], info["wd"], info["md"]
    NE = len(P["ids"])
    namen, fte, vast_nacht, flex = P["namen"], P["fte"], P["vast_nacht"], P["flex"]
    nachtpref, naar_verg, reeksregels = P["nachtpref"], P["naar_verg"], P["reeksregels"]
    beginsaldo, verlof, contract, te_werken = P["beginsaldo"], P["verlof"], P["contract"], P["te_werken"]
    dagpref, dienstpref = P["dagpref"], P["dienstpref"]
    liefst_max_rij, min_nacht_rij, max_aandeel_t, min_dd = P["liefst_max_rij"], P["min_nacht_rij"], P["max_aandeel_t"], P["min_dd"]
    bijzonder, bez, vorig, vast = P["bijzonder"], P["bez"], P["vorig"], P["vast"]
    sterk, gewoon, vakantie = P["sterk"], P["gewoon"], P["vakantie"]
    T_PRIO = P["t_prio"]
    UREN_FTE, U_DAG, U_NACHT = num(st["uren_fte"], 36), num(st["u_dag"], 8), num(st["u_nacht"], 9)
    SALDOGRENS = num(st["saldogrens"], 8)
    MAX_RIJ, MAX_T = int(num(st["max_rij"], 5)), int(num(st["max_t"], 1))
    VERG_VRIJ, VERG_V, VERG_L, VERG_T = (num(st.get(k), 0) for k in ("verg_vrij", "verg_v", "verg_l", "verg_t"))
    REKENTIJD = num(rekentijd if rekentijd is not None else st.get("rekentijd"), 60)
    dm = [d.day for d in info["days"]]
    nde = [(x - 1) // 7 + 1 for x in dm]
    OFFSET = info["first"].weekday()
    week = [(d + OFFSET) // 7 for d in range(ND)]
    NW = max(week) + 1

    def t_toegestaan(d):
        if bez[wd[d]][1] > 0: return True
        return wd[d] <= 3 and T_PRIO.get(wd[d]) is not None

    def t_kost(d):
        p = T_PRIO.get(wd[d]) if wd[d] <= 3 else None
        return 0.0 if p is None else 2.0 * p

    def dag_hard_vrij(e, d):
        return dagpref[e][wd[d]] == "Nooit"

    def oplossen():
        c, lb, ub, integ = [], [], [], []

        def var(lo=0.0, hi=1.0, kost=0.0, geheel=1):
            c.append(kost); lb.append(lo); ub.append(hi); integ.append(geheel); return len(c) - 1
        X = [[[None] * 4 for _ in range(ND)] for _ in range(NE)]
        for e in range(NE):
            for d in range(ND):
                for s in range(4):
                    hi, kost = 1.0, 0.0
                    if vast_nacht[e]:
                        if s != 3 or vast.get((e, d)) != "N": hi = 0.0
                    elif flex[e]:
                        if vast.get((e, d)) != S[s]: hi = 0.0
                    else:
                        if dag_hard_vrij(e, d): hi = 0.0
                        if s < 3 and dienstpref[e][s] == "Nooit": hi = 0.0
                        if s == 3 and nachtpref[e] == "Nooit": hi = 0.0
                        kost += K_DAG.get(dagpref[e][wd[d]], 0.0)
                        kost += K_DIENST.get(dienstpref[e][s], 0.0) if s < 3 else K_NACHT.get(nachtpref[e], 150.0)
                    if s == 1:
                        if not t_toegestaan(d): hi = 0.0
                        kost += t_kost(d)
                    for (be, bwd, bweek, bs, afspraak) in bijzonder:
                        if be == e and bwd == wd[d] and (bweek is None or bweek == nde[d]) and bs == s:
                            if afspraak == "Nooit": hi = 0.0
                            kost += K_BIJZ.get(afspraak, 0.0)
                    if (e, d) in sterk: hi = 0.0
                    if (e, d) in gewoon: kost += W_WENS_GEWOON
                    lo = 1.0 if vast.get((e, d)) == S[s] else 0.0
                    if lo == 1.0: hi = 1.0
                    X[e][d][s] = var(lo, hi, kost)
        rows, cols, vals, lo_r, hi_r = [], [], [], [], []

        def con(terms, lo=-np.inf, hi=np.inf, const=0.0):
            r = len(lo_r)
            for v, k in terms.items():
                rows.append(r); cols.append(v); vals.append(k)
            lo_r.append(lo - const); hi_r.append(hi - const)

        def som(*delen):
            t, k = {}, 0.0
            for f, (tt, kk) in delen:
                for v, q in tt.items(): t[v] = t.get(v, 0.0) + f * q
                k += f * kk
            return t, k
        A = [e for e in range(NE) if MD >= 1 and naar_verg[e] and not vast_nacht[e] and not flex[e]]
        M, WM = {}, {}
        for e in A:
            m = var(0, 1, 0.0, 1); M[e] = m
            nz, nm = X[e][MD - 1][3], X[e][MD][3]
            con({m: 1.0, nz: 1.0}, hi=1.0); con({m: 1.0, nm: 1.0}, hi=1.0); con({m: 1.0, nz: 1.0, nm: 1.0}, lo=1.0)
            wm = var(0, 1, 0.0, 1); WM[e] = wm
            allx = {X[e][MD][s]: 1.0 for s in range(4)}
            t = dict(allx); t[wm] = -1.0; con(t, hi=0.0)
            con({wm: 1.0, m: -1.0}, lo=0.0)
            t = {k: -v for k, v in allx.items()}; t[wm] = 1.0; t[m] = -1.0; con(t, hi=0.0)

        def w(e, d):
            if d < 0: return {}, (1.0 if vorig[e][d + 5] else 0.0)
            if d == MD and e in WM: return {WM[e]: 1.0}, 0.0
            return {X[e][d][s]: 1.0 for s in range(4)}, 0.0

        def uren_dag(e, d):
            t = {X[e][d][s]: (U_NACHT if s == 3 else U_DAG) for s in range(4)}
            if d == MD and e in M:
                t[M[e]] = t.get(M[e], 0.0) + VERG_VRIJ
                for s, extra in ((0, VERG_V), (2, VERG_L), (1, VERG_T)):
                    t[X[e][d][s]] -= (VERG_VRIJ - extra)
            return t
        for e in range(NE):
            for d in range(ND): con({X[e][d][s]: 1.0 for s in range(4)}, hi=1.0)
        OPEN = {}
        for d in range(ND):
            for s in range(4):
                t = {X[e][d][s]: 1.0 for e in range(NE)}
                nodig = bez[wd[d]][s]
                if s == 1 and nodig == 0:
                    con(t, hi=MAX_T if t_toegestaan(d) else 0.0)
                elif nodig > 0:
                    OPEN[(d, s)] = var(0, nodig, W_OPEN, 1); t[OPEN[(d, s)]] = 1.0
                    con(t, nodig, nodig)
                else:
                    con(t, hi=0.0)
        for e in range(NE):
            if not vast_nacht[e] and not flex[e]:
                for d0 in range(-5, ND - MAX_RIJ):
                    t, k = som(*[(1, w(e, d0 + j)) for j in range(MAX_RIJ + 1)])
                    if t: con(t, hi=MAX_RIJ, const=k)
                if reeksregels[e]:
                    for d0 in range(-2, ND - 2):
                        t, k = som((1, w(e, d0)), (-1, w(e, d0 + 1)), (1, w(e, d0 + 2)))
                        if t: con(t, hi=1, const=k)
            for d in range(-1, ND - 1):
                if d < 0:
                    if vorig[e][4] == "L": con({X[e][0][0]: 1.0}, hi=0.0)
                    if vorig[e][4] == "N":
                        for s2 in (0, 1, 2): con({X[e][0][s2]: 1.0}, hi=0.0)
                    continue
                con({X[e][d][2]: 1.0, X[e][d + 1][0]: 1.0}, hi=1.0)
                for s2 in (0, 1, 2): con({X[e][d][3]: 1.0, X[e][d + 1][s2]: 1.0}, hi=1.0)
            if vast_nacht[e] or flex[e]: continue
            uren = {}
            for d in range(ND):
                for v, k in uren_dag(e, d).items(): uren[v] = uren.get(v, 0.0) + k
            onder, boven = var(0, 1e4, W_SALDO, 0), var(0, 1e4, W_SALDO, 0)
            t = dict(uren); t[onder] = 1.0; con(t, lo=te_werken[e] - SALDOGRENS)
            t = dict(uren); t[boven] = -1.0; con(t, hi=te_werken[e] + SALDOGRENS)
            if fte[e] > 0:
                t = {v: k / fte[e] for v, k in uren.items()}
                for breedte, kost in W_EERLIJK: t[var(0, breedte, kost, 0)] = 1.0
                con(t, lo=te_werken[e] / fte[e])
            for wk in range(NW):
                dagen = [d for d in range(ND) if week[d] == wk]
                doel = fte[e] * UREN_FTE * sum(1 for d in dagen if (e, d) not in vakantie) / 7
                tw = {}
                for d in dagen:
                    for v, k in uren_dag(e, d).items(): tw[v] = tw.get(v, 0.0) + k
                plus, min_ = var(0, 1e3, W_WEEK, 0), var(0, 1e3, W_WEEK, 0)
                t = dict(tw); t[plus] = -1.0; con(t, hi=doel + WEEK_MARGE)
                t = dict(tw); t[min_] = 1.0; con(t, lo=doel - WEEK_MARGE)
            for d in range(ND):
                st_ = var(0, 1, W_START, 0)
                t, k = som((1, w(e, d)), (-1, w(e, d - 1))); t[st_] = -1.0; con(t, hi=0, const=k)
            if liefst_max_rij[e]:
                mx = int(liefst_max_rij[e])
                for d0 in range(-5, ND - mx):
                    t, k = som(*[(1, w(e, d0 + j)) for j in range(mx + 1)])
                    if t: sl = var(0, 10, 40.0, 0); t[sl] = -1.0; con(t, hi=mx, const=k)
            if min_nacht_rij[e] and num(min_nacht_rij[e]) >= 2:
                for d in range(ND):
                    sl = var(0, 1, 200.0, 0); t = {X[e][d][3]: 1.0, sl: -1.0}
                    if d > 0: t[X[e][d - 1][3]] = -1.0
                    elif vorig[e][4] == "N": continue
                    if d < ND - 1: t[X[e][d + 1][3]] = -1.0
                    con(t, hi=0)
            if max_aandeel_t[e]:
                a = num(max_aandeel_t[e])
                sl = var(0, 40, 20.0, 0)
                t = {X[e][d][1]: 1.0 - a for d in range(ND)}
                for d in range(ND):
                    for s in (0, 2, 3): t[X[e][d][s]] = -a
                t[sl] = -1.0; con(t, hi=0)
            if min_dd[e]:
                mdd = num(min_dd[e])
                for a in range(0, NW, 2):
                    wk_a = [d for d in range(ND) if week[d] == a and wd[d] <= 4]
                    wk_b = [d for d in range(ND) if week[d] == a + 1 and wd[d] <= 4]
                    if len(wk_a) < 5 and len(wk_b) < 5: continue
                    z = var(0, 1, 0.0, 1); sl = var(0, 5, 20.0, 0)
                    t = {X[e][d][s]: 1.0 for d in wk_a for s in range(4)}; t[z] = -mdd; t[sl] = 1.0; con(t, lo=0)
                    t = {X[e][d][s]: 1.0 for d in wk_b for s in range(4)}; t[z] = mdd; t[sl] = 1.0; con(t, lo=mdd)
        kand = [e for e in range(NE) if not vast_nacht[e] and not flex[e] and not (dagpref[e][5] in ("Vrij", "Nooit") and dagpref[e][6] in ("Vrij", "Nooit"))]
        za = [d for d in range(ND - 1) if wd[d] == 5]
        we_dagen = [d for d in range(ND) if wd[d] >= 5]
        tot = sum(max(te_werken[e], 0) for e in kand) or 1.0
        totaal_we = sum(bez[wd[d]][s] for d in we_dagen for s in (0, 1, 2))
        for e in kand:
            for d in za:
                z = var(0, 1, 4.0, 0)
                a_, b_ = {X[e][d][s]: 1.0 for s in range(4)}, {X[e][d + 1][s]: 1.0 for s in range(4)}
                t = dict(a_)
                for v in b_: t[v] = t.get(v, 0) - 1.0
                t[z] = -1.0; con(t, hi=0)
                t = {v: -1.0 for v in a_}
                for v in b_: t[v] = t.get(v, 0) + 1.0
                t[z] = -1.0; con(t, hi=0)
            doel = totaal_we * max(te_werken[e], 0) / tot
            dv_ = var(0, 50, 3.0, 0)
            t = {X[e][d][s]: 1.0 for d in we_dagen for s in range(3)}; t[dv_] = -1.0; con(t, hi=doel)
            t = {X[e][d][s]: -1.0 for d in we_dagen for s in range(3)}; t[dv_] = -1.0; con(t, hi=-doel)
        for (be, bwd, bweek, bs, afspraak) in bijzonder:
            if afspraak == "Moet":
                for d in range(ND):
                    if wd[d] == bwd and (bweek is None or bweek == nde[d]):
                        con({X[be][d][bs]: 1.0}, lo=1.0)
        A_ = coo_matrix((vals, (rows, cols)), shape=(len(lo_r), len(c))).tocsr()
        res = milp(c=np.array(c), constraints=LinearConstraint(A_, np.array(lo_r), np.array(hi_r)),
                   integrality=np.array(integ), bounds=Bounds(np.array(lb), np.array(ub)),
                   options={"time_limit": REKENTIJD, "mip_rel_gap": 0.005})
        rooster, verg, open_ = None, {}, {}
        if res.x is not None:
            rooster = [[next((S[s] for s in range(4) if res.x[X[e][d][s]] > 0.5), "") for d in range(ND)] for e in range(NE)]
            verg = {e: int(round(res.x[M[e]])) for e in M}
            open_ = {k: int(round(res.x[v])) for k, v in OPEN.items() if res.x[v] > 0.5}
        return res, rooster, verg, open_

    def dstr(d): return f"{DAGNAMEN[wd[d]]} {dm[d]}-{info['m']}"
    rapport = []
    t0 = time.time()
    res, rooster, verg, open_ = oplossen()
    duur = time.time() - t0
    if rooster is None:
        if res.status != 2:
            rapport.append(["Let op", f"Binnen de rekentijd ({REKENTIJD:.0f} seconden) is nog geen rooster gevonden. Zet bij Instellingen de rekentijd hoger en probeer opnieuw."])
        else:
            rapport.append(["Let op", "Er is geen rooster mogelijk. Kijk naar de vaste diensten (bijvoorbeeld twee nachten op dezelfde dag) en de afspraken met 'Moet'."])
        return {"ok": False, "rapport": rapport, "duur": duur}
    if open_:
        aantal = sum(open_.values())
        rapport.append(["Open diensten", f"{aantal} dienst(en) blijven open, omdat het met alle regels, vakanties en sterke wensen echt niet rondkomt. Zoek een uitzendkracht, of vraag of iemand een sterke wens (geen vakantie) wil laten vallen."])
        for d in sorted({d for (d, s_) in open_}):
            welke = ", ".join(f"{n}x {S[s_]}" for (dd, s_), n in sorted(open_.items()) if dd == d)
            wens = [namen[e] for e in range(NE) if (e, d) in sterk and (e, d) not in vakantie]
            vak = [namen[e] for e in range(NE) if (e, d) in vakantie]
            rapport.append([f"Open op {dstr(d)}", f"{welke}. Sterke wens vrij die dag: {', '.join(wens) if wens else 'niemand'}. Met vakantie: {', '.join(vak) if vak else 'niemand'}."])
    status = {0: "beste rooster gevonden", 1: "tijd op: het beste rooster tot nu toe (langere rekentijd kan beter)"}.get(res.status, f"status {res.status}")
    rapport.append(["Programma", f"{status} (rekentijd {duur:.0f} seconden)"])
    open_n = [f"{namen[e]} op {dstr(d)}" for e in range(NE) if not vast_nacht[e] and not flex[e] for d in range(ND) if rooster[e][d] == "N"]
    rapport.append(["Nachten door het dagteam", "; ".join(open_n) if open_n else "geen"])
    for e in range(NE):
        if vast_nacht[e] or flex[e]: continue
        vrij = sum(1 for d in range(ND) if rooster[e][d] and dagpref[e][wd[d]] == "Vrij")
        ln = sum(1 for d in range(ND) if rooster[e][d] and dagpref[e][wd[d]] == "Liever niet")
        dn = sum(1 for d in range(ND) if rooster[e][d] in ("V", "T", "L") and dienstpref[e][S.index(rooster[e][d])] == "Liever niet")
        gw = sum(1 for (ee, d) in gewoon if ee == e and rooster[e][d])
        bij = [f"{DAGKORT[bwd]} {S[bs]}" for (be, bwd, bweek, bs, a) in bijzonder if be == e and a == "Graag"
               for d in range(ND) if wd[d] == bwd and (bweek is None or bweek == nde[d]) and rooster[e][d] != S[bs]]
        delen = []
        if vrij: delen.append(f"{vrij}x op een vaste vrije dag")
        if ln: delen.append(f"{ln}x op een liever-niet-dag")
        if dn: delen.append(f"{dn}x een dienst die liever niet")
        if gw: delen.append(f"{gw}x een gewone wens niet gehaald")
        if bij: delen.append("afspraak niet gehaald: " + ", ".join(bij))
        if delen: rapport.append([f"Voorkeur {namen[e]}", "; ".join(delen)])
    ids = P["ids"]
    return {
        "ok": True, "duur": duur, "status": int(res.status), "rapport": rapport,
        "rooster": {ids[e]: rooster[e] for e in range(NE)},
        "verg": {ids[e]: v for e, v in verg.items()},
        "open": [{"dag": d + 1, "dienst": S[s], "aantal": n} for (d, s), n in sorted(open_.items())],
    }
