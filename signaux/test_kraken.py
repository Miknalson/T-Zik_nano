"""Test historique de la cassure 20 jours (achat seul) sur toutes les cryptos en euros de Kraken.

Règle d'ajout fixée AVANT de voir les résultats (03/10/2026). Comme on teste des centaines de
cryptos, certaines passeraient le test habituel par pur hasard : la règle est donc plus stricte.
- au moins 3 ans d'historique ;
- gagnante sur les deux moitiés de l'historique ;
- au moins 30 trades ;
- p < 0,05 : nettement meilleure que les mêmes trades placés à des dates au hasard.
Mêmes réglages et mêmes frais que le bot (test_spot.py). Historique Yahoo (USD), contrôlé contre
le prix Kraken pour écarter les homonymes (Yahoo donne parfois une autre crypto du même nom).
"""
import json
import time
import urllib.request

import pandas as pd
import yfinance as yf

import signaux as s
from bot import PAIRES
from test_spot import FRAIS_SPOT

P_STRICT = 0.05
ANS_MIN = 3
MONNAIES = {"USD", "EUR", "GBP", "CHF", "CAD", "AUD", "JPY", "USDT", "USDC", "DAI", "PYUSD", "EURT",
            "EURC", "USDE", "USDS", "TUSD", "USDG", "RLUSD", "USDQ", "EURQ", "EURR", "USDR", "FDUSD"}
YAHOO = {"XBT": "BTC", "XDG": "DOGE"}


def paires_kraken():
    with urllib.request.urlopen("https://api.kraken.com/0/public/AssetPairs", timeout=30) as r:
        paires = json.load(r)["result"]
    deja = set(PAIRES.values())
    bases = {}
    for cle, v in paires.items():
        alt = v["altname"]
        if not alt.endswith("EUR") or v.get("status") != "online" or alt in deja or alt.endswith(".d"):
            continue
        base = alt[:-3]
        if base not in MONNAIES:
            bases[base] = cle  # nom interne de la paire, ex. XLTCZEUR pour LTCEUR
    return bases


def prix_kraken(cles):
    prix = {}
    for i in range(0, len(cles), 50):
        url = "https://api.kraken.com/0/public/Ticker?pair=" + ",".join(cles[i:i + 50])
        with urllib.request.urlopen(url, timeout=30) as r:
            prix.update({cle: float(t["c"][0]) for cle, t in json.load(r)["result"].items()})
    return prix


def historiques(tickers, paquet=20, pause=8):
    """Télécharge par petits paquets : Yahoo bloque les gros téléchargements (« Too Many Requests »)."""
    resultat, manquants = {}, list(tickers)
    for tour in range(3):
        restants = []
        for i in range(0, len(manquants), paquet):
            lot = manquants[i:i + paquet]
            donnees = yf.download(lot, period="10y", interval="1d", auto_adjust=True, progress=False,
                                  group_by="ticker", threads=False)
            for t in lot:
                try:
                    df = donnees[t][["Open", "High", "Low", "Close"]].dropna()
                except KeyError:
                    df = pd.DataFrame()
                df = df[(df > 0).all(axis=1)]  # Yahoo met parfois des prix à zéro
                if df.empty:
                    restants.append(t)
                else:
                    df.index = pd.to_datetime(df.index).tz_localize(None)
                    resultat[t] = df
            time.sleep(pause)
        manquants = restants
        if not manquants:
            break
        time.sleep(60)  # laisse passer la limite de Yahoo avant de réessayer les absents
    return resultat


def main():
    bases = paires_kraken()
    prix_eur = prix_kraken(list(bases.values()))
    tickers = {base: f"{YAHOO.get(base, base)}-USD" for base in bases}
    donnees = historiques(list(tickers.values()))

    lignes, retenus, testes, recents, douteux, absents = [], [], 0, [], [], []
    for base, ticker in sorted(tickers.items()):
        df = donnees.get(ticker)
        df = s.seances_terminees(df, "crypto") if df is not None else None
        if df is None or len(df) < 2:
            absents.append(base)
            continue
        annees = (df.index[-1] - df.index[0]).days / 365.25
        if annees < ANS_MIN:
            recents.append(f"{base} ({annees:.1f} an)")
            continue
        eur = prix_eur.get(bases[base])
        ratio = eur / df["Close"].iloc[-1] if eur else 0
        if not 0.7 < ratio < 1.1:  # 1 € ≈ 1,13 $ : un prix en euros vaut ~0,88 fois le prix en dollars
            douteux.append(base)
            continue
        testes += 1
        e = s.evaluer(df, s.regle_cassure(df).clip(lower=0), FRAIS_SPOT, en_cours=True)
        net, moitie = e["execution"]["net"], len(df) // 2
        m1, m2 = net[:moitie].sum(), net[moitie:].sum()
        ok = m1 > 0 and m2 > 0 and e["nb_trades"] >= s.TRADES_MIN and e["p"] < P_STRICT
        if ok:
            retenus.append(base)
        lignes.append((e["p"], f"{base:<7} {annees:4.1f} ans {e['nb_trades']:>4} trades "
                               f"{e['rendement_annuel']:+8.1%}/an  moitiés {m1:+6.0%} / {m2:+6.0%}  "
                               f"p = {e['p']:.3f}  {'RETENU' if ok else ''}"))

    for _, ligne in sorted(lignes):
        print(ligne)
    print(f"\n{len(bases)} cryptos en euros sur Kraken (hors les 6 du bot et les monnaies stables).")
    print(f"Testées : {testes}. Trop récentes (< {ANS_MIN} ans) : {len(recents)}. "
          f"Sans historique Yahoo : {len(absents)}. Prix Yahoo ≠ Kraken (homonyme) : {len(douteux)}.")
    print(f"Retenues : {', '.join(retenus) or 'aucune'}. "
          f"Par pur hasard, on en attendrait au plus environ {testes * P_STRICT:.0f}.")
    print(f"\nTrop récentes : {', '.join(recents)}")
    print(f"Sans historique Yahoo : {', '.join(absents)}")
    print(f"Homonymes écartés : {', '.join(douteux)}")


if __name__ == "__main__":
    main()
