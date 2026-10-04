"""Recherche d'une méthode qui marche sur les actions (CFD Libertex), même protocole que le forex.

Protocole fixé AVANT de voir les résultats (04/10/2026) :
- les 5 méthodes de test_forex.py, sans aucun réglage retouché ;
- 30 grandes actions (20 américaines, 10 françaises), achat et vente, entrée en cours permise,
  stop 2 × ATR ;
- frais prudents d'un CFD action : 0,3 % aller-retour, financement 0,02 % par nuit ;
- sélection sur 2010-2018 : gagnant, au moins 30 trades, p < 0,05 ;
- confirmation sur 2019 à aujourd'hui, période que la sélection n'a pas vue.
Biais connu : ces actions sont des réussites d'aujourd'hui, ce qui avantage les méthodes de
tendance ; la comparaison au hasard en corrige une partie seulement.
"""
import time

import pandas as pd
import yfinance as yf

import signaux as s
from test_forex import REGLES, P_STRICT

ACTIONS = {"Apple": "AAPL", "Microsoft": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN", "Google": "GOOGL",
           "Meta": "META", "Tesla": "TSLA", "AMD": "AMD", "Netflix": "NFLX", "Intel": "INTC",
           "JPMorgan": "JPM", "Visa": "V", "Mastercard": "MA", "Coca-Cola": "KO", "Pepsi": "PEP",
           "Exxon": "XOM", "J&J": "JNJ", "Walmart": "WMT", "Disney": "DIS", "Boeing": "BA",
           "LVMH": "MC.PA", "TotalEnergies": "TTE.PA", "Airbus": "AIR.PA", "L'Oréal": "OR.PA",
           "Sanofi": "SAN.PA", "BNP": "BNP.PA", "Hermès": "RMS.PA", "Schneider": "SU.PA",
           "Air Liquide": "AI.PA", "Kering": "KER.PA"}
FRAIS_ACTION = {"aller_retour": 0.003, "financement_jour": 0.0002}
DEBUT, COUPURE = "2010-01-01", "2019-01-01"


def historique(ticker):
    for essai in range(3):
        df = yf.download(ticker, period="max", interval="1d", auto_adjust=True, progress=False)
        if not df.empty:
            break
        time.sleep(20)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    df = df[(df > 0).all(axis=1)]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return s.seances_terminees(df[df.index >= DEBUT], "action")


def periode(df, voulu, debut=None, fin=None):
    masque = pd.Series(True, index=df.index)
    if debut:
        masque &= df.index >= debut
    if fin:
        masque &= df.index < fin
    return s.evaluer(df[masque], voulu[masque], FRAIS_ACTION, en_cours=True)


def main():
    lignes, selectionnees, confirmees = [], 0, []
    for nom, ticker in ACTIONS.items():
        try:
            df = historique(ticker)
        except Exception as exc:
            print(f"{nom} : données indisponibles ({exc})")
            continue
        time.sleep(3)
        for nom_regle, regle in REGLES.items():
            voulu = regle(df)
            avant = periode(df, voulu, fin=COUPURE)
            apres = periode(df, voulu, debut=COUPURE)
            choisie = avant["rendement_annuel"] > 0 and avant["nb_trades"] >= s.TRADES_MIN and avant["p"] < P_STRICT
            confirmee = choisie and apres["rendement_annuel"] > 0
            selectionnees += choisie
            if confirmee:
                confirmees.append(f"{nom} — {nom_regle}")
            lignes.append((avant["p"], f"{nom:<14} {nom_regle:<28} 2010-18 : {avant['rendement_annuel']:+6.1%}/an "
                                       f"{avant['nb_trades']:>4} trades p = {avant['p']:.3f} | 2019-26 : "
                                       f"{apres['rendement_annuel']:+6.1%}/an {apres['nb_trades']:>3} trades "
                                       f"p = {apres['p']:.2f}  {'CONFIRMÉE' if confirmee else 'sélectionnée, puis ÉCHEC' if choisie else ''}"))
    for _, ligne in sorted(lignes)[:40]:
        print(ligne)
    print(f"\nSélectionnées sur 2010-2018 : {selectionnees} sur {len(lignes)} (≈ {len(lignes) * P_STRICT:.1f} par hasard).")
    print(f"Confirmées sur 2019-2026 : {len(confirmees)} (≈ {len(lignes) * P_STRICT / 2:.1f} par hasard) : "
          f"{', '.join(confirmees) or 'aucune'}")


if __name__ == "__main__":
    main()
