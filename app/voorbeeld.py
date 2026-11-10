"""Een verzonnen team om mee te oefenen en te testen. Geen echte personen."""
from .model import empty_team, empty_month, new_employee

# naam, fte, vaste nachten, nachten, vergadering, rijtjesregels, dagen ma..zo, diensten V/T/L, extra
_TEAM = [
    ("Anna", .45, False, "Nooit", True, True, ["Vrij", "", "Vrij", "Vrij", "", "Vrij", "Vrij"], ("Graag", "", ""), {}),
    ("Bram", .625, True, "Graag", False, True, [""] * 7, ("", "", ""), {}),
    ("Chantal", 1, False, "Neutraal", True, True, ["", "", "", "", "", "Vrij", ""], ("", "", ""), {}),
    ("Dewi", .89, False, "Nooit", True, True, [""] * 7, ("Liever niet", "Liever niet", "Graag"), {"liefst_max_rij": 4}),
    ("Esra", .67, False, "Neutraal", False, True, ["Vrij", "", "", "", "Vrij", "", ""], ("", "Graag", ""), {"max_aandeel_t": .5}),
    ("Fatima", .89, False, "Graag", True, True, ["", "", "Vrij", "", "", "", ""], ("Liever niet", "Liever niet", "Graag"), {"min_nacht_rij": 2}),
    ("Gerda", .67, False, "Nooit", True, False, ["", "Nooit", "", "Nooit", "Nooit", "", ""], ("", "", ""), {"min_dd": 2}),
    ("Hanneke", .89, False, "Neutraal", True, True, ["", "", "Vrij", "", "", "", ""], ("", "", ""), {}),
    ("Ilse", 1, False, "Graag", True, True, [""] * 7, ("Graag", "Liever niet", "Liever niet"), {}),
    ("Jeroen", 1, True, "Graag", False, True, [""] * 7, ("", "", ""), {}),
    ("Karin", .89, False, "Neutraal", True, True, ["Vrij", "", "", "", "", "", ""], ("", "", ""), {}),
]


def voorbeeld_team():
    t = empty_team()
    for naam, fte, vn, nacht, verg, reeks, dagen, (v, tt, l), extra in _TEAM:
        e = new_employee(naam, fte)
        e.update(vast_nacht=vn, nachten=nacht, vergadering=verg, reeksregels=reeks, dagen=list(dagen), diensten={"V": v, "T": tt, "L": l}, **extra)
        t["employees"].append(e)
    ids = {e["naam"]: e["id"] for e in t["employees"]}
    t["afspraken"] = [
        {"emp": ids["Karin"], "weekdag": 2, "week": 2, "dienst": "V", "soort": "Graag"},
        {"emp": ids["Chantal"], "weekdag": 4, "week": 2, "dienst": "V", "soort": "Graag"},
        {"emp": ids["Hanneke"], "weekdag": 6, "week": None, "dienst": "V", "soort": "Liever niet"},
    ]
    return t


def voorbeeld_maand(team, key="2027-02"):
    """Februari 2027 met vaste nachten voor de twee nachtmensen, een paar vakanties en wensen."""
    m = empty_month(key)
    ids = {e["naam"]: e["id"] for e in team["employees"]}
    bram, jeroen = ids["Bram"], ids["Jeroen"]
    nachten_bram = [5, 6, 7, 8, 9, 19, 20, 21, 22, 23]
    nachten_jeroen = [1, 2, 3, 4, 10, 11, 12, 13, 14, 15, 16, 24, 25, 26, 27, 28]
    m["vast"][bram] = {str(d): "N" for d in nachten_bram}
    m["vast"][jeroen] = {str(d): "N" for d in nachten_jeroen}
    m["vorig"][jeroen] = ["", "", "N", "N", "N"]
    m["vorig"][ids["Chantal"]] = ["V", "V", "", "", "L"]
    m["vorig"][ids["Ilse"]] = ["", "V", "V", "V", ""]
    m["verlof"][ids["Chantal"]] = 36
    m["verlof"][ids["Gerda"]] = 31
    for d in range(1, 6): m["wensen"].append({"emp": ids["Chantal"], "dag": d, "soort": "sterk", "reden": "vakantie"})
    for d in range(20, 29): m["wensen"].append({"emp": ids["Gerda"], "dag": d, "soort": "sterk", "reden": "vakantie"})
    for d in (12, 13, 14): m["wensen"].append({"emp": ids["Ilse"], "dag": d, "soort": "sterk", "reden": "verjaardag"})
    m["wensen"].append({"emp": ids["Karin"], "dag": 11, "soort": "sterk", "reden": ""})
    m["wensen"].append({"emp": ids["Anna"], "dag": 17, "soort": "gewoon", "reden": ""})
    return m


# Het rooster dat de rekenkern voor deze voorbeeldmaand vindt (zodat een demo meteen iets laat zien). Punt = vrij.
VOORBEELD_ROOSTER = {
    "Anna": "V...V...V..V...V..V...V..V..", "Bram": "....NNNNN.........NNNNN.....", "Chantal": "......LTTVV...TLTV...VLTL...",
    "Dewi": "LLLL....LLL...LLLL...LLLL...", "Esra": ".TTT.....LT..L..VT..V..LT..L", "Fatima": "L...LLLL..LL.....LLLLL...LLL",
    "Gerda": "T....VVV.T...VV.L...........", "Hanneke": "VLLL...L...VVLL...TVLT..VV..", "Ilse": ".VVVV..VVVV...VVNN...VVV..VV",
    "Jeroen": "NNNN.....NNNNNNN.......NNNNN", "Karin": ".VVVT...L..TL..TVVV...TVVT..",
}
VOORBEELD_RAPPORT = [
    ["Programma", "beste rooster gevonden"], ["Nachten door het dagteam", "Ilse op wo 17-2; Ilse op do 18-2"],
    ["Voorkeur Anna", "1x op een vaste vrije dag"], ["Voorkeur Chantal", "afspraak niet gehaald: Vr V"],
    ["Voorkeur Hanneke", "1x op een vaste vrije dag"], ["Voorkeur Karin", "afspraak niet gehaald: Wo V"],
]


def voorbeeld_met_rooster(team, key="2027-02"):
    m = voorbeeld_maand(team, key)
    m["rooster"] = {e["id"]: [("" if x == "." else x) for x in VOORBEELD_ROOSTER[e["naam"]]] for e in team["employees"]}
    m["rapport"] = [list(r) for r in VOORBEELD_RAPPORT]
    return m
