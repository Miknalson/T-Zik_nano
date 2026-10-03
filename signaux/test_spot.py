"""Test historique de la cassure 20 jours en achat seulement, pour un bot sur une plateforme crypto.

Sur une plateforme d'échange au comptant, on ne peut pas vendre à découvert : la position est
achat ou rien. Pas de frais de financement (on possède la crypto). Frais : 0,1 % par ordre
+ un peu d'écart achat-vente (≈ 0,25 % aller-retour) ; la colonne « frais forts » prend 0,8 %
aller-retour (tarif débutant le plus cher). Même règle d'acceptation qu'avant : gagnant sur
les deux moitiés de l'historique, au moins 30 trades.
"""
import signaux as s

FRAIS_SPOT = {"aller_retour": 0.0025, "financement_jour": 0.0}
FRAIS_FORTS = {"aller_retour": 0.008, "financement_jour": 0.0}


def main():
    for ticker, regle in s.METHODE_SUIVIE.items():
        nom = dict((t, n) for t, n, _ in s.MARCHES)[ticker]
        if not ticker.endswith("-USD"):
            continue
        df = s.seances_terminees(s.completer_crypto(ticker, s.telecharger(ticker, 10)), "crypto")
        voulu = s.REGLES[regle](df)
        achat = voulu.clip(lower=0)
        cfd = s.evaluer(df, voulu, s.FRAIS["crypto"], en_cours=True)
        e = s.evaluer(df, achat, FRAIS_SPOT, en_cours=True)
        forts = s.evaluer(df, achat, FRAIS_FORTS, en_cours=True)
        net, moitie = e["execution"]["net"], len(df) // 2
        m1, m2 = net[:moitie].sum(), net[moitie:].sum()
        ok = m1 > 0 and m2 > 0 and e["nb_trades"] >= s.TRADES_MIN
        print(f"{nom:<10} achat seul {e['nb_trades']:>4} trades {e['rendement_annuel']:+7.1%}/an "
              f"(frais forts {forts['rendement_annuel']:+7.1%}/an) moitiés {m1:+.0%} / {m2:+.0%} "
              f"p = {e['p']:.3f} | achat+vente Libertex {cfd['rendement_annuel']:+7.1%}/an  "
              f"{'OK' if ok else 'NON'}")


if __name__ == "__main__":
    main()
