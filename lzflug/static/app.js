// lz-flugsuche · Oberfläche
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const eur = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' });
const eur0 = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
const tag = new Intl.DateTimeFormat('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', year: '2-digit' });
const uhr = new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' });

const speicher = {
  lesen(k, d) { try { const v = localStorage.getItem('lzflug.' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  schreiben(k, v) { try { localStorage.setItem('lzflug.' + k, JSON.stringify(v)); } catch { /* privat */ } },
};

function esc(t) {
  return String(t ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function datum(iso) { return iso ? tag.format(new Date(iso + 'T12:00:00')) : ''; }
function dauer(min) { if (!min) return ''; const h = Math.floor(min / 60), m = min % 60; return h ? `${h} h ${m ? m + ' min' : ''}`.trim() : `${m} min`; }
function alter(iso) {
  if (!iso) return '';
  const min = Math.round((Date.now() - new Date(iso)) / 60000);
  if (min < 60) return `vor ${Math.max(min, 1)} min`;
  if (min < 2880) return `vor ${Math.round(min / 60)} h`;
  return `vor ${Math.round(min / 1440)} Tagen`;
}

/* ---------- Thema ---------- */
function thema(wahl) {
  const root = document.documentElement;
  if (wahl === 'auto') root.removeAttribute('data-theme'); else root.dataset.theme = wahl;
  $$('.thema button').forEach(b => b.setAttribute('aria-checked', String(b.dataset.thema === wahl)));
  speicher.schreiben('thema', wahl);
}
$$('.thema button').forEach(b => b.addEventListener('click', () => thema(b.dataset.thema)));
thema(speicher.lesen('thema', 'auto'));

/* ---------- Flughafen-Vorschläge ---------- */
function vorschlaege(input, liste, onWahl) {
  let treffer = [], aktiv = -1, timer;
  const zeigen = () => {
    liste.innerHTML = treffer.map((f, i) =>
      `<li role="option" data-i="${i}" aria-selected="${i === aktiv}"><b>${esc(f.iata)}</b> ${esc(f.ort || f.name)} <small>${esc(f.name)} · ${esc(f.land_name)}</small></li>`).join('');
    liste.hidden = !treffer.length;
  };
  const waehlen = f => { input.value = `${f.ort || f.name} (${f.iata})`; input.dataset.iata = f.iata; liste.hidden = true; onWahl?.(f); };
  input.addEventListener('input', () => {
    delete input.dataset.iata;
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { treffer = []; zeigen(); return; }
    timer = setTimeout(async () => {
      try { treffer = await (await fetch('/api/flughaefen?q=' + encodeURIComponent(q))).json(); } catch { treffer = []; }
      aktiv = treffer.length ? 0 : -1; zeigen();
    }, 150);
  });
  input.addEventListener('keydown', e => {
    if (liste.hidden) return;
    if (e.key === 'ArrowDown') { aktiv = Math.min(aktiv + 1, treffer.length - 1); zeigen(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { aktiv = Math.max(aktiv - 1, 0); zeigen(); e.preventDefault(); }
    else if (e.key === 'Enter' && aktiv >= 0) { waehlen(treffer[aktiv]); e.preventDefault(); }
    else if (e.key === 'Escape') liste.hidden = true;
  });
  liste.addEventListener('mousedown', e => { const li = e.target.closest('li'); if (li) { waehlen(treffer[+li.dataset.i]); e.preventDefault(); } });
  input.addEventListener('blur', () => setTimeout(() => { liste.hidden = true; }, 120));
}
function iata(input) {
  if (input.dataset.iata) return input.dataset.iata;
  const m = input.value.match(/\b([A-Za-z]{3})\)?\s*$/);
  return m ? m[1].toUpperCase() : '';
}

const start = $('#start');
vorschlaege(start, $('#start-liste'), f => speicher.schreiben('start', { iata: f.iata, text: start.value }));
vorschlaege($('#zielflughafen'), $('#ziel-liste'));
const gemerkt = speicher.lesen('start', null);
if (gemerkt) { start.value = gemerkt.text; start.dataset.iata = gemerkt.iata; }

/* ---------- Formular ---------- */
const radius = $('#radius');
const radiusZeigen = () => { $('#radius-wert').textContent = radius.value === '0' ? 'nur dieser' : radius.value + ' km'; };
radius.addEventListener('input', radiusZeigen);
radius.value = speicher.lesen('radius', 200); radiusZeigen();

function zielArt() { return $('input[name="ziel_art"]:checked').value; }
function zielfelder() { $$('[data-fuer]').forEach(f => { f.hidden = f.dataset.fuer !== zielArt(); }); }
$$('input[name="ziel_art"]').forEach(r => r.addEventListener('change', zielfelder));
function reisefelder() { const r = $('input[name="reise"]:checked').value; $$('[data-fuer-reise]').forEach(f => { f.hidden = f.dataset.fuerReise !== r; }); }
$$('input[name="reise"]').forEach(r => r.addEventListener('change', reisefelder));

const heute = new Date();
const iso = d => d.toISOString().slice(0, 10);
$('#von').value = iso(new Date(heute.getTime() + 14 * 864e5));
$('#bis').value = iso(new Date(heute.getTime() + 45 * 864e5));

(async () => {
  const info = await (await fetch('/api/info')).json();
  $('#kontinent').innerHTML = Object.entries(info.kontinente).filter(([k]) => k !== 'AN')
    .map(([k, n]) => `<option value="${k}">${esc(n)}</option>`).join('');
  const laender = await (await fetch('/api/laender')).json();
  $('#land').innerHTML = laender.map(l => `<option value="${l.code}">${esc(l.name)}</option>`).join('');
  $('#land').value = 'ES';
})();
zielfelder(); reisefelder();

/* ---------- Suche ---------- */
let laufend = null, letztes = null;

$('#suche').addEventListener('submit', async e => {
  e.preventDefault();
  const s = iata(start);
  if (!s) { meldung('Bitte einen Heimatflughafen aus der Liste wählen (oder den IATA-Code eintippen, z. B. FRA).'); start.focus(); return; }
  const art = zielArt();
  let ziel = '';
  if (art === 'kontinent') ziel = $('#kontinent').value;
  if (art === 'land') ziel = $('#land').value;
  if (art === 'flughafen') {
    ziel = iata($('#zielflughafen'));
    if (!ziel) { meldung('Bitte einen Zielflughafen aus der Liste wählen.'); $('#zielflughafen').focus(); return; }
  }
  speicher.schreiben('radius', +radius.value);
  const rueck = $('input[name="reise"]:checked').value === 'rueck';
  const body = {
    start: s, ziel_art: art, ziel, von_datum: $('#von').value, bis_datum: $('#bis').value,
    naechte: rueck ? +$('#naechte').value : null, radius_km: +radius.value, erwachsene: +$('#erwachsene').value,
    gepaeck: $('#gepaeck').value, nur_direkt: $('#direkt').checked, eur_pro_km: +$('#eurkm').value, live_pruefen: +$('#live').value,
  };
  meldung('');
  const r = await fetch('/api/suche', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const antwort = await r.json();
  if (!r.ok) { meldung(antwort.detail?.[0]?.msg || antwort.detail || 'Suche konnte nicht starten.'); return; }
  laufend = antwort.id;
  $('#los').disabled = true; $('#stand').hidden = false; $('#leer').hidden = true;
  $('#liste').innerHTML = ''; $('#kopfzeile').hidden = true; gezeigt.clear();
  abfragen(antwort.id);
});

$('#stopp').addEventListener('click', async () => {
  if (laufend) await fetch('/api/suche/' + laufend, { method: 'DELETE' });
});

async function abfragen(id) {
  if (id !== laufend) return;
  let d;
  try { d = await (await fetch('/api/suche/' + id)).json(); } catch { setTimeout(() => abfragen(id), 2000); return; }
  const f = d.fortschritt;
  $('#schritt').textContent = f.gesamt ? `${f.schritt} · ${f.erledigt}/${f.gesamt}` : f.schritt;
  $('#balken').max = f.gesamt || 1; $('#balken').value = f.erledigt;
  if (d.ergebnis) { letztes = d.ergebnis; zeichnen(d.ergebnis, d.fertig); }
  if (d.fehler) meldung(d.fehler);
  if (d.fertig) { laufend = null; $('#los').disabled = false; $('#stand').hidden = true; if (!d.ergebnis && !d.fehler) $('#leer').hidden = false; return; }
  setTimeout(() => abfragen(id), 1000);
}

function meldung(text) { const m = $('#fehler'); m.textContent = text; m.hidden = !text; }

$$('input[name="sort"]').forEach(r => r.addEventListener('change', () => { if (letztes) { gezeigt.clear(); $('#liste').innerHTML = ''; zeichnen(letztes, !laufend); } }));

/* ---------- Ergebnisse ---------- */
const gezeigt = new Set();
const QUELLE = { 'google-live': ['Live geprüft', 'ok'], 'google-kalender': ['Kalenderpreis', ''], 'ryanair': ['Ryanair direkt', ''] };

function zeichnen(e, fertig) {
  const a = e.anfrage;
  $('#kopfzeile').hidden = false;
  $('#zusammenfassung').innerHTML =
    `<strong>${e.ziele_mit_preis}</strong> Ziele mit Preis · <strong>${e.ziele_durchsucht}</strong> Zielflughäfen bei Google abgefragt, dazu alle Ryanair-Ziele` +
    (fertig ? '' : ' · <em>Suche läuft, Liste wird ergänzt</em>');
  $('#abflughaefen').innerHTML = e.abflughaefen.map((x, i) =>
    `<span class="chip ${x.durchsucht ? '' : 'aus'}" title="${esc(x.name)}"><b>${esc(x.iata)}</b> ${esc(x.ort)}` +
    (i ? ` · ${x.strasse_km} km · ${dauer(x.fahrzeit_min)} · ${eur0.format(x.anreise_eur)}` : ' · Heimat') + `</span>`).join('');
  $('#hinweise').innerHTML = (e.hinweise || []).map(h => `<div class="hinweis">${esc(h)}</div>`).join('');

  const sort = $('input[name="sort"]:checked').value;
  const ziele = [...e.ziele].sort((x, y) => sort === 'preis' ? x.bestes.preis - y.bestes.preis : x.gesamt - y.gesamt).slice(0, 80);
  const liste = $('#liste');
  liste.innerHTML = '';
  ziele.forEach((z, i) => liste.append(karte(z, a, i, gezeigt.has(z.ziel.iata))));
  ziele.forEach(z => gezeigt.add(z.ziel.iata));
}

function karte(z, a, i, schonDa) {
  const b = z.bestes, ziel = z.ziel;
  const li = document.createElement('li');
  li.className = 'karte treffer';
  if (schonDa) li.style.animation = 'none'; else li.style.animationDelay = Math.min(i, 12) * 45 + 'ms';
  const opt = z.optionen.find(o => o.abflug === z.abflug);
  const [qText, qKlasse] = QUELLE[b.quelle] || [b.quelle, ''];
  const abz = [`<span class="badge ${qKlasse}">${qText}${b.quelle === 'ryanair' && b.preis_stand ? ' · Stand ' + alter(b.preis_stand) : ''}</span>`];
  if (z.ersparnis > 0) abz.push(`<span class="badge spar">spart ${eur0.format(z.ersparnis)} ggü. ${esc(a.start)}</span>`);
  if (b.quelle === 'ryanair' && a.gepaeck !== 'keins') abz.push('<span class="badge warn">Gepäck kommt dazu</span>');
  if (b.selbst_umstieg) abz.push('<span class="badge warn">Selbst umsteigen, kein Anschlussschutz</span>');
  if (z.verlauf?.tiefst != null) {
    const d = b.preis - z.verlauf.tiefst;
    abz.push(`<span class="badge ${d <= 0 ? 'ok' : ''}">${d <= 0 ? 'Tiefster bisher gesehener Preis' : 'Bisher tiefst ' + eur0.format(z.verlauf.tiefst)}</span>`);
  }
  abz.push(`<span class="badge">${esc(b.gepaeck)}</span>`);

  const zeiten = b.abflug && b.abflug.length > 10 ? ` · ${uhr.format(new Date(b.abflug))}` : '';
  const stopps = b.stopps == null ? '' : b.stopps === 0 ? 'Direkt' : `${b.stopps} Umstieg${b.stopps > 1 ? 'e' : ''}`;
  li.innerHTML = `
    <div class="treffer-kopf">
      <div>
        <h3>${esc(ziel.ort || ziel.iata)} <span class="land">${esc(ziel.iata)} · ${esc(ziel.land_name || '')}</span></h3>
        <div class="meta">ab <b>${esc(b.von)}</b>${b.von !== a.start ? ` (${opt ? opt.strasse_km + ' km Anfahrt' : ''})` : ''} · ${datum(b.hin)}${zeiten}${b.rueck ? ' – ' + datum(b.rueck) : ''}</div>
      </div>
      <div class="preis">
        <div class="gross">${eur0.format(z.gesamt)}</div>
        <div class="klein">Flug ${eur.format(b.preis)}${opt && opt.anreise_eur ? ' + Anreise ' + eur0.format(opt.anreise_eur) : ''}</div>
      </div>
    </div>
    <div class="details">
      ${b.airline ? `<span>${esc(b.airline)}</span>` : ''}
      ${stopps ? `<span>${stopps}</span>` : ''}
      ${b.dauer_min ? `<span>${dauer(b.dauer_min)}</span>` : ''}
      ${b.flugnummern ? `<span class="meta">${esc(b.flugnummern.join(', '))}</span>` : ''}
    </div>
    <div class="abzeichen">${abz.join('')}</div>
    <div class="aktionen">
      <a class="buchen" href="${esc(b.link)}" target="_blank" rel="noopener">${b.quelle === 'ryanair' ? 'Bei Ryanair ansehen' : 'Bei Google Flights ansehen'}</a>
      ${z.optionen.length > 1 ? `<details class="optionen"><summary>${z.optionen.length} Abflughäfen im Vergleich</summary>${tabelle(z)}</details>` : ''}
    </div>`;
  return li;
}

function tabelle(z) {
  return `<table class="tabelle"><thead><tr><th>ab</th><th class="breit">Datum</th><th class="zahl">Flug</th><th class="zahl breit">Anreise</th><th class="zahl">Gesamt</th><th></th></tr></thead><tbody>` +
    z.optionen.map(o => `<tr><td><b>${esc(o.abflug)}</b></td><td class="breit">${datum(o.angebot.hin)}</td>` +
      `<td class="zahl">${eur0.format(o.angebot.preis)}</td><td class="zahl breit">${eur0.format(o.anreise_eur)}</td>` +
      `<td class="zahl"><b>${eur0.format(o.gesamt)}</b></td><td><a href="${esc(o.angebot.link)}" target="_blank" rel="noopener">ansehen</a></td></tr>`).join('') +
    `</tbody></table>`;
}
