"""Test historique du bot comme un vrai portefeuille : au plus 5 cryptos en même temps.

Règles fixées AVANT de voir les résultats (03/10/2026) :
- univers : les 6 cryptos du bot + les 8 grosses retenues par test_kraken.py ;
- chaque crypto suit la cassure 20 jours en achat seul, entrée en cours permise, stop 2 × ATR ;
- au plus 5 positions ; quand il y a plus de candidates que de places, on prend celles qui ont
  le plus monté sur 90 jours ;
- taille : 1 % du portefeuille risqué au stop, plafonnée à 1/5 du portefeuille et aux liquidités ;
- frais du bot (0,4 % par ordre). Entrée et sortie à l'ouverture qui suit le signal, stop dans
  la séance (à l'ouverture en cas de gap), comme pour les autres tests.
Comparaison : le même portefeuille avec un classement tiré au hasard (le classement apporte-t-il
quelque chose ?) et sans limite de positions (le bot actuel).
"""
import numpy as np
import pandas as pd

import signaux as s
from bot import FRAIS_ORDRE, RISQUE

UNIVERS = {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD", "XRP": "XRP-USD", "Dogecoin": "DOGE-USD",
           "Stellar": "XLM-USD", "VeChain": "VET-USD", "Solana": "SOL-USD", "BNB": "BNB-USD",
           "Tron": "TRX-USD", "Avalanche": "AVAX-USD", "NEAR": "NEAR-USD", "Hedera": "HBAR-USD",
           "Polkadot": "DOT-USD", "Algorand": "ALGO-USD", "FLOKI": "FLOKI-USD"}
MAX_POSITIONS = 5
ELAN = 90  # jours pour mesurer « le plus monté »
CAPITAL = 1000.0


def preparer(donnees):
    """Tableaux alignés sur les mêmes dates : prix, signal de la veille, ATR et élan de la veille."""
    dates = sorted(set().union(*(df.index for df in donnees.values())))
    t = {}
    for champ in ("Open", "High", "Low", "Close"):
        t[champ] = pd.DataFrame({n: df[champ] for n, df in donnees.items()}).reindex(dates)
    t["voulu"] = pd.DataFrame({n: s.regle_cassure(df).clip(lower=0) for n, df in donnees.items()}
                              ).reindex(dates).shift(1)
    t["atr"] = pd.DataFrame({n: s.atr(df) for n, df in donnees.items()}).reindex(dates).shift(1)
    t["elan"] = pd.DataFrame({n: df["Close"] / df["Close"].shift(ELAN) - 1 for n, df in donnees.items()}
                             ).reindex(dates).shift(1)
    return {k: v.to_numpy(float) for k, v in t.items()}, list(donnees), dates


def simuler(t, noms, max_positions=MAX_POSITIONS, hasard=None, tp_atr=None, suiveur_atr=None):
    """Valeur du portefeuille chaque soir. `hasard` : générateur pour classer au hasard.

    Variantes de sortie (test_sorties.py) : `tp_atr` vend dès que le cours monte de tp_atr × ATR
    au-dessus du prix d'achat ; `suiveur_atr` remonte le stop chaque soir à suiveur_atr × ATR
    sous la clôture (il ne redescend jamais).
    """
    o, h, l, c = t["Open"], t["High"], t["Low"], t["Close"]
    cash, positions, valeurs, trades = CAPITAL, {}, [], 0
    dernier = np.full(len(noms), np.nan)
    for i in range(len(c)):
        # 1. Sorties à l'ouverture : la règle a dit « plus en tendance » à la clôture de la veille.
        for j in list(positions):
            if not np.isnan(o[i, j]) and t["voulu"][i, j] == 0:
                q = positions.pop(j)[0]
                cash += q * o[i, j] * (1 - FRAIS_ORDRE)
        # 2. Entrées à l'ouverture, les plus fortes d'abord, dans la limite des places.
        valeur = cash + sum(p[0] * (o[i, j] if not np.isnan(o[i, j]) else dernier[j]) for j, p in positions.items())
        candidats = [j for j in range(len(noms)) if j not in positions and t["voulu"][i, j] == 1
                     and not np.isnan(o[i, j]) and not np.isnan(t["atr"][i, j]) and not np.isnan(t["elan"][i, j])]
        if hasard is not None:
            hasard.shuffle(candidats)
        else:
            candidats.sort(key=lambda j: -t["elan"][i, j])
        for j in candidats[:max(max_positions - len(positions), 0)]:
            distance = s.K_STOP * t["atr"][i, j]
            montant = min(valeur * RISQUE * o[i, j] / distance, valeur / MAX_POSITIONS, cash / (1 + FRAIS_ORDRE))
            if montant < 5:
                continue
            cash -= montant * (1 + FRAIS_ORDRE)
            objectif = o[i, j] + tp_atr * t["atr"][i, j] if tp_atr else np.inf
            positions[j] = [montant / o[i, j], o[i, j] - distance, objectif, t["atr"][i, j]]
            trades += 1
        assert len(positions) <= max_positions
        # 3. Stops dans la séance (au prix d'ouverture si le marché ouvre déjà dessous), puis
        #    objectif de gain s'il y en a un. Si les deux sont touchés le même jour, on suppose
        #    le stop d'abord (hypothèse prudente).
        for j in list(positions):
            q, stop, objectif, _ = positions[j]
            if not np.isnan(l[i, j]) and l[i, j] <= stop:
                positions.pop(j)
                cash += q * min(o[i, j], stop) * (1 - FRAIS_ORDRE)
            elif not np.isnan(h[i, j]) and h[i, j] >= objectif:
                positions.pop(j)
                cash += q * max(o[i, j], objectif) * (1 - FRAIS_ORDRE)
        # 4. Stop suiveur : remonté à la clôture, jamais redescendu.
        if suiveur_atr:
            for j, p in positions.items():
                if not np.isnan(c[i, j]):
                    p[1] = max(p[1], c[i, j] - suiveur_atr * p[3])
        dernier = np.where(np.isnan(c[i]), dernier, c[i])
        valeurs.append(cash + sum(p[0] * dernier[j] for j, p in positions.items()))
    return np.array(valeurs), trades


def resume(nom, valeurs, dates, trades):
    annees = (dates[-1] - dates[0]).days / 365.25
    serie = pd.Series(valeurs, index=dates)
    moitie = len(serie) // 2
    m1 = serie.iloc[moitie] / serie.iloc[0] - 1
    m2 = serie.iloc[-1] / serie.iloc[moitie] - 1
    baisse = (serie / serie.cummax() - 1).min()
    rendement = (serie.iloc[-1] / CAPITAL) ** (1 / annees) - 1
    print(f"{nom:<34} {serie.iloc[-1]:>10.0f} €  {rendement:+6.1%}/an  pire baisse {baisse:6.1%}  "
          f"moitiés {m1:+7.0%} / {m2:+6.0%}  {trades} achats")
    return serie.iloc[-1], m1, m2


def main():
    donnees = {}
    for nom, ticker in UNIVERS.items():
        df = s.seances_terminees(s.telecharger(ticker, 10), "crypto")
        donnees[nom] = df[(df > 0).all(axis=1)]
    t, noms, dates = preparer(donnees)
    print(f"Du {dates[0]:%d/%m/%Y} au {dates[-1]:%d/%m/%Y}, départ {CAPITAL:.0f} €\n")

    valeurs, trades = simuler(t, noms)
    final, m1, m2 = resume("Max 5, les plus fortes d'abord", valeurs, dates, trades)
    valeurs, trades = simuler(t, noms, max_positions=len(noms))
    resume("Sans limite (bot actuel, 14 cryptos)", valeurs, dates, trades)
    rng = np.random.default_rng(0)
    finaux = np.array([simuler(t, noms, hasard=rng)[0][-1] for _ in range(100)])
    p = (1 + np.sum(finaux >= final)) / (1 + len(finaux))
    print(f"{'Max 5, tirées au hasard (100 fois)':<34} {np.median(finaux):>10.0f} € en médiane "
          f"(de {finaux.min():.0f} à {finaux.max():.0f} €)")
    print(f"\nLe classement « les plus fortes d'abord » bat le hasard ? p = {p:.2f} "
          f"({'oui' if p < 0.05 else 'non, pas nettement'}). "
          f"Gagnant sur les deux moitiés : {'oui' if m1 > 0 and m2 > 0 else 'non'}.")


if __name__ == "__main__":
    main()
