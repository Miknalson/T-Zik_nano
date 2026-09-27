"""Signaux de trading quotidiens, avec un contrôle de fiabilité avant affichage.

Chaque règle est d'abord testée sur tout l'historique, frais et financement
compris, puis comparée à la même règle décalée dans le temps (même exposition,
mêmes durées de position, mais au hasard des dates). Un signal n'est affiché
que si la règle bat nettement ce hasard ET reste gagnante sur les deux moitiés
de l'historique. Sinon : « pas de signal fiable ».

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

# Coûts d'un CFD grand public, en fraction du nominal. À remplacer par ceux de
# ton courtier (spread affiché + frais de financement overnight).
FRAIS = {
    "crypto":  {"aller_retour": 0.006,  "financement_jour": 0.0005},
    "matiere": {"aller_retour": 0.003,  "financement_jour": 0.0002},
    "indice":  {"aller_retour": 0.0005, "financement_jour": 0.0002},
    "forex":   {"aller_retour": 0.0002, "financement_jour": 0.0001},
}

P_MAX = 0.01          # probabilité max que le résultat soit dû au hasard
TRADES_MIN = 30       # en dessous, trop peu de trades pour conclure
DECALAGE_MIN = 20     # décalages trop proches de la vraie date exclus du test
BARRES_MIN = 400

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
# +1 acheteur, -1 vendeur, 0 neutre. Elle n'est appliquée qu'à la séance
# suivante (voir `evaluer`), donc aucune règle ne voit le futur.
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


# ------------------------------------------------------------------- évaluation
def p_valeur(p, r):
    """Part des décalages temporels de la position qui font au moins aussi bien.

    Décaler la série de positions garde exactement l'exposition, le nombre et
    la durée des trades : seul le choix des dates change. On mesure donc si le
    timing de la règle apporte quelque chose, au-delà d'être simplement exposé.
    """
    n = len(p)
    corr = np.fft.irfft(np.conj(np.fft.rfft(p)) * np.fft.rfft(r), n)
    nul = corr[DECALAGE_MIN:n - DECALAGE_MIN]
    return (1 + np.sum(nul >= corr[0] - 1e-12)) / (1 + len(nul))


def evaluer(df, pos, frais):
    r = df["Close"].pct_change().fillna(0).values
    p = pos.shift(1).fillna(0).values
    jours = df.index.to_series().diff().dt.days.fillna(1).values
    rotation = np.abs(np.diff(p, prepend=0))
    brut = p * r
    net = brut - rotation * frais["aller_retour"] / 2 - np.abs(p) * jours * frais["financement_jour"]

    precedente = np.concatenate([[0], p[:-1]])
    nb_trades = int(np.sum((p != 0) & (p != precedente)))
    annees = max((df.index[-1] - df.index[0]).days / 365.25, 1e-9)
    moitie = len(net) // 2
    courbe = np.cumsum(net)
    pval = p_valeur(p, r)

    raisons = []
    if nb_trades < TRADES_MIN:
        raisons.append(f"trop peu de trades ({nb_trades} < {TRADES_MIN})")
    if pval >= P_MAX:
        raisons.append(f"pas mieux que le hasard (p = {pval:.2f})")
    if net[:moitie].sum() <= 0 or net[moitie:].sum() <= 0:
        raisons.append("perdant sur une des deux moitiés de l'historique")

    return {
        "nb_trades": nb_trades,
        "rendement_annuel": net.sum() / annees,
        "exposition": float(np.mean(p != 0)),
        "perte_max": float(np.max(np.maximum.accumulate(courbe) - courbe)) if len(courbe) else 0.0,
        "p": pval,
        "valide": not raisons,
        "raisons": raisons,
    }


def signal_du_jour(df, pos, capital, risque_pct):
    actuelle = pos.iloc[-1]
    changements = pos.index[pos.ne(pos.shift(1))]
    depuis = changements[-1] if len(changements) else pos.index[0]
    cloture = float(df["Close"].iloc[-1])
    a = float(atr(df).iloc[-1])
    distance = 2 * a / cloture
    nominal = capital * risque_pct / 100 / distance if distance > 0 else 0.0
    return {
        "sens": {1: "ACHAT", -1: "VENTE", 0: "NEUTRE"}[int(actuelle)],
        "nouveau": depuis == pos.index[-1] and actuelle != 0,
        "depuis": depuis,
        "cloture": cloture,
        "stop": cloture - 2 * a if actuelle > 0 else cloture + 2 * a,
        "nominal": nominal,
        "levier": nominal / capital if capital else 0.0,
    }


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


def retirer_barre_en_cours(df, classe):
    # Une crypto cote 24h/24 : la barre du jour n'est complète qu'à minuit UTC.
    if classe == "crypto":
        aujourd_hui = pd.Timestamp(dt.datetime.now(dt.timezone.utc).date())
        df = df[df.index < aujourd_hui]
    return df


# ------------------------------------------------------------------------ sortie
def eur(x):
    return f"{x:,.0f} €".replace(",", " ")


def afficher_console(resultats, nb_tests):
    valides = [r for r in resultats if r["eval"] and r["eval"]["valide"]]
    print()
    for r in resultats:
        tete = f"{r['nom']:<13} {r['regle']:<30}"
        if r["erreur"]:
            print(f"{tete} ✗ {r['erreur']}")
        elif not r["eval"]["valide"]:
            print(f"{tete} — pas de signal fiable : {', '.join(r['eval']['raisons'])}")
        else:
            s, e = r["signal"], r["eval"]
            neuf = " (NOUVEAU)" if s["nouveau"] else f" (depuis le {s['depuis']:%d/%m/%Y})"
            print(f"{tete} ✓ {s['sens']}{neuf}")
            if s["sens"] != "NEUTRE":
                print(f"{'':<45}stop {s['stop']:.4g}  |  nominal max {eur(s['nominal'])} "
                      f"(levier {s['levier']:.1f})  |  historique {e['rendement_annuel']:+.1%}/an, "
                      f"{e['nb_trades']} trades, p = {e['p']:.3f}")
    print(f"\n{len(valides)} règle(s) validée(s) sur {nb_tests} testées. "
          f"Par pur hasard, on en attendrait environ {nb_tests * P_MAX:.1f}.")


def ecrire_html(resultats, chemin, capital, risque, demo, public=False):
    lignes = []
    for r in resultats:
        if r["erreur"]:
            statut, detail, classe = "Données indisponibles", html.escape(r["erreur"]), "gris"
        elif not r["eval"]["valide"]:
            statut, classe = "Pas de signal fiable", "gris"
            detail = html.escape(", ".join(r["eval"]["raisons"]))
        else:
            s, e = r["signal"], r["eval"]
            classe = {"ACHAT": "achat", "VENTE": "vente", "NEUTRE": "gris"}[s["sens"]]
            statut = s["sens"] + (" — nouveau" if s["nouveau"] else f" — depuis le {s['depuis']:%d/%m/%Y}")
            detail = (f"Historique : {e['rendement_annuel']:+.1%}/an, {e['nb_trades']} trades, "
                      f"p = {e['p']:.3f}")
            if s["sens"] != "NEUTRE":
                taille = (f"position max {s['levier']:.2f} × ton capital" if public
                          else f"nominal max {eur(s['nominal'])} (levier {s['levier']:.1f})")
                detail = f"Clôture {s['cloture']:.4g} · stop {s['stop']:.4g} · {taille}<br>" + detail
        lignes.append(f'<div class="carte {classe}"><div class="marche">{html.escape(r["nom"])}'
                      f'<span>{html.escape(r["regle"])}</span></div>'
                      f'<div class="statut">{html.escape(statut)}</div>'
                      f'<div class="detail">{detail}</div></div>')

    avert = '<p class="demo">MODE DÉMO — données simulées, aucun signal réel.</p>' if demo else ""
    maintenant = dt.datetime.now(ZoneInfo("Europe/Paris"))
    dates = [r["date_cloture"] for r in resultats if r["date_cloture"] is not None]
    cloture = f" · clôtures du {max(dates):%d/%m/%Y}" if dates else ""
    compte = "" if public else f" · capital {eur(capital)}"
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Signaux du jour</title>
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Signaux">
<link rel="apple-touch-icon" href="icone.png">
<style>
:root{{--fond:#f6f6f4;--carte:#fff;--texte:#1d1d1b;--doux:#6b6b66;--achat:#1f7a4d;--vente:#b3261e;--bord:#e2e2dd}}
@media (prefers-color-scheme:dark){{:root{{--fond:#141413;--carte:#1f1f1d;--texte:#ededea;--doux:#9b9b95;--achat:#4fbf85;--vente:#f2766c;--bord:#33332f}}}}
body{{margin:0;background:var(--fond);color:var(--texte);font:15px/1.45 -apple-system,system-ui,sans-serif}}
main{{max-width:640px;margin:0 auto;padding:16px}}
h1{{font-size:20px;margin:4px 0}} .sous{{color:var(--doux);font-size:13px;margin:0 0 14px}}
.carte{{background:var(--carte);border:1px solid var(--bord);border-left:4px solid var(--bord);border-radius:8px;padding:10px 12px;margin:8px 0}}
.carte.achat{{border-left-color:var(--achat)}} .carte.vente{{border-left-color:var(--vente)}}
.marche{{font-weight:600}} .marche span{{font-weight:400;color:var(--doux);font-size:13px;margin-left:6px}}
.achat .statut{{color:var(--achat);font-weight:600}} .vente .statut{{color:var(--vente);font-weight:600}}
.gris .statut{{color:var(--doux)}} .detail{{color:var(--doux);font-size:13px;margin-top:2px}}
.demo{{background:#fff3cd;color:#664d03;padding:8px 10px;border-radius:6px}}
.note{{color:var(--doux);font-size:12px;margin-top:18px}}
</style></head><body><main>
<h1>Signaux du jour</h1>
<p class="sous">Mis à jour le {maintenant:%d/%m/%Y à %H:%M}{cloture}{compte} · risque {risque} % par trade</p>
{avert}{''.join(lignes)}
<p class="note">Un signal validé a battu le hasard sur l'historique, frais compris. Cela ne garantit
pas l'avenir. La taille max est calculée pour qu'un stop touché coûte {risque} % du capital.</p>
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
            s = r["signal"]
            w.writerow([dt.date.today().isoformat(), f"{r['date_cloture']:%Y-%m-%d}",
                        r["ticker"], r["regle"], int(r["eval"]["valide"]), s["sens"],
                        f"{s['cloture']:.6g}", f"{s['stop']:.6g}" if s["sens"] != "NEUTRE" else ""])


# -------------------------------------------------------------------------- main
def analyser(demo, annees, capital, risque):
    resultats = []
    for ticker, nom, classe in MARCHES:
        try:
            df = simuler(ticker) if demo else telecharger(ticker, annees)
            df = retirer_barre_en_cours(df, classe)
            if len(df) < BARRES_MIN:
                raise ValueError(f"historique trop court ({len(df)} jours)")
            erreur = None
        except Exception as exc:  # une source en panne ne doit pas bloquer les autres
            df, erreur = None, str(exc) or exc.__class__.__name__
        for nom_regle, regle in REGLES.items():
            base = {"ticker": ticker, "nom": nom, "regle": nom_regle, "erreur": erreur,
                    "eval": None, "signal": None, "date_cloture": None}
            if df is not None:
                pos = regle(df)
                base["eval"] = evaluer(df, pos, FRAIS[classe])
                base["signal"] = signal_du_jour(df, pos, capital, risque)
                base["date_cloture"] = df.index[-1]
            resultats.append(base)
    return resultats


def main():
    ap = argparse.ArgumentParser(description="Signaux quotidiens avec contrôle de fiabilité.")
    ap.add_argument("--capital", type=float, default=1000, help="capital du compte en € (défaut 1000)")
    ap.add_argument("--risque", type=float, default=1.0, help="%% du capital risqué par trade (défaut 1)")
    ap.add_argument("--annees", type=int, default=10, help="années d'historique (défaut 10)")
    ap.add_argument("--demo", action="store_true", help="données simulées, sans Internet")
    ap.add_argument("--public", action="store_true",
                    help="page publiable : capital masqué, tailles en multiple du capital")
    ap.add_argument("--sortie", default=os.path.join(DOSSIER, "rapport_signaux.html"),
                    help="chemin du rapport HTML")
    args = ap.parse_args()

    resultats = analyser(args.demo, args.annees, args.capital, args.risque)
    if all(r["erreur"] for r in resultats):
        sys.exit("Aucune donnée récupérée. Vérifie ta connexion Internet.")

    nb_tests = sum(1 for r in resultats if not r["erreur"])
    afficher_console(resultats, nb_tests)
    rapport = args.sortie
    os.makedirs(os.path.dirname(os.path.abspath(rapport)), exist_ok=True)
    ecrire_html(resultats, rapport, args.capital, args.risque, args.demo, args.public)
    if not args.demo:
        journaliser(resultats, os.path.join(DOSSIER, "journal_signaux.csv"))
    print(f"Rapport pour le téléphone : {rapport}")


if __name__ == "__main__":
    main()
