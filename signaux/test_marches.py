"""Test historique de la méthode cassure 20 jours (entrée en cours permise) sur de nouveaux marchés.

Règle d'ajout fixée avant de voir les résultats (29/09/2026) : gagnant sur les deux moitiés
de l'historique et au moins 30 trades, avec les frais Libertex. Réglages inchangés. La colonne
« frais ×2 » vérifie que le résultat tient si le spread réel est plus large.
"""
import signaux as s

NOUVEAUX = [
    ("DOGE-USD", "Dogecoin", "crypto"), ("ADA-USD", "Cardano", "crypto"),
    ("XLM-USD", "Stellar", "crypto"), ("ETC-USD", "Ethereum Classic", "crypto"),
    ("LINK-USD", "Chainlink", "crypto"), ("VET-USD", "VeChain", "crypto"),
    ("SHIB-USD", "SHIB", "crypto"), ("PEPE24478-USD", "PEPE", "crypto"),
    ("APT21794-USD", "Aptos", "crypto"), ("WLD-USD", "Worldcoin", "crypto"),
    ("BZ=F", "Pétrole Brent", "matiere"),
]


def main():
    retenus = []
    for ticker, nom, classe in NOUVEAUX:
        try:
            df = s.telecharger(ticker, 10)
            if classe == "crypto":
                df = s.completer_crypto(ticker, df)
            df = s.seances_terminees(df, classe)
        except Exception as exc:
            print(f"{nom:<17} données indisponibles : {exc}")
            continue
        voulu = s.regle_cassure(df)
        e = s.evaluer(df, voulu, s.FRAIS[classe], en_cours=True)
        double = {k: 2 * v for k, v in s.FRAIS[classe].items()}
        e2 = s.evaluer(df, voulu, double, en_cours=True)
        net, moitie = e["execution"]["net"], len(df) // 2
        m1, m2 = net[:moitie].sum(), net[moitie:].sum()
        annees = (df.index[-1] - df.index[0]).days / 365.25
        ok = m1 > 0 and m2 > 0 and e["nb_trades"] >= s.TRADES_MIN
        if ok:
            retenus.append(nom)
        print(f"{nom:<17} {annees:4.1f} ans {e['nb_trades']:>4} trades  {e['rendement_annuel']:+7.1%}/an  "
              f"(frais ×2 : {e2['rendement_annuel']:+7.1%}/an)  moitiés {m1:+.0%} / {m2:+.0%}  "
              f"p = {e['p']:.3f}  {'RETENU' if ok else 'non retenu'}")
    print(f"\nRetenus : {', '.join(retenus) or 'aucun'} sur {len(NOUVEAUX)} testés.")


if __name__ == "__main__":
    main()
