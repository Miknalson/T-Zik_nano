"""Recherche d'une méthode qui marche sur le forex, sans se tromper soi-même.

Protocole fixé AVANT de voir les résultats (03/10/2026) :
- 5 méthodes seulement, sans aucun réglage retouché : les 3 du programme + cassure 55 jours
  (sortie 20 jours, « Turtle ») + élan 100 jours (acheteur si le cours est au-dessus de celui
  d'il y a 100 séances, vendeur sinon) ;
- 10 grandes paires, achat et vente, entrée en cours permise, stop 2 × ATR, frais forex du
  programme (écart + financement de nuit) ;
- sélection sur 2005-2018 : gagnant, au moins 30 trades, p < 0,05 ;
- confirmation sur 2019 à aujourd'hui, période que la sélection n'a pas vue : doit gagner aussi.
Par pur hasard, ~2,5 combinaisons sur 50 passent la sélection et ~1 la confirmation.
"""
import time

import pandas as pd
import yfinance as yf

import signaux as s

PAIRES = {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X", "AUD/USD": "AUDUSD=X",
          "USD/CHF": "CHF=X", "USD/CAD": "CAD=X", "NZD/USD": "NZDUSD=X", "EUR/GBP": "EURGBP=X",
          "EUR/JPY": "EURJPY=X", "GBP/JPY": "GBPJPY=X"}
DEBUT, COUPURE = "2005-01-01", "2019-01-01"
P_STRICT = 0.05


def regle_elan(df, n=100):
    c = df["Close"]
    pos = pd.Series(0.0, index=df.index)
    pos[c > c.shift(n)] = 1
    pos[c < c.shift(n)] = -1
    return pos


REGLES = {**s.REGLES,
          "Cassure 55 jours": lambda df: s.regle_cassure(df, entree=55, sortie=20),
          "Élan 100 jours": regle_elan}


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
    return s.seances_terminees(df[df.index >= DEBUT], "forex")


def periode(df, voulu, debut=None, fin=None):
    masque = pd.Series(True, index=df.index)
    if debut:
        masque &= df.index >= debut
    if fin:
        masque &= df.index < fin
    return s.evaluer(df[masque], voulu[masque], s.FRAIS["forex"], en_cours=True)


def main():
    lignes, selectionnees, confirmees = [], 0, []
    for nom, ticker in PAIRES.items():
        try:
            df = historique(ticker)
        except Exception as exc:
            print(f"{nom} : données indisponibles ({exc})")
            continue
        time.sleep(3)
        for nom_regle, regle in REGLES.items():
            voulu = regle(df)  # calculée sur tout l'historique : seuls les signaux passés comptent
            avant = periode(df, voulu, fin=COUPURE)
            apres = periode(df, voulu, debut=COUPURE)
            choisie = avant["rendement_annuel"] > 0 and avant["nb_trades"] >= s.TRADES_MIN and avant["p"] < P_STRICT
            confirmee = choisie and apres["rendement_annuel"] > 0
            selectionnees += choisie
            if confirmee:
                confirmees.append(f"{nom} — {nom_regle}")
            lignes.append((avant["p"], f"{nom:<8} {nom_regle:<28} 2005-18 : {avant['rendement_annuel']:+6.1%}/an "
                                       f"{avant['nb_trades']:>4} trades p = {avant['p']:.3f} | 2019-26 : "
                                       f"{apres['rendement_annuel']:+6.1%}/an {apres['nb_trades']:>3} trades "
                                       f"p = {apres['p']:.2f}  {'CONFIRMÉE' if confirmee else 'sélectionnée, puis ÉCHEC' if choisie else ''}"))
    for _, ligne in sorted(lignes):
        print(ligne)
    print(f"\nSélectionnées sur 2005-2018 : {selectionnees} sur {len(lignes)} (≈ {len(lignes) * P_STRICT:.1f} par hasard).")
    print(f"Confirmées sur 2019-2026 : {', '.join(confirmees) or 'aucune'} (≈ {len(lignes) * P_STRICT / 2:.1f} par hasard).")


if __name__ == "__main__":
    main()
