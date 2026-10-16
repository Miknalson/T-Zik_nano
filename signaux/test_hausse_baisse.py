"""Parier sur la hausse ET sur la baisse ? Test du portefeuille du bot sur 10 ans.

Règles fixées AVANT de voir les résultats (16/10/2026), même portefeuille que le bot (15 cryptos,
5 positions au plus, 1 % de risque, plafond 1/5 par position, stop 2 × ATR) :
- achat : cassure 20 jours à la hausse, seulement si Bitcoin est au-dessus de sa moyenne 200 jours
  (variante B de test_entrees.py), frais du comptant 0,4 % par ordre ;
- vente : cassure 20 jours à la baisse (clôture sous le plus bas des 20 jours), seulement si Bitcoin
  est sous sa moyenne 200 jours ; sortie quand la clôture repasse au-dessus du plus haut des 10 jours
  ou au stop 2 × ATR au-dessus du prix de vente ;
- coûts de la vente : contrats perpétuels Kraken (0,05 % par ordre, 0,03 % par jour de financement)
  ou marge Kraken (0,42 % par ordre, 0,12 % par jour), les deux sont testés.
La vente est ajoutée au bot seulement si « achat + vente (perpétuels) » fait mieux que « achat seul »
sur les deux moitiés des 10 ans.
"""
import numpy as np
import pandas as pd

import signaux as s
from bot import FRAIS_ORDRE, RISQUE
from test_portefeuille import CAPITAL, MAX_POSITIONS, UNIVERS, preparer, resume

PERPETUELS = (0.0005, 0.0003)   # frais par ordre, financement par jour
MARGE = (0.0042, 0.0012)


def preparer_ventes(donnees, dates):
    """Signal de vente de la veille : -1 quand la cassure est à la baisse."""
    return pd.DataFrame({n: s.regle_cassure(df).clip(upper=0) for n, df in donnees.items()}
                        ).reindex(dates).shift(1).to_numpy(float)


def simuler(t, ventes, noms, achats=True, filtre=True, cout_vente=None):
    o, h, l, c = t["Open"], t["High"], t["Low"], t["Close"]
    cash, positions, valeurs, trades = CAPITAL, {}, [], 0
    dernier = np.full(len(noms), np.nan)

    def valeur_position(p, prix):
        q, sens, entree, mise = p["q"], p["sens"], p["entree"], p["mise"]
        return q * prix if sens > 0 else mise + q * (entree - prix)

    def fermer(j, prix):
        nonlocal cash
        p = positions.pop(j)
        frais = FRAIS_ORDRE if p["sens"] > 0 else cout_vente[0]
        cash += valeur_position(p, prix) - p["q"] * prix * frais

    for i in range(len(c)):
        hausse = t["marche"][i] == 1
        # 1. Sorties à l'ouverture quand la règle ne veut plus de la position.
        for j in list(positions):
            p = positions[j]
            veut = t["voulu"][i, j] == 1 if p["sens"] > 0 else ventes[i, j] == -1
            if not np.isnan(o[i, j]) and not veut:
                fermer(j, o[i, j])
        # 2. Entrées à l'ouverture, les plus fortes (hausse ou baisse) d'abord.
        valeur = cash + sum(valeur_position(p, o[i, j] if not np.isnan(o[i, j]) else dernier[j])
                            for j, p in positions.items())
        candidats = []
        for j in range(len(noms)):
            if j in positions or np.isnan(o[i, j]) or np.isnan(t["atr"][i, j]) or np.isnan(t["elan"][i, j]):
                continue
            if achats and t["voulu"][i, j] == 1 and (hausse or not filtre):
                candidats.append((-t["elan"][i, j], j, 1))
            elif cout_vente and ventes[i, j] == -1 and (not hausse or not filtre):
                candidats.append((t["elan"][i, j], j, -1))
        for _, j, sens in sorted(candidats)[:max(MAX_POSITIONS - len(positions), 0)]:
            distance = s.K_STOP * t["atr"][i, j]
            frais = FRAIS_ORDRE if sens > 0 else cout_vente[0]
            mise = min(valeur * RISQUE * o[i, j] / distance, valeur / MAX_POSITIONS, cash / (1 + frais))
            if mise < 5:
                continue
            cash -= mise * (1 + frais)
            positions[j] = {"q": mise / o[i, j], "sens": sens, "entree": o[i, j], "mise": mise,
                            "stop": o[i, j] - sens * distance}
            trades += 1
        # 3. Stops dans la séance (au prix d'ouverture en cas de gap).
        for j in list(positions):
            p = positions[j]
            if p["sens"] > 0 and not np.isnan(l[i, j]) and l[i, j] <= p["stop"]:
                fermer(j, min(o[i, j], p["stop"]))
            elif p["sens"] < 0 and not np.isnan(h[i, j]) and h[i, j] >= p["stop"]:
                fermer(j, max(o[i, j], p["stop"]))
        # 4. Financement des ventes, chaque jour.
        for j, p in positions.items():
            if p["sens"] < 0 and not np.isnan(c[i, j]):
                cash -= p["q"] * c[i, j] * cout_vente[1]
        dernier = np.where(np.isnan(c[i]), dernier, c[i])
        valeurs.append(cash + sum(valeur_position(p, dernier[j]) for j, p in positions.items()))
    return np.array(valeurs), trades


def main():
    donnees = {}
    for nom, ticker in UNIVERS.items():
        df = s.seances_terminees(s.telecharger(ticker, 10), "crypto")
        donnees[nom] = df[(df > 0).all(axis=1)]
    t, noms, dates = preparer(donnees)
    ventes = preparer_ventes(donnees, dates)
    print(f"Du {dates[0]:%d/%m/%Y} au {dates[-1]:%d/%m/%Y}, départ {CAPITAL:.0f} €\n")
    variantes = {
        "Actuelle (achat seul, sans filtre)": dict(filtre=False),
        "Achat seul, marché en hausse (B)": dict(),
        "Achat + vente, perpétuels": dict(cout_vente=PERPETUELS),
        "Achat + vente, marge": dict(cout_vente=MARGE),
        "Vente seule, perpétuels": dict(achats=False, cout_vente=PERPETUELS),
    }
    r = {}
    for nom, options in variantes.items():
        valeurs, trades = simuler(t, ventes, noms, **options)
        r[nom] = resume(nom, valeurs, dates, trades)
    _, b1, b2 = r["Achat seul, marché en hausse (B)"]
    _, v1, v2 = r["Achat + vente, perpétuels"]
    print(f"\nAjouter la vente (perpétuels) : {'OUI, mieux sur les deux moitiés' if v1 > b1 and v2 > b2 else 'NON, pas mieux sur les deux moitiés'}")


if __name__ == "__main__":
    main()
