"use strict";
/* Roostermaker: de hele pagina. Geen bouwstap nodig; alles praat met /api/. */

const S = ["V", "T", "L", "N"];
const DIENST = {
  V: { naam: "Vroeg", tijd: "07:30 tot 15:30" },
  T: { naam: "Tussen", tijd: "11:00 tot 19:00" },
  L: { naam: "Laat", tijd: "15:00 tot 23:00" },
  N: { naam: "Nacht", tijd: "22:45 tot 07:45" },
};
const DAGK = ["ma", "di", "wo", "do", "vr", "za", "zo"];
const DAGLANG = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"];
const MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"];
const STAPPEN = [
  { nr: 1, naam: "Vorige maand" },
  { nr: 2, naam: "Uren uit ORTEC" },
  { nr: 3, naam: "Vakantie en vrij" },
  { nr: 4, naam: "Vaste diensten" },
  { nr: 5, naam: "Rooster maken" },
  { nr: 6, naam: "Rooster bekijken" },
];

let team = null;      // teamgegevens
let cur = null;       // { maand, info, status } van de geopende maand
let controle = null;  // laatste controle van het rooster
const app = document.getElementById("app");
const pop = document.getElementById("pop");
const dlg = document.getElementById("dlg");

/* ---------- hulpjes ---------- */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const h = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const getal = (x, dec = 1) => (Math.round(Number(x || 0) * 10 ** dec) / 10 ** dec).toLocaleString("nl-NL");
const plus = (x) => (x > 0.05 ? "+" : "") + getal(x);
const medewerkers = () => team.employees.filter((e) => (e.naam || "").trim());
const isFlex = (e) => Number(e.fte || 0) === 0 && !e.vast_nacht;
const urenPerWeek = (e) => Number(e.fte || 0) * Number(team.settings.uren_fte || 36);
const maandLabel = (key) => { const [y, m] = key.split("-").map(Number); return `${MAANDEN[m - 1]} ${y}`; };

async function api(method, pad, body, formulier) {
  const opt = { method, headers: {}, credentials: "same-origin" };
  if (formulier) opt.body = formulier;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  let r;
  try { r = await fetch(pad, opt); } catch (e) { throw new Error("Geen verbinding met de server. Controleer de internetverbinding."); }
  if (r.status === 401 && pad !== "/api/login") { toonInlog(); throw new Error("Log eerst in."); }
  const type = r.headers.get("content-type") || "";
  const data = type.includes("json") ? await r.json() : await r.blob();
  if (!r.ok) throw new Error((data && data.detail) || `Er ging iets mis (${r.status}).`);
  return data;
}

function melding(tekst, fout = false) {
  const m = $("#melding");
  m.textContent = tekst; m.className = "melding" + (fout ? " fout" : ""); m.hidden = false;
  clearTimeout(melding.t); melding.t = setTimeout(() => (m.hidden = true), fout ? 6000 : 3000);
}

/* ---------- opslaan (automatisch) ---------- */
const wacht = {};
function zetOpslag(tekst, fout) { const o = $("#opslag"); o.textContent = tekst; o.classList.toggle("fout", !!fout); }
function plan(sleutel, fn, ms = 700) {
  zetOpslag("Wijziging wordt opgeslagen...");
  clearTimeout(wacht[sleutel]?.t);
  const item = { fn };
  item.t = setTimeout(() => voerUit(sleutel), ms);
  wacht[sleutel] = item;
}
async function voerUit(sleutel) {
  const item = wacht[sleutel]; if (!item) return;
  delete wacht[sleutel];
  try { await item.fn(); if (!Object.keys(wacht).length) zetOpslag("Alles is opgeslagen"); }
  catch (e) { zetOpslag("Niet opgeslagen: " + e.message, true); wacht[sleutel] = item; }
}
async function slaAllesOp() { for (const k of Object.keys(wacht)) { clearTimeout(wacht[k].t); await voerUit(k); } }
const bewaarTeam = () => plan("team", () => api("PUT", "/api/team", team));
const bewaarMaand = () => { const m = cur.maand; plan("maand:" + m.key, () => api("PUT", `/api/maanden/${m.key}`, m)); };
window.addEventListener("beforeunload", (e) => { if (Object.keys(wacht).length) { slaAllesOp(); e.preventDefault(); e.returnValue = ""; } });

/* ---------- dialogen ---------- */
function dialoog(html, { breed } = {}) {
  dlg.innerHTML = html; dlg.style.maxWidth = breed ? "min(860px, calc(100vw - 32px))" : "";
  dlg.showModal();
  return dlg;
}
function vraag(titel, tekst, ja = "Ja", gevaar = false) {
  return new Promise((klaar) => {
    dialoog(`<div class="binnen"><h2>${h(titel)}</h2><p>${tekst}</p></div>
      <div class="onder"><button class="knop tweede" value="nee">Annuleren</button><button class="knop ${gevaar ? "gevaar" : ""}" value="ja">${h(ja)}</button></div>`);
    $$("button", dlg).forEach((b) => (b.onclick = () => { dlg.close(); klaar(b.value === "ja"); }));
    dlg.onclose = () => klaar(false);
  });
}

/* ---------- keuzemenu bij een cel ---------- */
let popAnker = null;
function openPop(anker, titel, sub, opties, kies) {
  popAnker = anker;
  pop.innerHTML = `<div class="titel">${h(titel)}</div>${sub ? `<div class="sub">${sub}</div>` : ""}<div class="opties">${opties.map((o) =>
    `<button type="button" class="optie ${o.huidig ? "huidig" : ""}" data-v="${h(o.v)}"><span class="cel ${o.klasse || ""}">${h(o.letter ?? "")}</span><span>${h(o.naam)}${o.uitleg ? `<small>${h(o.uitleg)}</small>` : ""}</span></button>`).join("")}</div>`;
  pop.hidden = false;
  const r = anker.getBoundingClientRect();
  const w = pop.offsetWidth, hoog = pop.offsetHeight;
  let x = r.left + window.scrollX, y = r.bottom + window.scrollY + 6;
  if (x + w > window.scrollX + document.documentElement.clientWidth - 8) x = window.scrollX + document.documentElement.clientWidth - w - 8;
  if (r.bottom + hoog + 10 > window.innerHeight && r.top > hoog + 10) y = r.top + window.scrollY - hoog - 6;
  pop.style.left = Math.max(8, x) + "px"; pop.style.top = y + "px";
  pop.onclick = (e) => { const b = e.target.closest("[data-v]"); if (b) { sluitPop(); kies(b.dataset.v); } };
  (pop.querySelector(".huidig") || pop.querySelector(".optie")).focus();
}
function sluitPop(terug) { if (pop.hidden) return; pop.hidden = true; if (terug && popAnker) popAnker.focus(); popAnker = null; }
document.addEventListener("pointerdown", (e) => { if (!pop.hidden && !pop.contains(e.target) && e.target !== popAnker) sluitPop(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") sluitPop(true);
  if (!pop.hidden && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
    const b = $$(".optie", pop); const i = b.indexOf(document.activeElement);
    b[(i + (e.key === "ArrowDown" ? 1 : b.length - 1)) % b.length].focus(); e.preventDefault();
  }
});
function dienstOpties(huidig, metVrij = true) {
  const o = S.map((s) => ({ v: s, letter: s, klasse: s, naam: DIENST[s].naam, uitleg: DIENST[s].tijd, huidig: huidig === s }));
  if (metVrij) o.push({ v: "", letter: "", naam: "Vrij", uitleg: "geen dienst", huidig: !huidig });
  return o;
}

/* ---------- het raster (gebruikt bij vorige maand, wensen, vaste diensten en rooster) ---------- */
function rasterHTML({ dagen, cel, onder, idPrefix = "r" }) {
  const emps = medewerkers();
  let x = `<div class="rasterwrap"><table class="raster" id="${idPrefix}"><thead><tr><th class="wie">Medewerker</th>`;
  for (const d of dagen) x += `<th class="${d.we ? "we" : ""} ${d.verg ? "verg" : ""} ${d.vorig ? "vorig" : ""}" title="${h(d.titel || "")}">${h(d.kort)}<b>${h(d.nr)}</b></th>`;
  x += `</tr></thead><tbody>`;
  for (const e of emps) {
    x += `<tr><th class="wie" scope="row">${h(e.naam)}<small>${e.vast_nacht ? "vaste nachten" : isFlex(e) ? "invaller" : getal(urenPerWeek(e)) + " uur per week"}</small></th>`;
    for (const d of dagen) {
      const c = cel(e, d);
      x += `<td class="${d.we ? "we" : ""} ${d.vorig ? "vorig" : ""}"><button type="button" class="cel ${c.klasse || ""}" data-e="${e.id}" data-d="${d.d}" title="${h(c.titel || "")}" aria-label="${h(e.naam)}, ${h(d.titel || "")}: ${h(c.titel || c.tekst || "vrij")}" ${c.uit ? "disabled" : ""}>${c.html ?? h(c.tekst || "")}</button></td>`;
    }
    x += `</tr>`;
  }
  x += `</tbody>`;
  if (onder) x += `<tfoot>${onder}</tfoot>`;
  return x + `</table></div>`;
}
function maandDagen(metVorig = false) {
  const i = cur.info, out = [];
  if (metVorig) for (let j = 0; j < 5; j++) out.push({ d: "v" + j, nr: i.vorig_dagen[j], kort: DAGK[i.vorig_wd[j]], we: i.vorig_wd[j] >= 5, vorig: true, titel: `${DAGLANG[i.vorig_wd[j]]} ${i.vorig_dagen[j]} (vorige maand)` });
  for (let d = 0; d < i.nd; d++) out.push({ d, nr: d + 1, kort: DAGK[i.wd[d]], we: i.wd[d] >= 5, verg: d === i.md, titel: `${DAGLANG[i.wd[d]]} ${d + 1} ${MAANDEN[i.m - 1]}` + (d === i.md ? " (teamvergadering)" : "") });
  return out;
}
function wensVan(m, id, d) { return m.wensen.find((w) => w.emp === id && Number(w.dag) === d + 1); }
function wensSoort(w) { if (!w) return ""; if (w.soort === "sterk") return /vakantie/i.test(w.reden || "") ? "vak" : "sterk"; return "gewoon"; }
const WENS = {
  vak: { naam: "Vakantie", tekst: "vak", uitleg: "telt niet mee voor de weekuren" },
  sterk: { naam: "Vrij (moet)", tekst: "vrij", uitleg: "wordt nooit ingepland" },
  gewoon: { naam: "Liever vrij", tekst: "~", uitleg: "alleen inplannen als het niet anders kan" },
};
// cellen met de muis (ingedrukt) of een vinger beschilderen
function maakSchilderbaar(tabel, verf) {
  let bezig = false; const gedaan = new Set();
  const doe = (b) => { if (!b || b.disabled) return; const k = b.dataset.e + "|" + b.dataset.d; if (gedaan.has(k)) return; gedaan.add(k); verf(b); };
  tabel.addEventListener("pointerdown", (e) => { const b = e.target.closest(".cel"); if (!b) return; bezig = true; gedaan.clear(); doe(b); e.preventDefault(); });
  tabel.addEventListener("pointerover", (e) => { if (bezig) doe(e.target.closest(".cel")); });
  window.addEventListener("pointerup", () => (bezig = false));
  tabel.addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && e.target.closest(".cel")) { gedaan.clear(); doe(e.target.closest(".cel")); e.preventDefault(); } });
}
// pijltjestoetsen in het raster
function pijltjes(tabel) {
  tabel.addEventListener("keydown", (e) => {
    const b = e.target.closest(".cel"); if (!b || !pop.hidden) return;
    const td = b.parentElement, tr = td.parentElement, k = [...tr.children].indexOf(td);
    let doel = null;
    if (e.key === "ArrowRight") doel = td.nextElementSibling; else if (e.key === "ArrowLeft") doel = td.previousElementSibling;
    else if (e.key === "ArrowDown") doel = tr.nextElementSibling?.children[k]; else if (e.key === "ArrowUp") doel = tr.previousElementSibling?.children[k];
    else return;
    const nb = doel?.querySelector(".cel"); if (nb) { nb.focus(); e.preventDefault(); }
  });
}
function flits(id, d) {
  const sel = id ? `.cel[data-e="${id}"][data-d="${d}"]` : `.cel[data-d="${d}"]`;
  const cellen = $$(sel); if (!cellen.length) return;
  cellen[0].scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
  cellen.forEach((c) => { c.classList.remove("flits"); void c.offsetWidth; c.classList.add("flits"); });
  if (id) cellen[0].focus({ preventScroll: true });
}

/* ---------- navigatie ---------- */
window.addEventListener("hashchange", route);
async function route() {
  await slaAllesOp(); sluitPop();
  if (dlg.open) dlg.close();
  const p = (location.hash.replace(/^#\/?/, "") || "").split("/");
  $$(".hoofdmenu a").forEach((a) => a.classList.toggle("actief", a.dataset.nav === (p[0] === "maand" || !p[0] ? "maanden" : p[0])));
  app.classList.remove("breed");
  app.oninput = app.onchange = null;
  if (p[0] !== "maand") cur = null;
  try {
    if (!team) team = await api("GET", "/api/team");
    if (p[0] === "team") await paginaTeam();
    else if (p[0] === "instellingen") await paginaInstellingen();
    else if (p[0] === "maand" && p[1]) await paginaMaand(p[1], Number(p[2] || 1));
    else await paginaMaanden();
    app.focus({ preventScroll: true });
  } catch (e) {
    if (e.message !== "Log eerst in.") app.innerHTML = `<div class="balk fout"><p>${h(e.message)}</p><p><a href="#/">Terug naar het begin</a></p></div>`;
  }
}

/* ---------- inloggen ---------- */
function toonInlog(fout) {
  $("#kop").hidden = true; team = null;
  app.innerHTML = `<form class="inlog vlak" id="inlog"><h1>Roostermaker</h1>
    <p class="uitleg">Vul het wachtwoord van de roostermaker in.</p>
    <div class="veld"><label for="ww">Wachtwoord</label><input id="ww" type="password" autocomplete="current-password" required></div>
    <div class="balk fout" id="inlogfout" ${fout ? "" : "hidden"}><p>${h(fout || "")}</p></div>
    <button class="knop groot" type="submit">Inloggen</button></form>`;
  $("#ww").focus();
  $("#inlog").onsubmit = async (e) => {
    e.preventDefault();
    const knop = $("#inlog button"); knop.disabled = true;
    try { await api("POST", "/api/login", { wachtwoord: $("#ww").value }); start(); }
    catch (er) { $("#inlogfout").hidden = false; $("#inlogfout p").textContent = er.message; knop.disabled = false; $("#ww").select(); }
  };
}
$("#uitloggen").onclick = async () => { await slaAllesOp(); await api("POST", "/api/logout"); location.hash = "#/"; toonInlog(); };
async function start() {
  const me = await api("GET", "/api/me");
  if (!me.ingelogd) return toonInlog(me.wachtwoord_ingesteld ? "" : "Er is op de server nog geen wachtwoord ingesteld. Zet APP_PASSWORD in Railway.");
  $("#kop").hidden = false; zetOpslag("");
  $("#demo").hidden = !me.demo;
  route();
}

/* ---------- maanden ---------- */
async function paginaMaanden() {
  const lijst = await api("GET", "/api/maanden");
  const geenTeam = !medewerkers().length;
  const STATUS = { voorbereiding: "nog geen rooster", rooster: "rooster gemaakt", definitief: "definitief" };
  app.innerHTML = `<h1>Maanden</h1>
    <p class="uitleg">Kies een maand om verder te gaan, of begin aan een nieuwe maand.</p>
    <div class="knoppen"><button class="knop groot" id="nieuw" ${geenTeam ? "disabled" : ""}>Nieuwe maand maken</button></div>
    ${geenTeam ? `<div class="vlak leeg"><h2>Eerst het team</h2><p>Er staan nog geen medewerkers in de roostermaker. Vul eerst het team in, of lees het Excel-bestand van de roostermaker in.</p>
      <div class="knoppen" style="justify-content:center"><a class="knop" href="#/team">Team invullen</a><a class="knop tweede" href="#/instellingen">Excel-bestand inlezen</a></div></div>` : ""}
    ${lijst.length ? `<ul class="maanden">${lijst.map((m) => `<li><a href="#/maand/${m.key}/${m.status === "voorbereiding" ? 1 : 6}"><span class="naam">${h(m.label)}</span><span class="label ${m.status}">${STATUS[m.status]}</span><span class="pijl" aria-hidden="true">Openen</span></a></li>`).join("")}</ul>`
      : geenTeam ? "" : `<div class="vlak leeg"><p>Er zijn nog geen maanden. Klik op <b>Nieuwe maand maken</b> om te beginnen.</p></div>`}`;
  $("#nieuw").onclick = () => {
    const nu = new Date();
    let voorstel = `${nu.getFullYear()}-${String(nu.getMonth() + 2 > 12 ? 1 : nu.getMonth() + 2).padStart(2, "0")}`;
    if (nu.getMonth() === 11) voorstel = `${nu.getFullYear() + 1}-01`;
    if (lijst.length) { const [y, m] = lijst[0].key.split("-").map(Number); voorstel = m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, "0")}`; }
    dialoog(`<form method="dialog" id="nm"><div class="binnen"><h2>Nieuwe maand</h2>
      <div class="veld"><label for="mk">Welke maand?</label><input type="month" id="mk" value="${voorstel}" required></div>
      <p class="uitleg">Als de vorige maand al in de roostermaker staat, vult het programma de laatste dagen en het saldo alvast voor je in.</p></div>
      <div class="onder"><button class="knop tweede" value="nee" type="button" id="nmw">Annuleren</button><button class="knop" type="submit">Maand maken</button></div></form>`);
    $("#nmw").onclick = () => dlg.close();
    $("#nm").onsubmit = async (e) => {
      e.preventDefault();
      try { const r = await api("POST", "/api/maanden", { key: $("#mk").value }); dlg.close(); location.hash = `#/maand/${r.key}/1`; }
      catch (er) { melding(er.message, true); }
    };
  };
}

/* ---------- één maand ---------- */
async function paginaMaand(key, stap) {
  if (!cur || cur.maand.key !== key) { cur = await api("GET", `/api/maanden/${key}`); controle = null; }
  const m = cur.maand;
  if (stap === 6 && !m.rooster) stap = 5;
  const klaar = {
    1: Object.values(m.vorig || {}).some((r) => r.some(Boolean)),
    2: Object.keys(m.saldo || {}).length > 0 || Object.keys(m.verlof || {}).length > 0,
    3: m.wensen.length > 0,
    4: Object.values(m.vast || {}).some((r) => Object.keys(r).length),
    5: !!m.rooster, 6: !!m.definitief,
  };
  app.classList.toggle("breed", true);
  app.innerHTML = `<div style="max-width:1400px;margin:0 auto">
    <h1 class="maandtitel">${h(cur.info.label)}</h1>
    <ol class="stappen">${STAPPEN.map((s) => `<li><a href="#/maand/${key}/${s.nr}" class="${s.nr === stap ? "nu" : ""} ${klaar[s.nr] ? "klaar" : ""}" ${s.nr === stap ? 'aria-current="step"' : ""}>${h(s.naam)}</a></li>`).join("")}</ol>
    <section id="stap"></section></div>`;
  const vak = $("#stap");
  ({ 1: stapVorig, 2: stapUren, 3: stapWensen, 4: stapVast, 5: stapMaken, 6: stapRooster })[stap](vak, m);
}
function stapKnoppen(stap, volgendeTekst) {
  const key = cur.maand.key;
  return `<div class="knoppen">${stap > 1 ? `<a class="knop tweede" href="#/maand/${key}/${stap - 1}">Vorige stap</a>` : `<a class="knop tweede" href="#/">Terug naar maanden</a>`}
    ${stap < 6 ? `<a class="knop groot rechts" href="#/maand/${key}/${stap + 1}">${h(volgendeTekst || "Volgende stap")}</a>` : ""}</div>`;
}

function stapVorig(vak, m) {
  const info = cur.info;
  vak.innerHTML = `<h2>Wat is er gewerkt aan het eind van ${MAANDEN[(info.m + 10) % 12]}?</h2>
    <p class="uitleg">Vul per persoon de laatste 5 dagen van de vorige maand in, zoals ze echt gewerkt zijn (kijk in ORTEC). Het programma heeft dit nodig voor de regels over rijtjes en nachten. Klik op een vakje om de dienst te kiezen.</p>
    ${m.vorig_bron === "rooster" ? `<div class="balk let"><p>Dit is alvast ingevuld uit het rooster van vorige maand. Is er geruild of was iemand ziek? Pas het dan hier aan.</p></div>` : ""}
    <div id="rw"></div>${stapKnoppen(1)}`;
  const teken = () => {
    $("#rw").innerHTML = rasterHTML({
      idPrefix: "vorig",
      dagen: maandDagen(true).filter((d) => d.vorig),
      cel: (e, d) => { const x = (m.vorig[e.id] || [])[Number(d.d.slice(1))] || ""; return { klasse: x, tekst: x, titel: x ? DIENST[x].naam : "vrij" }; },
    });
    const t = $("#vorig"); pijltjes(t);
    t.onclick = (ev) => {
      const b = ev.target.closest(".cel"); if (!b) return;
      const e = team.employees.find((x) => x.id === b.dataset.e), j = Number(b.dataset.d.slice(1));
      const hier = (m.vorig[e.id] || ["", "", "", "", ""])[j];
      openPop(b, `${e.naam}, ${b.closest("table").tHead.rows[0].cells[j + 1].title}`, "", dienstOpties(hier), (v) => {
        m.vorig[e.id] = m.vorig[e.id] || ["", "", "", "", ""]; m.vorig[e.id][j] = v; bewaarMaand(); teken();
        $(`#vorig .cel[data-e="${e.id}"][data-d="v${j}"]`)?.focus();
      });
    };
    t.onkeydown = (ev) => typLetter(ev, (e, j, v) => { m.vorig[e.id] = m.vorig[e.id] || ["", "", "", "", ""]; m.vorig[e.id][Number(j.slice(1))] = v; bewaarMaand(); teken(); $(`#vorig .cel[data-e="${e.id}"][data-d="${j}"]`)?.focus(); });
  };
  teken();
}
// V, T, L, N of Delete typen in een vakje
function typLetter(ev, zet) {
  const b = ev.target.closest(".cel"); if (!b || b.disabled) return;
  const k = ev.key.toUpperCase();
  let v = null;
  if (S.includes(k)) v = k; else if (["DELETE", "BACKSPACE", "0", "-"].includes(k)) v = "";
  if (v === null || ev.ctrlKey || ev.metaKey) return;
  ev.preventDefault();
  zet(team.employees.find((x) => x.id === b.dataset.e), b.dataset.d, v);
}

function stapUren(vak, m) {
  const info = cur.info, st = team.settings;
  const rij = (e) => {
    const contract = Number(e.fte || 0) * Number(st.uren_fte) * info.nd / 7;
    return `<tr><th scope="row">${h(e.naam)}</th>
      <td><input type="number" step="0.25" inputmode="decimal" data-e="${e.id}" data-f="saldo" value="${m.saldo[e.id] ?? ""}" placeholder="0" aria-label="Saldo ${h(e.naam)}"></td>
      <td><input type="number" step="0.25" min="0" inputmode="decimal" data-e="${e.id}" data-f="verlof" value="${m.verlof[e.id] ?? ""}" placeholder="0" aria-label="Verlofuren ${h(e.naam)}"></td>
      <td class="getal">${isFlex(e) ? "invaller" : getal(contract)}</td></tr>`;
  };
  vak.innerHTML = `<h2>Saldo en verlof uit ORTEC</h2>
    <p class="uitleg">ORTEC houdt de uren bij. Neem per persoon twee getallen over: het saldo aan het eind van vorige maand (te veel gewerkt is plus, te weinig is min) en de verlofuren in ${MAANDEN[info.m - 1]}. Leeg betekent 0.</p>
    ${m.saldo_bron === "berekend" ? `<div class="balk let"><p>Het saldo is alvast ingevuld met wat de roostermaker heeft uitgerekend voor vorige maand. ORTEC weet het precies (ziekte, ruilen). Vergelijk en pas aan waar het verschilt.</p></div>` : ""}
    <div class="tabelwrap"><table class="tabel"><thead><tr><th>Medewerker</th><th>Saldo eind vorige maand (uren)</th><th>Verlofuren deze maand</th><th class="getal">Contracturen deze maand</th></tr></thead>
    <tbody>${medewerkers().map(rij).join("")}</tbody></table></div>${stapKnoppen(2)}`;
  vak.oninput = (ev) => {
    const i = ev.target.closest("input[data-e]"); if (!i) return;
    const v = i.value.trim().replace(",", ".");
    if (v === "") delete m[i.dataset.f][i.dataset.e]; else if (!isNaN(Number(v))) m[i.dataset.f][i.dataset.e] = Number(v);
    bewaarMaand();
  };
}

function penselenHTML(lijst, actief) {
  return `<div class="penselen" role="toolbar" aria-label="Wat wil je neerzetten?">${lijst.map((p) =>
    `<button type="button" class="penseel" data-p="${p.v}" aria-pressed="${p.v === actief}"><span class="cel ${p.klasse || ""}">${h(p.letter || "")}</span>${h(p.naam)}</button>`).join("")}</div>`;
}
function stapWensen(vak, m) {
  let pen = stapWensen.pen || "vak";
  vak.innerHTML = `<h2>Vakanties en vrije dagen</h2>
    <p class="uitleg">Kies hieronder wat je wilt neerzetten en klik dan op de dagen. Houd de muis ingedrukt en sleep over een week om die in één keer te vullen.</p>
    <div id="pz"></div><div id="rw"></div>
    <div class="legenda"><span><span class="cel vak">vak</span>vakantie: nooit inplannen</span><span><span class="cel sterk">vrij</span>vrij: nooit inplannen</span><span><span class="cel gewoon">~</span>liever vrij: alleen als het echt niet anders kan</span><span><span class="cel N">N</span>vaste dienst (stap 4)</span></div>
    ${stapKnoppen(3)}`;
  const PEN = [
    { v: "vak", klasse: "vak", letter: "vak", naam: "Vakantie" },
    { v: "sterk", klasse: "sterk", letter: "vrij", naam: "Vrij (moet)" },
    { v: "gewoon", klasse: "gewoon", letter: "~", naam: "Liever vrij" },
    { v: "", letter: "", naam: "Wissen" },
  ];
  const tekenPen = () => { $("#pz").innerHTML = penselenHTML(PEN, pen); $$(".penseel").forEach((b) => (b.onclick = () => { pen = stapWensen.pen = b.dataset.p; tekenPen(); })); };
  const celInfo = (e, d) => {
    const w = wensSoort(wensVan(m, e.id, d.d)), vast = (m.vast[e.id] || {})[d.d + 1];
    if (w) return { klasse: w, tekst: WENS[w].tekst, titel: WENS[w].naam + (wensVan(m, e.id, d.d).reden && w !== "vak" ? ": " + wensVan(m, e.id, d.d).reden : "") };
    if (vast) return { klasse: vast + " vast", tekst: vast, titel: "vaste dienst " + DIENST[vast].naam };
    return { tekst: "", titel: "geen wens" };
  };
  const teken = () => {
    $("#rw").innerHTML = rasterHTML({ idPrefix: "wens", dagen: maandDagen(), cel: celInfo });
    const t = $("#wens"); pijltjes(t);
    maakSchilderbaar(t, (b) => {
      const id = b.dataset.e, d = Number(b.dataset.d);
      m.wensen = m.wensen.filter((w) => !(w.emp === id && Number(w.dag) === d + 1));
      if (pen) {
        m.wensen.push({ emp: id, dag: d + 1, soort: pen === "gewoon" ? "gewoon" : "sterk", reden: pen === "vak" ? "vakantie" : "" });
        if ((m.vast[id] || {})[d + 1]) { delete m.vast[id][d + 1]; melding("De vaste dienst op die dag is weggehaald."); }
      }
      const e = team.employees.find((x) => x.id === id), c = celInfo(e, { d });
      b.className = "cel " + (c.klasse || ""); b.textContent = c.tekst; b.title = c.titel;
      bewaarMaand();
    });
  };
  tekenPen(); teken();
}

function stapVast(vak, m) {
  let pen = stapVast.pen || "N";
  const nachtmensen = medewerkers().filter((e) => e.vast_nacht).map((e) => e.naam);
  const invallers = medewerkers().filter(isFlex).map((e) => e.naam);
  vak.innerHTML = `<h2>Diensten die al vastliggen</h2>
    <p class="uitleg">Zet hier de nachten van ${nachtmensen.length ? h(nachtmensen.join(" en ")) : "de vaste nachtdiensten"}${invallers.length ? `, de diensten van ${h(invallers.join(", "))}` : ""} en elke dienst die al is afgesproken. Het programma verandert deze diensten niet en plant de rest eromheen. Open nachten hoef je niet te vullen: die verdeelt het programma over het dagteam.</p>
    <div id="pz"></div><div id="rw"></div>
    <div class="legenda"><span><span class="cel vak">vak</span>vakantie</span><span><span class="cel sterk">vrij</span>vrij</span><span><span class="cel gewoon">~</span>liever vrij</span><span>Een punt rechtsboven betekent: vaste dienst</span></div>
    ${stapKnoppen(4)}`;
  const PEN = [...S.map((s) => ({ v: s, klasse: s, letter: s, naam: DIENST[s].naam })), { v: "", letter: "", naam: "Wissen" }];
  const tekenPen = () => { $("#pz").innerHTML = penselenHTML(PEN, pen); $$(".penseel").forEach((b) => (b.onclick = () => { pen = stapVast.pen = b.dataset.p; tekenPen(); })); };
  const celInfo = (e, d) => {
    const vast = (m.vast[e.id] || {})[d.d + 1], w = wensSoort(wensVan(m, e.id, d.d));
    if (vast) return { klasse: vast + " vast", tekst: vast, titel: "vaste dienst " + DIENST[vast].naam };
    if (w) return { klasse: w, tekst: WENS[w].tekst, titel: WENS[w].naam };
    return { tekst: "", titel: "nog niet ingevuld" };
  };
  const teken = () => {
    $("#rw").innerHTML = rasterHTML({ idPrefix: "vast", dagen: maandDagen(), cel: celInfo });
    const t = $("#vast"); pijltjes(t);
    maakSchilderbaar(t, (b) => {
      const id = b.dataset.e, d = Number(b.dataset.d), e = team.employees.find((x) => x.id === id);
      const w = wensVan(m, id, d);
      if (pen && w && w.soort === "sterk") { melding(`${e.naam} is op ${d + 1} ${MAANDEN[cur.info.m - 1]} vrij of met vakantie. Haal dat eerst weg bij stap 3.`, true); return; }
      m.vast[id] = m.vast[id] || {};
      if (pen) m.vast[id][d + 1] = pen; else delete m.vast[id][d + 1];
      const c = celInfo(e, { d });
      b.className = "cel " + (c.klasse || ""); b.textContent = c.tekst; b.title = c.titel;
      bewaarMaand();
    });
  };
  tekenPen(); teken();
}

function stapMaken(vak, m) {
  const emps = medewerkers(), info = cur.info;
  const vasteNachten = Object.values(m.vast || {}).reduce((a, r) => a + Object.values(r).filter((x) => x === "N").length, 0);
  const nachtenNodig = Array.from({ length: info.nd }, (_, d) => Number(team.bezetting[info.wd[d]][3])).reduce((a, b) => a + b, 0);
  const geenSaldo = emps.every((e) => !m.saldo[e.id]);
  const geenVorig = !Object.values(m.vorig || {}).some((r) => r.some(Boolean));
  const tips = [];
  if (geenVorig) tips.push(`Bij <a href="#/maand/${m.key}/1">stap 1</a> staat niets ingevuld over de vorige maand. Klopt dat?`);
  if (geenSaldo) tips.push(`Alle saldi staan op 0 (<a href="#/maand/${m.key}/2">stap 2</a>). Klopt dat met ORTEC?`);
  if (!m.wensen.length) tips.push(`Er zijn geen vakanties of vrije dagen ingevuld (<a href="#/maand/${m.key}/3">stap 3</a>).`);
  vak.innerHTML = `<h2>Rooster maken</h2>
    <p class="uitleg">Het programma zoekt nu het rooster dat alle harde regels haalt en zo veel mogelijk voorkeuren. Dat duurt meestal 10 tot 60 seconden. Je kunt het rooster daarna nog met de hand aanpassen.</p>
    <div class="vlak"><ul>
      <li>${emps.length} medewerkers</li>
      <li>${m.wensen.filter((w) => wensSoort(w) === "vak").length} vakantiedagen, ${m.wensen.filter((w) => wensSoort(w) === "sterk").length} vrije dagen en ${m.wensen.filter((w) => w.soort === "gewoon").length} liever-vrij-dagen</li>
      <li>${vasteNachten} van de ${nachtenNodig} nachten liggen vast; de rest gaat naar het dagteam</li>
      ${info.md >= 0 ? `<li>Teamvergadering op maandag ${info.md + 1} ${MAANDEN[info.m - 1]}</li>` : ""}
    </ul></div>
    ${tips.length ? `<div class="balk let">${tips.map((t) => `<p>${t}</p>`).join("")}</div>` : ""}
    ${m.rooster ? `<div class="balk fout"><p><b>Er is al een rooster voor deze maand.</b> Opnieuw maken vervangt het, ook alles wat je met de hand hebt aangepast.</p></div>` : ""}
    <div class="knoppen"><a class="knop tweede" href="#/maand/${m.key}/4">Vorige stap</a>
      <button class="knop groot rechts" id="maak">${m.rooster ? "Rooster opnieuw maken" : "Maak het rooster"}</button>
      ${m.rooster ? `<a class="knop tweede" href="#/maand/${m.key}/6">Bestaand rooster bekijken</a>` : ""}</div>`;
  $("#maak").onclick = async () => {
    if (m.rooster && !(await vraag("Rooster opnieuw maken?", "Het huidige rooster en je aanpassingen worden vervangen door een nieuw rooster.", "Opnieuw maken", true))) return;
    await slaAllesOp();
    const w = document.createElement("div");
    w.className = "wachten"; w.setAttribute("role", "alert");
    w.innerHTML = `<div class="doos"><div class="blokjes" aria-hidden="true"><i></i><i></i><i></i><i></i></div><h2>Het rooster wordt gemaakt</h2><p class="tijd" id="tel">0</p><p class="uitleg">seconden. Sluit deze pagina niet. Dit duurt maximaal ${Math.round(team.settings.rekentijd || 60) + 15} seconden.</p></div>`;
    document.body.appendChild(w);
    const t0 = Date.now(), tik = setInterval(() => { const t = $("#tel"); if (t) t.textContent = Math.round((Date.now() - t0) / 1000); }, 500);
    try {
      const r = await api("POST", `/api/maanden/${m.key}/maken`);
      if (!r.ok) { dialoog(`<div class="binnen"><h2>Geen rooster gevonden</h2>${r.rapport.map((x) => `<p>${h(x[1])}</p>`).join("")}</div><div class="onder"><button class="knop" id="dicht">Sluiten</button></div>`); $("#dicht").onclick = () => dlg.close(); return; }
      cur.maand = r.maand; cur.status = "rooster"; controle = null;
      const open = r.maand.open.reduce((a, o) => a + o.aantal, 0);
      melding(open ? `Rooster gemaakt. ${open} dienst(en) blijven open.` : "Rooster gemaakt.");
      location.hash = `#/maand/${m.key}/6`;
    } catch (e) { melding(e.message, true); }
    finally { clearInterval(tik); w.remove(); }
  };
}

function stapRooster(vak, m) {
  const info = cur.info, st = team.settings;
  const op = (id) => m.rooster[id] || (m.rooster[id] = Array(info.nd).fill(""));
  const bijVerg = (e) => info.md >= 0 && e.vergadering && !e.vast_nacht && !isFlex(e) && op(e.id)[info.md] !== "N" && op(e.id)[info.md - 1] !== "N";
  const foutCellen = () => new Set((controle?.fouten || []).filter((f) => f.emp && f.dag).map((f) => f.emp + "|" + (f.dag - 1)));
  vak.innerHTML = `
    ${m.definitief ? `<div class="balk goed niet-printen"><p><b>Dit rooster is definitief.</b> Ruilen en ziekte verwerk je vanaf nu in ORTEC.</p></div>` : ""}
    <div class="knoppen niet-printen">
      <a class="knop" href="/api/maanden/${m.key}/excel" download>Download Excel (voor ORTEC)</a>
      <button class="knop tweede" id="print">Afdrukken</button>
      <button class="knop tweede" id="def">${m.definitief ? "Toch nog wijzigen" : "Rooster is definitief"}</button>
      <a class="knop stil rechts" href="#/maand/${m.key}/5">Opnieuw maken</a></div>
    <p class="uitleg niet-printen">${m.definitief ? "" : "Klik op een vakje om een dienst te veranderen, of typ V, T, L, N (of Delete voor vrij). De controle hieronder rekent meteen mee."}</p>
    <div class="alleen-print"><h2 style="text-transform:capitalize">Rooster ${h(info.label)}</h2></div>
    <div id="rw"></div>
    <div class="legenda">${S.map((s) => `<span><span class="cel ${s}">${s}</span>${DIENST[s].naam} ${DIENST[s].tijd}</span>`).join("")}
      <span><span class="cel vak">vak</span>vakantie</span><span><span class="cel sterk">vrij</span>vrij gevraagd</span>
      ${info.md >= 0 ? `<span><span class="cel">vg</span>teamvergadering 13:00 tot 17:00 op ${DAGLANG[info.wd[info.md]]} ${info.md + 1}</span>` : ""}</div>
    <div class="controle niet-printen"><div class="vlak" id="ctrl"><h2 style="margin-top:0">Controle</h2><p class="uitleg">Bezig met controleren...</p></div>
      <div class="vlak" id="rap"></div></div>
    <div class="vlak niet-printen" id="uren"></div>
    ${stapKnoppen(6)}`;
  const celInfo = (e, d) => {
    const x = op(e.id)[d.d] || "", w = wensSoort(wensVan(m, e.id, d.d)), vast = (m.vast[e.id] || {})[d.d + 1];
    let klasse = x, tekst = x, titel = x ? `${DIENST[x].naam} ${DIENST[x].tijd}` : "vrij";
    if (!x && w && w !== "gewoon") { klasse = w; tekst = WENS[w].tekst; titel = WENS[w].naam; }
    if (x && w && w !== "gewoon") { klasse += " wens-op-dienst"; titel += `, maar ${WENS[w].naam.toLowerCase()} gevraagd`; }
    if (vast && vast === x) { klasse += " vast"; titel += " (vaste dienst)"; }
    let html = h(tekst);
    if (d.d === info.md && bijVerg(e)) { if (x) html += `<span class="vg">vg</span>`; else { html = "vg"; titel = "alleen de teamvergadering"; } titel += ", bij de teamvergadering"; }
    if (fc.has(e.id + "|" + d.d)) klasse += " fout";
    return { klasse, html, titel, uit: m.definitief };
  };
  let fc = new Set();
  const somRij = () => {
    let x = `<tr class="som"><th class="wie">Bezetting</th>`;
    for (let d = 0; d < info.nd; d++) {
      const nodig = team.bezetting[info.wd[d]], tel = {};
      S.forEach((s) => (tel[s] = medewerkers().filter((e) => op(e.id)[d] === s).length));
      const delen = [];
      S.forEach((s, j) => {
        const n = Number(nodig[j]);
        if (s === "T" && n === 0) { if (tel.T) delen.push(`<span class="bez-meer" title="extra tussendienst">+T</span>`); return; }
        if (tel[s] < n) delen.push(`<span class="bez-fout" title="${n - tel[s]}x ${DIENST[s].naam} open">${s}${tel[s] - n}</span>`);
        else if (tel[s] > n) delen.push(`<span class="bez-meer" title="${tel[s] - n}x ${DIENST[s].naam} te veel">${s}+${tel[s] - n}</span>`);
      });
      x += `<td data-d="${d}">${delen.length ? delen.join("<br>") : `<span class="bez-ok" title="bezetting klopt">✓</span>`}</td>`;
    }
    return x + `</tr>`;
  };
  const teken = () => {
    $("#rw").innerHTML = rasterHTML({ idPrefix: "rooster", dagen: maandDagen(), cel: celInfo, onder: somRij() });
    pijltjes($("#rooster"));
  };
  const zet = (e, d, v) => {
    op(e.id)[d] = v; m.verg = {};
    bewaarMaand(); teken(); controleer();
    $(`#rooster .cel[data-e="${e.id}"][data-d="${d}"]`)?.focus();
  };
  const tekenControle = () => {
    const c = controle;
    if (!c) return;
    fc = foutCellen();
    $("#ctrl").innerHTML = `<h2 style="margin-top:0">Controle</h2>
      ${c.totaal === 0 ? `<div class="balk goed"><p><b>Alle harde regels kloppen.</b></p></div>` : `<div class="balk fout"><p><b>${c.totaal} ${c.totaal === 1 ? "punt" : "punten"} om naar te kijken.</b> Klik op een punt om het in het rooster te zien.</p></div>`}
      <ul class="regels">${c.regels.map((r) => `<li class="${r.fouten ? "nok" : "ok"}"><div class="kopje"><span class="teken">${r.fouten ? r.fouten : "✓"}</span>${h(r.tekst)}</div>
        ${r.fouten ? `<ul class="lijst">${c.fouten.filter((f) => f.regel === r.nr).map((f) => `<li><button type="button" data-e="${f.emp || ""}" data-d="${f.dag ? f.dag - 1 : ""}">${h(f.tekst)}</button></li>`).join("")}</ul>` : ""}</li>`).join("")}</ul>`;
    $$("#ctrl .lijst button").forEach((b) => (b.onclick = () => { if (b.dataset.d !== "") flits(b.dataset.e, b.dataset.d); }));
    const grens = Number(st.saldogrens);
    $("#uren").innerHTML = `<h2 style="margin-top:0">Uren</h2>
      <p class="uitleg">Eindsaldo = beginsaldo + gewerkte uren + verlof min contracturen. Rood: buiten de grens van ${getal(grens)} uur. Geel bij een week: meer dan 4 uur naast de weekuren (vakantie telt niet mee).</p>
      <div style="overflow-x:auto"><table class="tabel"><thead><tr><th>Medewerker</th><th class="getal">Contract</th><th class="getal">Verlof</th><th class="getal">Beginsaldo</th><th class="getal">Gewerkt</th><th class="getal">Eindsaldo</th>
      ${Array.from({ length: c.weken }, (_, i) => `<th class="getal">Week ${i + 1}</th>`).join("")}<th class="getal">V/T/L/N</th></tr></thead>
      <tbody>${c.personen.filter((p) => !p.flex).map((p) => `<tr><th scope="row">${h(p.naam)}</th><td class="getal">${getal(p.contract)}</td><td class="getal">${getal(p.verlof)}</td><td class="getal">${plus(p.beginsaldo)}</td><td class="getal">${getal(p.gewerkt)}</td>
        <td class="getal ${Math.abs(p.eindsaldo) > grens + 0.001 ? "buiten" : ""}">${plus(p.eindsaldo)}</td>
        ${p.weken.map((w) => `<td class="getal ${!p.vast_nacht && Math.abs(w) > 4 ? "ernaast" : ""}">${plus(w)}</td>`).join("")}<td class="getal">${S.map((s) => p.diensten[s]).join("/")}</td></tr>`).join("")}</tbody></table></div>`;
    teken();
  };
  const controleer = () => {
    clearTimeout(controleer.t);
    controleer.t = setTimeout(async () => {
      try { controle = await api("POST", `/api/maanden/${m.key}/controle`, { maand: m }); tekenControle(); }
      catch (e) { $("#ctrl").innerHTML = `<div class="balk fout"><p>${h(e.message)}</p></div>`; }
    }, 250);
  };
  $("#rap").innerHTML = `<h2 style="margin-top:0">Wat het programma meldde</h2>${(m.rapport || []).length ? `<dl class="rapport">${m.rapport.map((r) => `<dt>${h(r[0])}</dt><dd>${h(r[1])}</dd>`).join("")}</dl>` : `<p class="uitleg">Geen meldingen.</p>`}<p class="uitleg">Dit gaat over het rooster zoals het gemaakt is, nog zonder jouw aanpassingen.</p>`;
  teken();
  if (controle) tekenControle(); else controleer();
  $("#print").onclick = () => window.print();
  $("#def").onclick = async () => {
    if (!m.definitief && !(await vraag("Rooster definitief maken?", "Daarna kun je het hier niet meer per ongeluk wijzigen. Ruilen en ziekte doe je dan in ORTEC.", "Definitief maken"))) return;
    m.definitief = !m.definitief; bewaarMaand(); stapRooster(vak, m);
  };
  const tabelKlik = (ev) => {
    const b = ev.target.closest(".cel"); if (!b || b.disabled || m.definitief) return;
    const e = team.employees.find((x) => x.id === b.dataset.e), d = Number(b.dataset.d);
    const w = wensVan(m, e.id, d), ws = wensSoort(w);
    const sub = [ws ? `${WENS[ws].naam} gevraagd${w.reden && ws !== "vak" ? " (" + h(w.reden) + ")" : ""}` : "", e.dagen?.[info.wd[d]] ? `${DAGLANG[info.wd[d]]}: ${h(e.dagen[info.wd[d]].toLowerCase())}` : ""].filter(Boolean).join("<br>");
    openPop(b, `${e.naam}, ${DAGLANG[info.wd[d]]} ${d + 1}`, sub, dienstOpties(op(e.id)[d]), (v) => zet(e, d, v));
  };
  vak.onclick = (ev) => { if (ev.target.closest("#rooster")) tabelKlik(ev); };
  vak.onkeydown = (ev) => { if (ev.target.closest("#rooster") && !m.definitief) typLetter(ev, (e, d, v) => zet(e, Number(d), v)); };
}

/* ---------- team ---------- */
const DAGKEUZE = [["", "Kan"], ["Liever niet", "Liever niet"], ["Vrij", "Vaste vrije dag"], ["Nooit", "Nooit"]];
const DIENSTKEUZE = [["Graag", "Graag"], ["", "Maakt niet uit"], ["Liever niet", "Liever niet"], ["Nooit", "Nooit"]];
const NACHTKEUZE = [["Graag", "Graag"], ["Neutraal", "Als het moet"], ["Nooit", "Nooit"]];
const AFSPRAAKKEUZE = ["Graag", "Liever niet", "Nooit", "Moet"];

function samenvatting(e) {
  if (e.vast_nacht) return "Werkt vaste nachten (zelf invullen bij elke maand).";
  if (isFlex(e)) return "Invaller of uitzendkracht: werkt alleen wat je zelf vastzet.";
  const d = (w) => DAGK.filter((_, k) => e.dagen[k] === w).join(", ");
  const delen = [];
  if (d("Nooit")) delen.push("nooit op " + d("Nooit"));
  if (d("Vrij")) delen.push("vrij op " + d("Vrij"));
  if (d("Liever niet")) delen.push("liever niet op " + d("Liever niet"));
  const graag = "VTL".split("").filter((s) => e.diensten[s] === "Graag"), ln = "VTL".split("").filter((s) => e.diensten[s] === "Liever niet");
  if (graag.length) delen.push("graag " + graag.map((s) => DIENST[s].naam.toLowerCase()).join(" en "));
  if (ln.length) delen.push("liever geen " + ln.map((s) => DIENST[s].naam.toLowerCase()).join(" of "));
  delen.push({ Graag: "doet graag nachten", Neutraal: "nachten als het moet", Nooit: "geen nachten" }[e.nachten || "Neutraal"]);
  if (!e.vergadering) delen.push("niet bij de vergadering");
  return delen.join("; ").replace(/^./, (c) => c.toUpperCase()) + ".";
}

async function paginaTeam() {
  team = await api("GET", "/api/team");
  const emps = team.employees;
  app.innerHTML = `<h1>Team</h1>
    <p class="uitleg">Wie er in het rooster staan en wat ze graag willen. Dit geldt voor elke maand. Wijzigingen worden meteen opgeslagen.</p>
    <div class="knoppen"><button class="knop" id="toev">Medewerker toevoegen</button></div>
    ${emps.length ? `<ul class="mw-lijst">${emps.map((e, i) => `<li><span class="naam">${h(e.naam || "(geen naam)")}</span>
      <span class="samenvatting">${getal(e.fte, 2)} fte${isFlex(e) ? "" : `, ${getal(urenPerWeek(e))} uur per week`}. ${h(samenvatting(e))}</span>
      <span class="acties"><button class="knop klein" data-w="${i}">Wijzigen</button>
      <button class="knop stil klein" data-op="${i}" aria-label="${h(e.naam)} omhoog" ${i === 0 ? "disabled" : ""}>↑</button>
      <button class="knop stil klein" data-neer="${i}" aria-label="${h(e.naam)} omlaag" ${i === emps.length - 1 ? "disabled" : ""}>↓</button></span></li>`).join("")}</ul>`
      : `<div class="vlak leeg"><p>Nog geen medewerkers. Klik op <b>Medewerker toevoegen</b>, of lees bij Instellingen het Excel-bestand in.</p></div>`}
    <h2>Vaste afspraken</h2>
    <p class="uitleg">Afspraken die elke maand terugkomen, bijvoorbeeld: Karin werkt in week 2 op woensdag graag een vroege dienst. Week betekent: de hoeveelste woensdag van de maand.</p>
    <div class="tabelwrap"><table class="tabel" id="afs"><thead><tr><th>Wie</th><th>Dag</th><th>Week</th><th>Dienst</th><th>Soort</th><th></th></tr></thead><tbody></tbody></table></div>
    <div class="knoppen"><button class="knop tweede" id="afsToev" ${emps.length ? "" : "disabled"}>Afspraak toevoegen</button></div>`;
  $("#toev").onclick = async () => { const e = await api("GET", "/api/nieuwe-medewerker"); bewerkMedewerker(e, true); };
  $$("[data-w]").forEach((b) => (b.onclick = () => bewerkMedewerker(team.employees[Number(b.dataset.w)], false)));
  const wissel = (i, j) => { [emps[i], emps[j]] = [emps[j], emps[i]]; bewaarTeam(); paginaTeamNa(); };
  $$("[data-op]").forEach((b) => (b.onclick = () => wissel(Number(b.dataset.op), Number(b.dataset.op) - 1)));
  $$("[data-neer]").forEach((b) => (b.onclick = () => wissel(Number(b.dataset.neer), Number(b.dataset.neer) + 1)));
  const opt = (lijst, v) => lijst.map(([w, t]) => `<option value="${h(w)}" ${String(v ?? "") === String(w) ? "selected" : ""}>${h(t)}</option>`).join("");
  const tekenAfs = () => {
    $("#afs tbody").innerHTML = team.afspraken.length ? team.afspraken.map((a, i) => `<tr data-i="${i}">
      <td><select data-f="emp" aria-label="Wie">${opt(emps.map((e) => [e.id, e.naam]), a.emp)}</select></td>
      <td><select data-f="weekdag" aria-label="Dag">${opt(DAGLANG.map((d, k) => [k, d]), a.weekdag)}</select></td>
      <td><select data-f="week" aria-label="Week">${opt([["", "elke week"], [1, "1e"], [2, "2e"], [3, "3e"], [4, "4e"], [5, "5e"]], a.week ?? "")}</select></td>
      <td><select data-f="dienst" aria-label="Dienst">${opt(S.map((s) => [s, DIENST[s].naam]), a.dienst)}</select></td>
      <td><select data-f="soort" aria-label="Soort">${opt(AFSPRAAKKEUZE.map((s) => [s, s]), a.soort)}</select></td>
      <td><button class="knop gevaar klein" data-weg="${i}">Verwijderen</button></td></tr>`).join("")
      : `<tr><td colspan="6" class="uitleg">Geen vaste afspraken.</td></tr>`;
  };
  tekenAfs();
  $("#afs").onchange = (ev) => {
    const s = ev.target.closest("select"); if (!s) return;
    const a = team.afspraken[Number(s.closest("tr").dataset.i)], f = s.dataset.f;
    a[f] = f === "weekdag" ? Number(s.value) : f === "week" ? (s.value === "" ? null : Number(s.value)) : s.value;
    bewaarTeam();
  };
  $("#afs").onclick = (ev) => { const b = ev.target.closest("[data-weg]"); if (b) { team.afspraken.splice(Number(b.dataset.weg), 1); bewaarTeam(); tekenAfs(); } };
  $("#afsToev").onclick = () => { team.afspraken.push({ emp: emps[0].id, weekdag: 0, week: null, dienst: "V", soort: "Graag" }); bewaarTeam(); tekenAfs(); };
}
async function paginaTeamNa() { await slaAllesOp(); await paginaTeam(); }

function keuzeHTML(naam, lijst, waarde) {
  return `<div class="keuze" role="group" data-k="${naam}">${lijst.map(([w, t]) => `<button type="button" data-v="${h(w)}" aria-pressed="${String(waarde ?? "") === String(w)}">${h(t)}</button>`).join("")}</div>`;
}
function bewerkMedewerker(orig, nieuw) {
  const e = JSON.parse(JSON.stringify(orig));
  e.dagen = e.dagen || Array(7).fill(""); e.diensten = e.diensten || { V: "", T: "", L: "" };
  const nr = (v) => (v === null || v === undefined || v === "" ? "" : v);
  dialoog(`<form id="mw"><div class="binnen"><h2>${nieuw ? "Nieuwe medewerker" : h(e.naam)}</h2>
    <div class="raster2"><div class="veld"><label for="mw-naam">Naam</label><input type="text" id="mw-naam" value="${h(e.naam)}" required autocomplete="off"></div>
    <div class="veld"><label for="mw-fte">Contract in fte</label><input type="number" id="mw-fte" step="0.01" min="0" max="1.2" value="${nr(e.fte)}" required>
      <div class="hint" id="mw-uren"></div></div></div>
    <label class="vinkje"><input type="checkbox" id="mw-vn" ${e.vast_nacht ? "checked" : ""}><span><b>Werkt alleen vaste nachten</b><br><span class="uitleg">Je zet de nachten elke maand zelf neer bij stap 4. Het programma plant deze persoon verder niet in.</span></span></label>
    <div id="mw-dag">
      <h3>Dagen</h3><div class="weekkeuze">${DAGLANG.map((d, k) => `<span>${d}</span>${keuzeHTML("dag" + k, DAGKEUZE, e.dagen[k])}`).join("")}</div>
      <p class="uitleg">Nooit: kan echt niet, wordt nooit ingepland. Vaste vrije dag: liefst nooit, alleen als het echt niet anders kan.</p>
      <h3>Diensten</h3><div class="weekkeuze">${"VTL".split("").map((s) => `<span>${DIENST[s].naam}</span>${keuzeHTML("dienst" + s, DIENSTKEUZE, e.diensten[s])}`).join("")}
        <span>Nachten</span>${keuzeHTML("nacht", NACHTKEUZE, e.nachten || "Neutraal")}</div>
      <label class="vinkje"><input type="checkbox" id="mw-verg" ${e.vergadering ? "checked" : ""}><span><b>Komt naar de teamvergadering</b> (2e maandag van de maand)</span></label>
      <label class="vinkje"><input type="checkbox" id="mw-reeks" ${e.reeksregels !== false ? "checked" : ""}><span><b>Gezonde rijtjes</b>: na een reeks werkdagen minstens 2 dagen vrij, geen losse vrije dag ertussen. Zet uit voor bijvoorbeeld iemand met een stage elders.</span></label>
      <details class="extra"><summary>Meer instellingen</summary>
        <div class="raster2" style="margin-top:.6rem">
        <div class="veld"><label for="mw-lmr">Liefst niet meer dan ... dagen achter elkaar</label><input type="number" id="mw-lmr" min="1" max="7" value="${nr(e.liefst_max_rij)}"><div class="hint">Leeg: de gewone grens van ${team.settings.max_rij}.</div></div>
        <div class="veld"><label for="mw-mnr">Nachten minstens ... achter elkaar</label><input type="number" id="mw-mnr" min="1" max="7" value="${nr(e.min_nacht_rij)}"><div class="hint">Bijvoorbeeld 2: geen losse nachten.</div></div>
        <div class="veld"><label for="mw-mat">Hooguit ... procent tussendiensten</label><input type="number" id="mw-mat" min="0" max="100" step="5" value="${e.max_aandeel_t === null || e.max_aandeel_t === undefined || e.max_aandeel_t === "" ? "" : Math.round(e.max_aandeel_t * 100)}"></div>
        <div class="veld"><label for="mw-mdd">Minstens ... doordeweekse dagen per 2 weken</label><input type="number" id="mw-mdd" min="0" max="10" value="${nr(e.min_dd)}"></div></div>
      </details></div>
    <div class="veld" style="margin-top:1rem"><label for="mw-opm">Opmerking (alleen voor jezelf)</label><textarea id="mw-opm">${h(e.opmerking || "")}</textarea></div>
    </div><div class="onder">${nieuw ? "" : `<button type="button" class="knop gevaar" id="mw-weg" style="margin-right:auto">Verwijderen</button>`}
    <button type="button" class="knop tweede" id="mw-annu">Annuleren</button><button type="submit" class="knop">Opslaan</button></div></form>`, { breed: true });
  const urenTekst = () => {
    const f = Number($("#mw-fte").value || 0);
    $("#mw-uren").textContent = f === 0 && !$("#mw-vn").checked ? "0 fte: invaller of uitzendkracht. Werkt alleen wat je bij stap 4 vastzet." : `${getal(f * team.settings.uren_fte)} uur per week`;
    $("#mw-dag").hidden = $("#mw-vn").checked || (f === 0);
  };
  urenTekst();
  $("#mw-fte").oninput = urenTekst; $("#mw-vn").onchange = urenTekst;
  $$(".keuze", dlg).forEach((g) => g.addEventListener("click", (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    $$("button", g).forEach((x) => x.setAttribute("aria-pressed", x === b));
  }));
  $("#mw-annu").onclick = () => dlg.close();
  if (!nieuw) $("#mw-weg").onclick = async () => {
    dlg.close();
    if (!(await vraag(`${orig.naam} verwijderen?`, "Deze persoon verdwijnt uit het team en uit roosters die je hierna maakt. Afspraken van deze persoon worden ook verwijderd.", "Verwijderen", true))) return;
    team.employees = team.employees.filter((x) => x.id !== orig.id);
    team.afspraken = team.afspraken.filter((a) => a.emp !== orig.id);
    bewaarTeam(); paginaTeamNa();
  };
  $("#mw").onsubmit = (ev) => {
    ev.preventDefault();
    const getalOfNiets = (s) => { const v = $(s).value.trim(); return v === "" ? null : Number(v); };
    const k = (n) => $(`.keuze[data-k="${n}"] [aria-pressed=true]`, dlg)?.dataset.v ?? "";
    e.naam = $("#mw-naam").value.trim(); e.fte = Number($("#mw-fte").value || 0);
    e.vast_nacht = $("#mw-vn").checked;
    e.dagen = DAGLANG.map((_, i) => k("dag" + i));
    e.diensten = { V: k("dienstV"), T: k("dienstT"), L: k("dienstL") };
    e.nachten = k("nacht") || "Neutraal";
    e.vergadering = $("#mw-verg").checked; e.reeksregels = $("#mw-reeks").checked;
    e.liefst_max_rij = getalOfNiets("#mw-lmr"); e.min_nacht_rij = getalOfNiets("#mw-mnr");
    const mat = getalOfNiets("#mw-mat"); e.max_aandeel_t = mat === null ? null : mat / 100;
    e.min_dd = getalOfNiets("#mw-mdd"); e.opmerking = $("#mw-opm").value;
    if (!e.naam) return;
    if (nieuw) team.employees.push(e); else team.employees[team.employees.findIndex((x) => x.id === e.id)] = e;
    dlg.close(); bewaarTeam(); melding(`${e.naam} is opgeslagen.`); paginaTeamNa();
  };
}

/* ---------- instellingen ---------- */
async function paginaInstellingen() {
  team = await api("GET", "/api/team");
  const st = team.settings;
  const veld = (k, label, hint, attr = "") => `<div class="veld"><label for="st-${k}">${label}</label><input type="number" id="st-${k}" data-s="${k}" value="${st[k] ?? ""}" ${attr}>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
  const prio = (k) => `<select data-prio="${k}" aria-label="Tussendienst ${DAGLANG[k]}">${[["", "nooit"], [1, "als eerste"], [2, "als tweede"], [3, "als derde"], [4, "als vierde"]].map(([v, t]) => `<option value="${v}" ${String(st.t_prio?.[k] ?? "") === String(v) ? "selected" : ""}>${t}</option>`).join("")}</select>`;
  app.innerHTML = `<h1>Instellingen</h1>
    <p class="uitleg">Deze instellingen gelden voor alle maanden. Pas ze alleen aan als de afspraken veranderen.</p>
    <h2>Bezetting per dag</h2><p class="uitleg">Hoeveel mensen er per dienst nodig zijn. Een tussendienst met 0 kan toch worden ingepland als er uren over zijn (zie hieronder).</p>
    <div class="tabelwrap"><table class="tabel" id="bez"><thead><tr><th>Dag</th>${S.map((s) => `<th>${DIENST[s].naam}</th>`).join("")}</tr></thead>
      <tbody>${DAGLANG.map((d, k) => `<tr><th scope="row">${d}</th>${S.map((s, j) => `<td><input type="number" min="0" max="9" data-b="${k},${j}" value="${team.bezetting[k][j]}" aria-label="${DIENST[s].naam} op ${d}"></td>`).join("")}</tr>`).join("")}</tbody></table></div>
    <h2>Extra tussendiensten</h2><p class="uitleg">Als mensen te veel uren hebben, mag het programma een extra tussendienst inplannen. In welke volgorde?</p>
    <div class="vlak"><div class="raster2">${[0, 1, 2, 3].map((k) => `<div class="veld"><label>${DAGLANG[k]}</label>${prio(k)}</div>`).join("")}</div>
      ${veld("max_t", "Hooguit zoveel extra tussendiensten per dag", "", 'min="0" max="3"')}</div>
    <h2>Regels</h2><div class="vlak"><div class="raster2">
      ${veld("uren_fte", "Uren per week bij 1 fte", "", 'step="0.5"')}
      ${veld("u_dag", "Uren van een dagdienst", "")}
      ${veld("u_nacht", "Uren van een nachtdienst", "")}
      ${veld("saldogrens", "Saldo mag hooguit zoveel uren plus of min zijn", "")}
      ${veld("max_rij", "Hooguit zoveel dagen achter elkaar werken", "", 'min="1" max="7"')}
      ${veld("max_nacht_rij", "Hooguit zoveel nachten achter elkaar", "", 'min="1" max="14"')}
      ${veld("rekentijd", "Rekentijd in seconden", "Langer zoeken kan een iets beter rooster geven.", 'min="10" max="240" step="10"')}
    </div></div>
    <h2>Teamvergadering</h2><div class="vlak">
      <label class="vinkje"><input type="checkbox" id="st-verg" ${st.vergadering ? "checked" : ""}><span><b>Elke 2e maandag van de maand, 13:00 tot 17:00</b></span></label>
      <div class="raster2">${veld("verg_vrij", "Uren als je die dag vrij bent", "")}${veld("verg_v", "Extra uren naast een vroege dienst", "")}${veld("verg_l", "Extra uren naast een late dienst", "")}${veld("verg_t", "Extra uren naast een tussendienst", "")}</div></div>
    <h2>Gegevens</h2><div class="vlak">
      <p>Maak af en toe een back-up, bijvoorbeeld na elk definitief rooster. Daarmee zet je alles terug als er iets misgaat.</p>
      <div class="knoppen"><a class="knop" href="/api/backup" download>Back-up downloaden</a>
        <label class="knop tweede" style="margin:0">Back-up terugzetten<input type="file" id="herstel" accept=".json,application/json" hidden></label></div>
      <h3>Excel-bestand van de roostermaker inlezen</h3>
      <p class="uitleg">Neemt het team, de voorkeuren, de instellingen en de maand uit het oude Excel-bestand over. Het team hier wordt dan vervangen.</p>
      <div class="knoppen"><label class="knop tweede" style="margin:0">Excel-bestand kiezen<input type="file" id="xls" accept=".xlsx" hidden></label></div>
      <h3>Oefenen</h3>
      <p class="uitleg">Zet een verzonnen team (Anna, Bram, Chantal ...) met een voorbeeldmaand klaar. Handig om de roostermaker uit te proberen zonder echte namen. Het team hier wordt dan vervangen.</p>
      <div class="knoppen"><button class="knop tweede" id="oefen">Voorbeeldteam laden</button></div>
    </div>`;
  $("#oefen").onclick = async () => {
    if (!(await vraag("Voorbeeldteam laden?", "Het team en de instellingen hier worden vervangen door een verzonnen team. Bestaande maanden blijven staan.", "Laden", medewerkers().length > 0))) return;
    try { const r = await api("POST", "/api/voorbeeld"); team = null; cur = null; melding("Voorbeeldteam geladen."); location.hash = `#/maand/${r.key}/1`; }
    catch (e) { melding(e.message, true); }
  };
  app.oninput = (ev) => {
    const i = ev.target;
    if (i.dataset.b) { const [k, j] = i.dataset.b.split(",").map(Number); team.bezetting[k][j] = Math.max(0, Number(i.value || 0)); bewaarTeam(); }
    else if (i.dataset.s) { if (i.value !== "") { st[i.dataset.s] = Number(i.value); bewaarTeam(); } }
  };
  app.onchange = async (ev) => {
    const i = ev.target;
    if (i.dataset.prio !== undefined) { st.t_prio = st.t_prio || [null, null, null, null]; st.t_prio[Number(i.dataset.prio)] = i.value === "" ? null : Number(i.value); bewaarTeam(); }
    else if (i.id === "st-verg") { st.vergadering = i.checked; bewaarTeam(); cur = null; }
    else if (i.id === "herstel" && i.files[0]) {
      if (!(await vraag("Back-up terugzetten?", "Het team en de maanden uit de back-up vervangen wat er nu staat.", "Terugzetten", true))) { i.value = ""; return; }
      const f = new FormData(); f.append("bestand", i.files[0]);
      try { const r = await api("POST", "/api/restore", undefined, f); team = null; cur = null; melding(`Back-up teruggezet (${r.aantal} onderdelen).`); location.hash = "#/"; }
      catch (e) { melding(e.message, true); } i.value = "";
    } else if (i.id === "xls" && i.files[0]) {
      if (medewerkers().length && !(await vraag("Excel-bestand inlezen?", "Het team en de instellingen hier worden vervangen door die uit het Excel-bestand.", "Inlezen", true))) { i.value = ""; return; }
      const f = new FormData(); f.append("bestand", i.files[0]);
      try { const r = await api("POST", "/api/import-excel", undefined, f); team = null; cur = null; melding(`Ingelezen: ${r.medewerkers} medewerkers en ${maandLabel(r.key)}.`); location.hash = `#/maand/${r.key}/1`; }
      catch (e) { melding(e.message, true); } i.value = "";
    }
  };
}

start();
