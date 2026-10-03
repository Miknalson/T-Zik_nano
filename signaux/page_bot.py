"""Page « Bot Kraken » : valeur, gains et pertes, courbe, positions ouvertes et historique.

Lit les fichiers du bot (papier et réel) et écrit une page autonome à côté de la page des
signaux. Appelée par signaux.py à chaque mise à jour de la page.
"""
import csv
import datetime as dt
import html
import json
import os

from signaux import DOSSIER, prix

BOTS = [("Papier", "argent fictif", "bot_portefeuille.json", "bot_journal.csv"),
        ("Réel", "ton compte Kraken", "bot_reel.json", "bot_reel_journal.csv")]
GENRES = {"achat": "Achat", "vente": "Vente", "stop": "Stop touché"}
INSECABLE = "\u00a0"  # espace qui ne coupe pas « 1 000 € » en fin de ligne


def euros(x, signe=False, centimes=True):
    texte = f"{abs(x):,.{2 if centimes else 0}f}".replace(",", INSECABLE).replace(".", ",") + INSECABLE + "€"
    if not signe:
        return ("−" if x < 0 else "") + texte
    return ("+" if x >= 0 else "−") + texte


def pourcent(x):
    return f"{x:+.2%}".replace(".", ",").replace("%", INSECABLE + "%")


def date_fr(iso):
    return f"{dt.date.fromisoformat(iso):%d/%m/%Y}"


def sens(x):
    """Classe CSS et flèche : la couleur n'est jamais seule, la flèche et le signe la doublent."""
    return ("gain", "▲") if x >= 0 else ("perte", "▼")


def charger(dossier, fichier_etat, fichier_journal):
    chemin = os.path.join(dossier, fichier_etat)
    if not os.path.exists(chemin):
        return None
    with open(chemin, encoding="utf-8") as f:
        etat = json.load(f)
    if not etat.get("maj"):
        return None
    operations = []
    chemin_journal = os.path.join(dossier, fichier_journal)
    if os.path.exists(chemin_journal):
        with open(chemin_journal, newline="", encoding="utf-8") as f:
            operations = list(csv.DictReader(f, delimiter=";"))
    return etat, operations


def bilan(etat, operations):
    depart = etat.get("depart", 1000.0)
    ventes = [float(o["resultat"]) for o in operations if o["operation"] in ("vente", "stop")]
    latent = sum(p["quantite"] * p.get("prix_actuel", p["prix_entree"]) - p.get("cout", 0)
                 for p in etat["positions"].values())
    return {"depart": depart, "valeur": etat["valeur"], "gain": etat["valeur"] - depart,
            "pct": etat["valeur"] / depart - 1 if depart else 0.0, "realise": sum(ventes), "latent": latent,
            "ventes": len(ventes), "gagnantes": sum(v > 0 for v in ventes)}


def points_courbe(etat, operations):
    points = [(h["date"], h["valeur"]) for h in etat.get("historique", [])]
    if operations and (not points or operations[0]["date"] < points[0][0]):
        points.insert(0, (operations[0]["date"], etat.get("depart", 1000.0)))
    return points


def courbe(points, depart, ident):
    if len(points) < 2:
        return '<p class="vide">La courbe apparaîtra après quelques jours de fonctionnement.</p>'
    l, h, g, d, hb = 640, 300, 104, 12, 40  # largeur, hauteur, marges gauche/droite/bas
    valeurs = [v for _, v in points] + [depart]
    bas, haut = min(valeurs), max(valeurs)
    marge = (haut - bas) * 0.1 or depart * 0.01
    bas, haut = bas - marge, haut + marge
    x = [g + i * (l - g - d) / (len(points) - 1) for i in range(len(points))]
    y = lambda v: 10 + (haut - v) * (h - hb - 10) / (haut - bas)
    trace = " ".join(f"{xi:.1f},{y(v):.1f}" for xi, (_, v) in zip(x, points))
    graduations = "".join(
        f'<line x1="{g}" x2="{l - d}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grille"/>'
        f'<text x="{g - 8}" y="{y(v) + 7:.1f}" class="axe" text-anchor="end">{html.escape(euros(v, centimes=False))}</text>'
        for v in (bas + marge, (bas + haut) / 2, haut - marge))
    donnees = json.dumps([{"x": round(xi, 1), "y": round(y(v), 1), "date": date_fr(dte), "valeur": euros(v)}
                          for xi, (dte, v) in zip(x, points)])
    return f"""<div class="graphe" id="{ident}">
<svg viewBox="0 0 {l} {h}" role="img" aria-label="Valeur du portefeuille jour par jour">
{graduations}
<line x1="{g}" x2="{l - d}" y1="{y(depart):.1f}" y2="{y(depart):.1f}" class="depart"/>
<text x="{l - d}" y="{y(depart) - 8:.1f}" class="axe" text-anchor="end">départ</text>
<polyline points="{trace}" class="ligne"/>
<text x="{g}" y="{h - 8}" class="axe">{date_fr(points[0][0])}</text>
<text x="{l - d}" y="{h - 8}" class="axe" text-anchor="end">{date_fr(points[-1][0])}</text>
<line class="repere" y1="10" y2="{h - hb}" visibility="hidden"/>
<circle class="point" r="7" visibility="hidden"/>
<rect x="{g}" y="0" width="{l - g - d}" height="{h - hb}" fill="transparent" class="zone"/>
</svg><div class="bulle" hidden></div>
<script type="application/json">{donnees}</script></div>"""


def tableau_positions(etat):
    if not etat["positions"]:
        return '<p class="vide">Aucune position ouverte : le bot attend une tendance.</p>'
    lignes = []
    for nom, p in sorted(etat["positions"].items()):
        actuel = p.get("prix_actuel", p["prix_entree"])
        gain = p["quantite"] * actuel - p.get("cout", 0)
        pct = gain / p["cout"] if p.get("cout") else 0
        classe, fleche = sens(gain)
        lignes.append(f'<li><div class="haut"><b>{html.escape(nom)}</b>'
                      f'<span class="{classe}">{fleche} {html.escape(euros(gain, True))} ({html.escape(pourcent(pct))})</span></div>'
                      f'<div class="detail">Acheté le {date_fr(p["date"])} à {prix(p["prix_entree"])} € · '
                      f'maintenant {prix(actuel)} € · stop {prix(p["stop"])} € · '
                      f'valeur {html.escape(euros(p["quantite"] * actuel))}</div></li>')
    return f'<ul class="positions">{"".join(lignes)}</ul>'


def tableau_historique(operations):
    if not operations:
        return '<p class="vide">Aucune opération pour l\'instant.</p>'
    lignes = []
    for o in reversed(operations):
        quantite, prix_op = float(o["quantite"]), float(o["prix"])
        if o["operation"] == "achat":
            resultat = '<td class="doux">—</td>'
        else:
            r = float(o["resultat"])
            classe, fleche = sens(r)
            resultat = f'<td class="{classe}">{fleche} {html.escape(euros(r, True))}</td>'
        lignes.append(f"<tr><td>{date_fr(o['date'])[:5]}</td><td>{html.escape(o['marche'])}</td>"
                      f"<td>{GENRES.get(o['operation'], html.escape(o['operation']))}</td>{resultat}"
                      f"<td>{html.escape(euros(quantite * prix_op))}</td><td>{prix(prix_op)} €</td></tr>")
    return ('<div class="defile"><table><thead><tr><th>Date</th><th>Crypto</th><th>Opération</th>'
            '<th>Résultat</th><th>Montant</th><th>Prix</th></tr></thead>'
            f'<tbody>{"".join(lignes)}</tbody></table></div>')


def section(titre, sous_titre, etat, operations, ident):
    b = bilan(etat, operations)
    classe, fleche = sens(b["gain"])
    taux = f"{b['gagnantes']} sur {b['ventes']}" if b["ventes"] else "aucune vente encore"
    tuiles = [("Gains et pertes réalisés", f'<span class="{sens(b["realise"])[0]}">{sens(b["realise"])[1]} '
                                           f'{html.escape(euros(b["realise"], True))}</span>'),
              ("En cours (positions ouvertes)", f'<span class="{sens(b["latent"])[0]}">{sens(b["latent"])[1]} '
                                                f'{html.escape(euros(b["latent"], True))}</span>'),
              ("Ventes gagnantes", html.escape(taux)),
              ("Positions ouvertes", str(len(etat["positions"])))]
    tuiles_html = "".join(f'<div class="tuile"><div class="etiquette">{e}</div><div class="chiffre">{v}</div></div>'
                          for e, v in tuiles)
    return f"""<section>
<h2>{html.escape(titre)} <span>{html.escape(sous_titre)}</span></h2>
<div class="heros"><div class="valeur">{html.escape(euros(b['valeur']))}</div>
<div class="{classe} total">{fleche} {html.escape(euros(b['gain'], True))} ({html.escape(pourcent(b['pct']))}) depuis le départ ({html.escape(euros(b['depart']))})</div></div>
<div class="tuiles">{tuiles_html}</div>
<h3>Valeur jour après jour</h3>{courbe(points_courbe(etat, operations), b['depart'], ident)}
<h3>Positions ouvertes</h3>{tableau_positions(etat)}
<h3>Historique des opérations</h3>{tableau_historique(operations)}
<p class="note">Dernier passage du bot : {date_fr(etat['maj'])}. Les gains et pertes incluent les frais Kraken.</p>
</section>"""


def ecrire(chemin_sortie, dossier=DOSSIER):
    arret = False
    chemin_arret = os.path.join(dossier, "bot_arret.json")
    if os.path.exists(chemin_arret):
        with open(chemin_arret, encoding="utf-8") as f:
            arret = json.load(f).get("arret", False)
    sections = []
    for i, (titre, sous_titre, fichier_etat, fichier_journal) in enumerate(BOTS):
        donnees = charger(dossier, fichier_etat, fichier_journal)
        if donnees:
            sections.append(section(titre, sous_titre, *donnees, f"graphe{i}"))
    etat_bot = ("⏸ Arrêté : plus aucun achat (bouton « Reprendre » dans GitHub Actions)" if arret
                else "▶ Actif : il achète et vend tout seul chaque nuit")
    contenu = "".join(sections) or '<p class="vide">Le bot n\'a pas encore tourné.</p>'
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Bot Kraken</title>
<link rel="apple-touch-icon" href="icone.png">
<style>
:root{{--fond:#f6f6f4;--carte:#fff;--texte:#1d1d1b;--doux:#6b6b66;--gain:#1f7a4d;--perte:#b3261e;--bord:#e2e2dd;--grille:#e8e8e4;--serie:#2a78d6}}
@media (prefers-color-scheme:dark){{:root{{--fond:#141413;--carte:#1f1f1d;--texte:#ededea;--doux:#9b9b95;--gain:#4fbf85;--perte:#f2766c;--bord:#33332f;--grille:#2c2c29;--serie:#3987e5}}}}
body{{margin:0;background:var(--fond);color:var(--texte);font:15px/1.45 -apple-system,system-ui,sans-serif}}
main{{max-width:760px;margin:0 auto;padding:16px}}
a{{color:var(--serie)}} h1{{font-size:20px;margin:4px 0}} .sous{{color:var(--doux);font-size:13px;margin:0 0 6px}}
section{{background:var(--carte);border:1px solid var(--bord);border-radius:10px;padding:14px;margin:14px 0}}
h2{{font-size:17px;margin:0 0 8px}} h2 span{{font-weight:400;color:var(--doux);font-size:13px}}
h3{{font-size:14px;margin:18px 0 6px;color:var(--doux)}}
.valeur{{font-size:44px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums}}
.total{{font-weight:600;margin-top:2px}} .gain{{color:var(--gain)}} .perte{{color:var(--perte)}} .doux{{color:var(--doux)}}
.tuiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-top:12px}}
.tuile{{border:1px solid var(--bord);border-radius:8px;padding:8px 10px}}
.etiquette{{color:var(--doux);font-size:12px}} .chiffre{{font-size:17px;font-weight:600;font-variant-numeric:tabular-nums}}
.graphe{{position:relative}} svg{{width:100%;height:auto;display:block;touch-action:pan-y}}
.grille{{stroke:var(--grille);stroke-width:1.8}} .depart{{stroke:var(--doux);stroke-width:1.8}}
.ligne{{fill:none;stroke:var(--serie);stroke-width:3.5;stroke-linejoin:round;stroke-linecap:round}}
.axe{{fill:var(--doux);font-size:20px}} .repere{{stroke:var(--doux);stroke-width:1.8}}
.point{{fill:var(--serie);stroke:var(--carte);stroke-width:3.5}}
.bulle{{position:absolute;top:0;background:var(--carte);border:1px solid var(--bord);border-radius:6px;padding:4px 8px;font-size:13px;pointer-events:none;white-space:nowrap}}
.bulle strong{{display:block;font-variant-numeric:tabular-nums}}
.defile{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bord);white-space:nowrap}} th{{color:var(--doux);font-weight:500}}
.vide{{color:var(--doux)}} .note{{color:var(--doux);font-size:12px;margin-top:12px}}
.etat{{font-weight:600;margin:8px 0}}
.positions{{list-style:none;margin:0;padding:0}} .positions li{{padding:8px 0;border-bottom:1px solid var(--bord)}}
.positions .haut{{display:flex;justify-content:space-between;gap:8px;font-weight:600}}
.positions .detail{{color:var(--doux);font-size:12px;margin-top:2px}}
</style></head><body><main>
<p class="sous"><a href="index.html">← Signaux du jour</a></p>
<h1>🤖 Bot Kraken</h1>
<p class="etat">{html.escape(etat_bot)}</p>
{contenu}
</main>
<script>
document.querySelectorAll(".graphe").forEach(function (g) {{
  var pts = JSON.parse(g.querySelector("script").textContent);
  var svg = g.querySelector("svg"), zone = g.querySelector(".zone"), repere = g.querySelector(".repere");
  var point = g.querySelector(".point"), bulle = g.querySelector(".bulle");
  function montrer(e) {{
    var r = svg.getBoundingClientRect(), x = (e.clientX - r.left) * 640 / r.width, i = 0;
    pts.forEach(function (p, k) {{ if (Math.abs(p.x - x) < Math.abs(pts[i].x - x)) i = k; }});
    var p = pts[i];
    repere.setAttribute("x1", p.x); repere.setAttribute("x2", p.x); repere.setAttribute("visibility", "visible");
    point.setAttribute("cx", p.x); point.setAttribute("cy", p.y); point.setAttribute("visibility", "visible");
    bulle.textContent = "";
    var v = document.createElement("strong"); v.textContent = p.valeur; bulle.appendChild(v);
    bulle.appendChild(document.createTextNode(p.date));
    bulle.hidden = false;
    var gauche = p.x * r.width / 640 + 10;
    bulle.style.left = Math.min(gauche, r.width - bulle.offsetWidth) + "px";
  }}
  function cacher() {{ repere.setAttribute("visibility", "hidden"); point.setAttribute("visibility", "hidden"); bulle.hidden = true; }}
  zone.addEventListener("pointermove", montrer); zone.addEventListener("pointerdown", montrer);
  zone.addEventListener("pointerleave", cacher);
}});
</script>
</body></html>"""
    with open(chemin_sortie, "w", encoding="utf-8") as f:
        f.write(page)
