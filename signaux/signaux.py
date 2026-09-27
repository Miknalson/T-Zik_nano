"""Signaux de trading quotidiens, avec un contrôle de fiabilité avant affichage.

Chaque règle est d'abord rejouée sur tout l'historique exactement comme tu la
suivrais (entrée à l'ouverture, stop-loss chez le courtier, frais et
financement compris), puis comparée à la même règle décalée dans le temps.
Un signal n'est affiché que si la règle bat nettement ce hasard ET reste
gagnante sur les deux moitiés de l'historique. Sinon : « pas de signal fiable ».

Usage :
    python signaux.py                     # données réelles (Yahoo Finance)
    python signaux.py --capital 2000 --risque 1
    python signaux.py --demo              # données simulées, sans Internet
"""
import argparse
import csv
import datetime as dt
import html
import os
import sys
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

MARCHES = [
    ("BTC-USD", "Bitcoin", "crypto"),
    ("ETH-USD", "Ethereum", "crypto"),
    ("XRP-USD", "XRP", "crypto"),
    ("NG=F", "Gaz naturel", "matiere"),
    ("CL=F", "Pétrole WTI", "matiere"),
    ("GC=F", "Or", "matiere"),
    ("^FCHI", "CAC 40", "indice"),
    ("^GSPC", "S&P 500", "indice"),
    ("EURUSD=X", "EUR/USD", "forex"),
    ("GBPUSD=X", "GBP/USD", "forex"),
]

# Coûts par trade en fraction du nominal. Crypto : mesuré sur Libertex (commission
# 0,10 % à l'ouverture + « ajustement de la marge » 0,14 %). Le reste et le
# financement overnight sont des valeurs prudentes de CFD grand public, à
# remplacer quand les coûts Libertex seront relevés.
FRAIS = {
    "crypto":  {"aller_retour": 0.0025, "financement_jour": 0.0005},
    "matiere": {"aller_retour": 0.003,  "financement_jour": 0.0002},
    "indice":  {"aller_retour": 0.0005, "financement_jour": 0.0002},
    "forex":   {"aller_retour": 0.0002, "financement_jour": 0.0001},
}

K_STOP = 2.0          # stop-loss à 2 × l'ATR (variation moyenne d'une séance)
P_MAX = 0.01          # probabilité max que le résultat soit dû au hasard
TRADES_MIN = 30       # en dessous, trop peu de trades pour conclure
DECALAGE_MIN = 20     # décalages trop proches de la vraie date exclus du test
NB_DECALAGES = 400    # nombre de versions « hasard » de chaque règle
BARRES_MIN = 400
DEBUT_SUIVI = pd.Timestamp("2026-09-28")  # début du test en conditions réelles (compte démo)

DOSSIER = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ indicateurs
def sma(s, n):
    return s.rolling(n).mean()


def rsi(s, n):
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    perte = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / perte)


def atr(df, n=14):
    c_prec = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - c_prec).abs(),
                    (df["Low"] - c_prec).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ------------------------------------------------------------------------ règles
# Chaque règle renvoie la position voulue à la clôture de chaque jour :
# +1 acheteur, -1 vendeur, 0 neutre. Elle n'est exécutée qu'à l'ouverture
# suivante (voir `executer`), donc aucune règle ne voit le futur.
def regle_tendance(df):
    c = df["Close"]
    m50, m200 = sma(c, 50), sma(c, 200)
    pos = pd.Series(0.0, index=df.index)
    pos[(c > m200) & (m50 > m200)] = 1
    pos[(c < m200) & (m50 < m200)] = -1
    return pos


def regle_cassure(df, entree=20, sortie=10):
    c = df["Close"].values
    haut_e = df["High"].rolling(entree).max().shift(1).values
    bas_e = df["Low"].rolling(entree).min().shift(1).values
    haut_s = df["High"].rolling(sortie).max().shift(1).values
    bas_s = df["Low"].rolling(sortie).min().shift(1).values
    pos, p = np.zeros(len(c)), 0
    for i in range(len(c)):
        if np.isnan(haut_e[i]):
            continue
        if (p == 1 and c[i] < bas_s[i]) or (p == -1 and c[i] > haut_s[i]):
            p = 0
        if p == 0:
            p = 1 if c[i] > haut_e[i] else -1 if c[i] < bas_e[i] else 0
        pos[i] = p
    return pd.Series(pos, index=df.index)


def regle_retour_moyenne(df):
    c = df["Close"].values
    r2 = rsi(df["Close"], 2).values
    m200 = sma(df["Close"], 200).values
    m5 = sma(df["Close"], 5).values
    pos, p = np.zeros(len(c)), 0
    for i in range(len(c)):
        if np.isnan(m200[i]):
            continue
        if (p == 1 and c[i] > m5[i]) or (p == -1 and c[i] < m5[i]):
            p = 0
        if p == 0:
            p = 1 if (r2[i] < 10 and c[i] > m200[i]) else -1 if (r2[i] > 90 and c[i] < m200[i]) else 0
        pos[i] = p
    return pd.Series(pos, index=df.index)


REGLES = {
    "Tendance (moyennes 50/200)": regle_tendance,
    "Cassure 20 jours": regle_cassure,
    "Retour à la moyenne (RSI 2)": regle_retour_moyenne,
}

# Une seule méthode par marché pour le test sur compte démo, fixée le 27/09/2026 :
# la plus probante parmi celles restées gagnantes sur les deux moitiés de
# l'historique (frais Libertex). Les marchés sans candidate ne sont pas suivis.
# Figé volontairement : changer de méthode au gré des résultats fausserait le test.
METHODE_SUIVIE = {
    "BTC-USD": "Cassure 20 jours",
    "ETH-USD": "Cassure 20 jours",
    "XRP-USD": "Cassure 20 jours",
    "^GSPC": "Retour à la moyenne (RSI 2)",
}


def suivie(r):
    return METHODE_SUIVIE.get(r["ticker"]) == r["regle"]


# ------------------------------------------------------------------- évaluation
def executer(df, voulu, frais, decalages=()):
    """Rejoue les trades exactement comme tu les passerais.

    - entrée à l'ouverture de la séance qui suit un NOUVEAU signal ;
    - stop-loss posé chez le courtier dès l'entrée, à K_STOP × ATR du prix
      d'entrée, déclenché dans la séance (au prix d'ouverture si le marché
      ouvre déjà au-delà du stop) ;
    - sortie à l'ouverture qui suit la fin du signal ;
    - après un stop, pas de nouvelle entrée avant un nouveau signal.

    Les versions décalées dans le temps (`decalages`) passent par la même
    mécanique : seul le moment des signaux change, ce qui sert de référence
    « hasard » pour juger la règle.
    """
    o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    a = atr(df).to_numpy(float)
    jours = df.index.to_series().diff().dt.days.fillna(1).to_numpy(float)
    v0 = voulu.to_numpy(float)
    V = np.vstack([v0] + [np.roll(v0, int(k)) for k in decalages])
    nb, n = V.shape
    demi = frais["aller_retour"] / 2
    financement = frais["financement_jour"]

    sens, stop, nb_entrees = np.zeros(nb), np.zeros(nb), np.zeros(nb, dtype=int)
    ret = np.zeros((nb, n))
    operations = []  # scénario réel uniquement : (séance, type, sens, prix)
    for t in range(1, n):
        prec = V[:, t - 1]
        avant = V[:, t - 2] if t >= 2 else np.zeros(nb)

        sortie = (sens != 0) & (prec != sens)
        ret[sortie, t] += sens[sortie] * (o[t] / c[t - 1] - 1) - demi
        if sortie[0]:
            operations.append((t, "sortie", sens[0], o[t]))
        sens[sortie] = 0

        entre = (sens == 0) & (prec != 0) & (prec != avant) & (not np.isnan(a[t - 1]))
        sens[entre] = prec[entre]
        stop[entre] = o[t] - sens[entre] * K_STOP * a[t - 1]
        ret[entre, t] -= demi
        nb_entrees += entre
        if entre[0]:
            operations.append((t, "entree", sens[0], o[t]))

        tenu = sens != 0
        base = np.where(entre, o[t], c[t - 1])
        touche = tenu & (((sens > 0) & (l[t] <= stop)) | ((sens < 0) & (h[t] >= stop)))
        prix_stop = np.where(sens > 0, np.minimum(o[t], stop), np.maximum(o[t], stop))
        fin_seance = np.where(touche, prix_stop, c[t])
        ret[tenu, t] += sens[tenu] * (fin_seance[tenu] / base[tenu] - 1)
        ret[tenu & ~entre, t] -= financement * jours[t]
        ret[touche, t] -= demi
        if touche[0]:
            operations.append((t, "stop", sens[0], prix_stop[0]))
        sens[touche] = 0

    return {"net": ret[0], "hasard": ret[1:].sum(axis=1), "nb_trades": int(nb_entrees[0]),
            "operations": operations, "sens": float(sens[0]), "stop": float(stop[0])}


def evaluer(df, voulu, frais, nb_decalages=NB_DECALAGES):
    n = len(df)
    decalages = np.unique(np.linspace(DECALAGE_MIN, n - DECALAGE_MIN, nb_decalages).astype(int))
    x = executer(df, voulu, frais, decalages)
    net = x["net"]
    pval = (1 + np.sum(x["hasard"] >= net.sum() - 1e-12)) / (1 + len(x["hasard"]))
    annees = max((df.index[-1] - df.index[0]).days / 365.25, 1e-9)
    moitie = n // 2

    raisons = []
    if x["nb_trades"] < TRADES_MIN:
        raisons.append(f"trop peu de trades ({x['nb_trades']} < {TRADES_MIN})")
    if pval >= P_MAX:
        raisons.append(f"pas mieux que le hasard (p = {pval:.2f})")
    if net[:moitie].sum() <= 0 or net[moitie:].sum() <= 0:
        raisons.append("perdant sur une des deux moitiés de l'historique")

    return {"nb_trades": x["nb_trades"], "rendement_annuel": net.sum() / annees, "p": pval,
            "valide": not raisons, "raisons": raisons, "execution": x}


def conseil_du_jour(df, voulu, execution, capital, risque_pct):
    """Traduit l'état de la règle à la dernière clôture en consigne pour demain."""
    v, v_prec = voulu.iloc[-1], voulu.iloc[-2]
    ops = execution["operations"]
    derniere = len(df) - 1
    entrees = [op for op in ops if op[1] == "entree"]
    cloture = float(df["Close"].iloc[-1])
    distance = K_STOP * float(atr(df).iloc[-1])
    nominal = capital * risque_pct / 100 * cloture / distance if distance > 0 else 0.0
    nouveau = v != 0 and v != v_prec

    if execution["sens"] != 0:
        action = "EN COURS" if v == execution["sens"] else ("INVERSER" if nouveau else "SORTIR")
    elif nouveau:
        action = "ENTRER"
    elif ops and ops[-1][0] == derniere and ops[-1][1] == "stop":
        action = "STOP TOUCHÉ"
    else:
        action = "RIEN"

    return {
        "action": action,
        "orientation": int(v),
        "sens": int(v) if action in ("ENTRER", "INVERSER") else int(execution["sens"]),
        "position_sens": int(execution["sens"]),
        "depuis": df.index[entrees[-1][0]] if entrees else None,
        "prix_entree": entrees[-1][3] if entrees else None,
        "stop_position": execution["stop"],
        "cloture": cloture,
        "stop_pct": distance / cloture,
        "stop_estime": cloture - v * distance,
        "nominal": nominal,
        "levier": nominal / capital if capital else 0.0,
    }


def suivi_depuis(df, execution, frais, debut=DEBUT_SUIVI):
    """Résultat des trades ouverts depuis le début du test sur compte démo.

    Les positions ouvertes avant `debut` sont ignorées : la consigne est de ne
    jamais entrer en cours de route, donc tu ne les aurais pas. Un trade encore
    ouvert est évalué au dernier cours de clôture.
    """
    ops = execution["operations"]
    trades, total = 0, 0.0
    for i, (t, genre, sens, prix) in enumerate(ops):
        if genre != "entree" or df.index[t] < debut:
            continue
        fin = next((op for op in ops[i + 1:] if op[1] in ("sortie", "stop")), None)
        t_fin, prix_fin = (fin[0], fin[3]) if fin else (len(df) - 1, float(df["Close"].iloc[-1]))
        couts = (frais["aller_retour"] * (1 if fin else 0.5)
                 + frais["financement_jour"] * (df.index[t_fin] - df.index[t]).days)
        total += sens * (prix_fin / prix - 1) - couts
        trades += 1
    return {"trades": trades, "resultat": total, "commence": bool(df.index[-1] >= debut)}


# ----------------------------------------------------------------------- données
def telecharger(ticker, annees, essais=3):
    import yfinance as yf
    for essai in range(essais):
        try:
            df = yf.download(ticker, period=f"{annees}y", interval="1d",
                             auto_adjust=True, progress=False)
            if not df.empty:
                break
        except Exception:
            if essai == essais - 1:
                raise
        # Yahoo limite parfois les serveurs cloud : on patiente avant de réessayer.
        time.sleep(5 * (essai + 1))
    if df.empty:
        raise ValueError("aucune donnée renvoyée par Yahoo")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def simuler(ticker, jours=2500):
    """Marche aléatoire sans aucun avantage exploitable : sert de test à vide."""
    rng = np.random.default_rng(abs(hash(ticker)) % 2**32)
    r = rng.normal(0, 0.015, jours)
    close = 100 * np.exp(np.cumsum(r))
    ouverture = close * np.exp(rng.normal(0, 0.003, jours))
    ecart = np.abs(rng.normal(0, 0.01, jours)) * close
    index = pd.bdate_range(end=dt.date.today(), periods=jours)
    return pd.DataFrame({"Open": ouverture, "Close": close,
                         "High": np.maximum(ouverture, close) + ecart,
                         "Low": np.minimum(ouverture, close) - ecart}, index=index)


def seances_terminees(df, classe):
    # La séance du jour n'est jamais complète, et Yahoo invente parfois des
    # séances le week-end pour le forex et les contrats à terme.
    aujourd_hui = pd.Timestamp(dt.datetime.now(dt.timezone.utc).date())
    df = df[df.index < aujourd_hui]
    if classe != "crypto":
        df = df[df.index.dayofweek < 5]
    return df


# ------------------------------------------------------------------------ sortie
def eur(x):
    return f"{x:,.0f} €".replace(",", " ")


def prix(x):
    # 73 970 plutôt que 7.397e+04 ; 1.1682 ou 2.874 gardent leurs décimales.
    return f"{x:,.0f}".replace(",", " ") if abs(x) >= 1000 else f"{x:.5g}"


SENS = {1: "ACHAT", -1: "VENTE"}
ORIENTATION = {1: ("↑ HAUSSE", "achat"), -1: ("↓ BAISSE", "vente"), 0: ("→ NEUTRE", "gris")}


def instructions(c):
    """Titre et consignes d'exécution détaillées correspondant à l'état de la règle."""
    taille = f"Taille max : {eur(c['nominal'])} de position (levier {c['levier']:.1f})."
    ouverture = [
        f"Stop-loss : à {c['stop_pct']:.1%} de ton prix d'entrée (≈ {prix(c['stop_estime'])}), "
        "à poser chez ton courtier dès l'entrée.",
        "Take-profit : aucun. Sors quand cette page affiche SORTIR.",
        taille,
    ]
    depuis = f"{c['depuis']:%d/%m/%Y}" if c["depuis"] is not None else "?"
    if c["action"] == "ENTRER":
        return f"ENTRER — {SENS[c['sens']]}", ["Quand : à l'ouverture de la prochaine séance."] + ouverture
    if c["action"] == "INVERSER":
        return (f"INVERSER → {SENS[c['sens']]}",
                [f"À l'ouverture : ferme ta position {SENS[c['position_sens']]} et entre en "
                 f"{SENS[c['sens']]}."] + ouverture)
    if c["action"] == "SORTIR":
        return "SORTIR", [f"Ferme la position {SENS[c['position_sens']]} ouverte le {depuis}, "
                          "à l'ouverture de la prochaine séance."]
    if c["action"] == "EN COURS":
        return (f"EN COURS — {SENS[c['sens']]} depuis le {depuis}",
                [f"Entrée à {prix(c['prix_entree'])}, stop-loss à {prix(c['stop_position'])}.",
                 "Pas encore dedans ? N'entre pas en cours de route : attends le prochain ENTRER."])
    if c["action"] == "STOP TOUCHÉ":
        return "STOP TOUCHÉ", ["La position a été fermée par le stop-loss. Attends le prochain ENTRER."]
    return "Rien à faire", ["Pas de position, pas de nouveau signal."]


def ligne_demo(c):
    """Consigne en une ligne, pour tester une règle non validée sur le compte démo."""
    if c["action"] in ("ENTRER", "INVERSER"):
        verbe = "ENTRER en" if c["action"] == "ENTRER" else "INVERSER →"
        return (f"Démo : {verbe} {SENS[c['sens']]} à l'ouverture, stop-loss à {c['stop_pct']:.1%}, "
                f"taille max {eur(c['nominal'])}.")
    if c["action"] == "SORTIR":
        return "Démo : SORTIR à l'ouverture, si tu as pris cette position."
    if c["action"] == "EN COURS":
        return (f"Démo : {SENS[c['sens']]} en cours depuis le {c['depuis']:%d/%m/%Y}, "
                f"stop-loss à {prix(c['stop_position'])}. N'entre pas en cours de route.")
    if c["action"] == "STOP TOUCHÉ":
        return "Démo : stop touché, attends le prochain ENTRER."
    return "Démo : rien à faire."


def consigne(r):
    """Renvoie (titre, lignes de détail, style) pour une règle et un marché."""
    if r["erreur"]:
        return "Données indisponibles", [r["erreur"]], "gris"
    e, c, s = r["eval"], r["conseil"], r["suivi"]
    suivi = (f"Suivi démo depuis le {DEBUT_SUIVI:%d/%m} : {s['trades']} trade(s), "
             f"résultat {s['resultat']:+.1%}" if s["commence"]
             else f"Suivi démo : commence le {DEBUT_SUIVI:%d/%m/%Y}")
    if not e["valide"]:
        return "Pas de signal fiable", [", ".join(e["raisons"]), ligne_demo(c), suivi], "gris"

    titre, lignes = instructions(c)
    historique = f"Historique : {e['rendement_annuel']:+.1%}/an, {e['nb_trades']} trades, p = {e['p']:.3f}"
    style = "sortir" if c["action"] == "SORTIR" else {1: "achat", -1: "vente", 0: "gris"}[c["sens"]]
    if c["action"] == "STOP TOUCHÉ":
        style = "gris"
    return titre, lignes + [historique, suivi], style


def afficher_console(resultats, nb_tests):
    valides = [r for r in resultats if r["eval"] and r["eval"]["valide"]]
    print()
    for r in resultats:
        titre, lignes, _ = consigne(r)
        orientation = f" [{ORIENTATION[r['conseil']['orientation']][0]}]" if r["conseil"] else ""
        print(f"{r['nom']:<13} {r['regle']:<30} {titre}{orientation}")
        for ligne in lignes:
            print(f"{'':<45}{ligne}")
    print(f"\n{len(valides)} règle(s) validée(s) sur {nb_tests} testées. "
          f"Par pur hasard, on en attendrait environ {nb_tests * P_MAX:.1f}.")


def priorite(r):
    """Les cartes qui demandent d'agir aujourd'hui passent en tête de page."""
    if r["erreur"]:
        return 5
    valide, action = r["eval"]["valide"], r["conseil"]["action"]
    if action in ("ENTRER", "INVERSER", "SORTIR"):
        return 0 if valide else 1
    if action == "EN COURS":
        return 2 if valide else 3
    return 4


def carte_html(r):
    titre, lignes, style = consigne(r)
    detail = "<br>".join(html.escape(ligne) for ligne in lignes)
    badge = ""
    if r["conseil"]:
        texte, couleur = ORIENTATION[r["conseil"]["orientation"]]
        badge = f'<b class="badge {couleur}">{texte}</b>'
    etoile = '<div class="suivie">★ Méthode suivie</div>' if suivie(r) else ""
    return (f'<div class="carte {style}">{etoile}<div class="marche">{html.escape(r["nom"])}'
            f'<span>{html.escape(r["regle"])}</span>{badge}</div>'
            f'<div class="statut">{html.escape(titre)}</div>'
            f'<div class="detail">{detail}</div></div>')


def ecrire_html(resultats, chemin, capital, risque, demo):
    suivies = sorted((r for r in resultats if suivie(r)), key=priorite)
    autres = sorted((r for r in resultats if not suivie(r)), key=priorite)
    a_faire = sum(priorite(r) <= 1 for r in suivies)
    cartes = ([carte_html(r) for r in suivies]
              + ['<h2>Autres méthodes (pour information)</h2>']
              + [carte_html(r) for r in autres])

    avert = '<p class="demo">MODE DÉMO — données simulées, aucun signal réel.</p>' if demo else ""
    maintenant = dt.datetime.now(ZoneInfo("Europe/Paris"))
    dates = [r["date_cloture"] for r in resultats if r["date_cloture"] is not None]
    cloture = f" · clôtures du {max(dates):%d/%m/%Y}" if dates else ""
    compte = f" · capital {eur(capital)}"
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Signaux du jour</title>
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Signaux">
<link rel="apple-touch-icon" href="icone.png">
<style>
:root{{--fond:#f6f6f4;--carte:#fff;--texte:#1d1d1b;--doux:#6b6b66;--achat:#1f7a4d;--vente:#b3261e;--sortir:#9a6700;--bord:#e2e2dd}}
@media (prefers-color-scheme:dark){{:root{{--fond:#141413;--carte:#1f1f1d;--texte:#ededea;--doux:#9b9b95;--achat:#4fbf85;--vente:#f2766c;--sortir:#e3b341;--bord:#33332f}}}}
body{{margin:0;background:var(--fond);color:var(--texte);font:15px/1.45 -apple-system,system-ui,sans-serif}}
main{{max-width:640px;margin:0 auto;padding:16px}}
h1{{font-size:20px;margin:4px 0}} .sous{{color:var(--doux);font-size:13px;margin:0 0 14px}}
.carte{{background:var(--carte);border:1px solid var(--bord);border-left:4px solid var(--bord);border-radius:8px;padding:10px 12px;margin:8px 0}}
.carte.achat{{border-left-color:var(--achat)}} .carte.vente{{border-left-color:var(--vente)}} .carte.sortir{{border-left-color:var(--sortir)}}
.marche{{font-weight:600}} .marche span{{font-weight:400;color:var(--doux);font-size:13px;margin-left:6px}}
.achat .statut{{color:var(--achat);font-weight:600}} .vente .statut{{color:var(--vente);font-weight:600}} .sortir .statut{{color:var(--sortir);font-weight:600}}
.gris .statut{{color:var(--doux)}} .detail{{color:var(--doux);font-size:13px;margin-top:2px}}
.marche{{display:flex;align-items:baseline;flex-wrap:wrap;gap:0 6px}} .marche span{{margin-left:0!important;flex:1}}
.badge{{font-size:12px;font-weight:700;white-space:nowrap}} .badge.achat{{color:var(--achat)}} .badge.vente{{color:var(--vente)}} .badge.gris{{color:var(--doux)}}
.demo{{background:#fff3cd;color:#664d03;padding:8px 10px;border-radius:6px}}
.note{{color:var(--doux);font-size:12px;margin-top:18px}} .resume{{font-weight:600;margin:0 0 6px}}
.suivie{{font-size:12px;font-weight:700;color:var(--sortir);margin-bottom:2px}}
h2{{font-size:15px;color:var(--doux);margin:22px 0 4px}}
</style></head><body><main>
<h1>Signaux du jour</h1>
<p class="sous">Mis à jour le {maintenant:%d/%m/%Y à %H:%M}{cloture}{compte} · risque {risque} % par trade</p>
{avert}<p class="resume">À faire aujourd'hui : {a_faire} consigne(s) sur les méthodes suivies (★).</p>
{''.join(cartes)}
<p class="note">Un signal validé a battu le hasard sur l'historique, en simulant exactement ces
consignes : entrée à l'ouverture, stop-loss chez le courtier, frais compris. Cela ne garantit pas
l'avenir. Entrer plus tard que l'ouverture change le résultat. La taille max est calculée pour qu'un
stop touché coûte {risque} % du capital.<br><br>Les lignes « Démo » des règles non validées servent
uniquement à les tester sur un compte démo : elles n'ont pas battu le hasard. Le suivi démo
compte ce qu'aurait donné chaque règle depuis le {DEBUT_SUIVI:%d/%m/%Y}, en % de la position.</p>
</main></body></html>"""
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(page)


def journaliser(resultats, chemin):
    nouveau = not os.path.exists(chemin)
    deja = set()
    if not nouveau:
        with open(chemin, newline="", encoding="utf-8") as f:
            deja = {(l["date_cloture"], l["ticker"], l["regle"]) for l in csv.DictReader(f, delimiter=";")}
    with open(chemin, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if nouveau:
            w.writerow(["date_execution", "date_cloture", "ticker", "regle", "valide", "signal", "cloture", "stop"])
        for r in resultats:
            if r["erreur"] or (f"{r['date_cloture']:%Y-%m-%d}", r["ticker"], r["regle"]) in deja:
                continue
            c = r["conseil"]
            stop = {"ENTRER": c["stop_estime"], "INVERSER": c["stop_estime"],
                    "EN COURS": c["stop_position"]}.get(c["action"])
            w.writerow([dt.date.today().isoformat(), f"{r['date_cloture']:%Y-%m-%d}",
                        r["ticker"], r["regle"], int(r["eval"]["valide"]),
                        f"{c['action']} {SENS.get(c['sens'], '')}".strip(),
                        f"{c['cloture']:.6g}", f"{stop:.6g}" if stop is not None else ""])


MULTIPLICATEUR = 2  # plafond européen sur la crypto ; le montant investi reste ≫ la perte au stop
# Nom de l'instrument tel qu'il apparaît dans Libertex.
NOM_LIBERTEX = {"BTC-USD": "BTCUSD", "ETH-USD": "ETHUSD", "XRP-USD": "XRPUSD", "^GSPC": "US SPX 500 Cash"}
FERMER = "onglet « Actif » → ta position {nom} → « Fermer »"


def ticket_libertex(instrument, c):
    """Les cases de l'écran d'ordre Libertex, dans l'ordre où elles apparaissent."""
    montant = int(c["nominal"] / MULTIPLICATEUR)
    perte = montant * MULTIPLICATEUR * c["stop_pct"]
    return (f"Instrument : {instrument}\n"
            f"Direction : {'Acheter' if c['sens'] > 0 else 'Vendre'}\n"
            f"Montant : {eur(montant)}\n"
            f"Multiplicateur : ×{MULTIPLICATEUR}\n"
            "Take Profit : laisser vide\n"
            f"Stop Loss : {prix(c['stop_estime'])} (≈ −{perte:.0f} € si touché)\n"
            f"Prix de référence : {prix(c['cloture'])}")


def notifications(resultats):
    """Messages à envoyer sur le téléphone : uniquement ce qui demande d'agir."""
    messages = []
    for r in resultats:
        if r["erreur"] or not suivie(r):
            continue
        c = r["conseil"]
        if c["action"] in ("ENTRER", "INVERSER"):
            verbe = "ACHÈTE" if c["sens"] > 0 else "VENDS"
            instrument = NOM_LIBERTEX.get(r["ticker"], r["nom"])
            etapes = ticket_libertex(instrument, c) + "\nSortie : attends la notification FERME."
            if c["action"] == "INVERSER":
                etapes = (f"1) Ferme ta position {SENS[c['position_sens']]} : "
                          f"{FERMER.format(nom=NOM_LIBERTEX.get(r['ticker'], r['nom']))}\n2) Nouvel ordre :\n{etapes}")
            messages.append({
                "title": f"{r['nom']} : {verbe} (démo)",
                "message": etapes,
                "priority": 4,
                "tags": ["chart_with_upwards_trend" if c["sens"] > 0 else "chart_with_downwards_trend"],
            })
        elif c["action"] == "SORTIR":
            messages.append({
                "title": f"{r['nom']} : FERME (démo)",
                "message": f"Ferme ta position {SENS[c['position_sens']]} : {FERMER.format(nom=NOM_LIBERTEX.get(r['ticker'], r['nom']))}",
                "priority": 4,
                "tags": ["warning"],
            })
        elif c["action"] == "STOP TOUCHÉ":
            messages.append({
                "title": f"{r['nom']} : stop touché (démo)",
                "message": "Ta position a été fermée par le stop-loss. Rien à faire.",
                "priority": 3,
                "tags": ["information_source"],
            })
    return messages


def envoyer(sujet, message):
    import json
    import urllib.request
    corps = json.dumps({"topic": sujet, "click": "https://miknalson.github.io/T-Zik_nano/",
                        **message}).encode("utf-8")
    requete = urllib.request.Request("https://ntfy.sh/", data=corps,
                                     headers={"Content-Type": "application/json"})
    urllib.request.urlopen(requete, timeout=20).read()


# -------------------------------------------------------------------------- main
def analyser(demo, annees, capital, risque):
    resultats = []
    for ticker, nom, classe in MARCHES:
        try:
            df = simuler(ticker) if demo else telecharger(ticker, annees)
            df = seances_terminees(df, classe)
            if len(df) < BARRES_MIN:
                raise ValueError(f"historique trop court ({len(df)} jours)")
            erreur = None
        except Exception as exc:  # une source en panne ne doit pas bloquer les autres
            df, erreur = None, str(exc) or exc.__class__.__name__
        for nom_regle, regle in REGLES.items():
            base = {"ticker": ticker, "nom": nom, "regle": nom_regle, "erreur": erreur,
                    "eval": None, "conseil": None, "suivi": None, "date_cloture": None}
            if df is not None:
                voulu = regle(df)
                base["eval"] = evaluer(df, voulu, FRAIS[classe])
                base["conseil"] = conseil_du_jour(df, voulu, base["eval"]["execution"], capital, risque)
                base["suivi"] = suivi_depuis(df, base["eval"]["execution"], FRAIS[classe])
                base["date_cloture"] = df.index[-1]
            resultats.append(base)
    return resultats


def main():
    ap = argparse.ArgumentParser(description="Signaux quotidiens avec contrôle de fiabilité.")
    ap.add_argument("--capital", type=float, default=1000, help="capital du compte en € (défaut 1000)")
    ap.add_argument("--risque", type=float, default=1.0, help="%% du capital risqué par trade (défaut 1)")
    ap.add_argument("--annees", type=int, default=10, help="années d'historique (défaut 10)")
    ap.add_argument("--demo", action="store_true", help="données simulées, sans Internet")
    ap.add_argument("--sortie", default=os.path.join(DOSSIER, "rapport_signaux.html"),
                    help="chemin du rapport HTML")
    ap.add_argument("--notif-test", action="store_true",
                    help="envoie une notification de test (sujet ntfy dans NTFY_TOPIC)")
    args = ap.parse_args()
    sujet = os.environ.get("NTFY_TOPIC", "").strip()

    resultats = analyser(args.demo, args.annees, args.capital, args.risque)
    if all(r["erreur"] for r in resultats):
        sys.exit("Aucune donnée récupérée. Vérifie ta connexion Internet.")

    nb_tests = sum(1 for r in resultats if not r["erreur"])
    afficher_console(resultats, nb_tests)
    rapport = args.sortie
    os.makedirs(os.path.dirname(os.path.abspath(rapport)), exist_ok=True)
    ecrire_html(resultats, rapport, args.capital, args.risque, args.demo)
    if not args.demo:
        journaliser(resultats, os.path.join(DOSSIER, "journal_signaux.csv"))
    print(f"Rapport pour le téléphone : {rapport}")

    messages = [] if args.demo else notifications(resultats)
    if args.notif_test:
        exemple = {"sens": 1, "nominal": 150.0, "stop_pct": 0.066, "stop_estime": 81745, "cloture": 84915}
        messages.insert(0, {"title": "EXEMPLE — ne passe pas cet ordre",
                            "message": "Voici à quoi ressemblera une consigne :\n" + ticket_libertex("BTCUSD", exemple),
                            "priority": 3, "tags": ["white_check_mark"]})
    if messages and not sujet:
        print("Notifications non envoyées : NTFY_TOPIC n'est pas défini.")
    for m in messages if sujet else []:
        try:
            envoyer(sujet, m)
            print(f"Notification envoyée : {m['title']}")
        except Exception as exc:  # la page doit être publiée même si ntfy est en panne
            print(f"::warning::Notification non envoyée ({m['title']}) : {exc}")


if __name__ == "__main__":
    main()
