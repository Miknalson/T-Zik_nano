"""Le bot devrait-il aussi parier sur la baisse avec la marge Kraken ?

Teste séparément les deux côtés de la cassure 20 jours sur les 14 cryptos du bot :
- achat au comptant (ce que fait le bot) : 0,4 % par ordre, pas de frais de nuit ;
- vente à découvert sur marge : 0,4 % par ordre + 0,02 % d'ouverture + 0,02 % toutes les
  4 heures tant que la position est ouverte (≈ 0,12 % par jour, tarif Kraken courant).
Règle fixée avant le test (04/10/2026) : le côté vente vaut la peine seulement s'il gagne sur
les deux moitiés de l'historique, avec au moins 30 trades et p < 0,05, sur la majorité des cryptos.
"""
import signaux as s
from test_portefeuille import UNIVERS

ACHAT = {"aller_retour": 0.008, "financement_jour": 0.0}
VENTE_MARGE = {"aller_retour": 0.0082, "financement_jour": 0.0012}


def cote(df, voulu, frais):
    e = s.evaluer(df, voulu, frais, en_cours=True)
    net, moitie = e["execution"]["net"], len(df) // 2
    m1, m2 = net[:moitie].sum(), net[moitie:].sum()
    ok = m1 > 0 and m2 > 0 and e["nb_trades"] >= s.TRADES_MIN and e["p"] < 0.05
    return e, m1, m2, ok


def main():
    bons = 0
    for nom, ticker in UNIVERS.items():
        df = s.seances_terminees(s.telecharger(ticker, 10), "crypto")
        df = df[(df > 0).all(axis=1)]
        voulu = s.regle_cassure(df)
        a, _, _, _ = cote(df, voulu.clip(lower=0), ACHAT)
        v, m1, m2, ok = cote(df, voulu.clip(upper=0), VENTE_MARGE)
        bons += ok
        print(f"{nom:<10} achat {a['rendement_annuel']:+7.1%}/an | vente sur marge {v['rendement_annuel']:+7.1%}/an "
              f"{v['nb_trades']:>3} trades, moitiés {m1:+5.0%} / {m2:+5.0%}, p = {v['p']:.2f}  {'UTILE' if ok else ''}")
    print(f"\nCôté vente utile sur {bons} crypto(s) sur {len(UNIVERS)} "
          f"(il en faudrait au moins {len(UNIVERS) // 2 + 1}).")


if __name__ == "__main__":
    main()
