"""Le bot devrait-il vendre « quand c'est en hausse » ? Test des sorties sur 10 ans.

Règles fixées AVANT de voir les résultats (09/10/2026), même portefeuille que le bot (15 cryptos,
5 positions au plus, 1 % de risque, frais Kraken) :
- actuelle : vente quand la clôture passe sous le plus bas des 10 jours, ou stop 2 × ATR ;
- prise de bénéfice : en plus, vente dès que le cours monte de 3 × ATR au-dessus du prix d'achat ;
- stop suiveur : en plus, stop remonté chaque soir à 3 × ATR sous la clôture.
Une variante ne remplace l'actuelle que si elle fait mieux sur les deux moitiés des 10 ans.
"""
import signaux as s
from test_portefeuille import UNIVERS, preparer, resume, simuler

VARIANTES = {"Actuelle (tendance + stop)": {},
             "Prise de bénéfice à +3 ATR": {"tp_atr": 3.0},
             "Stop suiveur à 3 ATR": {"suiveur_atr": 3.0}}


def main():
    donnees = {}
    for nom, ticker in UNIVERS.items():
        df = s.seances_terminees(s.telecharger(ticker, 10), "crypto")
        donnees[nom] = df[(df > 0).all(axis=1)]
    t, noms, dates = preparer(donnees)
    print(f"Du {dates[0]:%d/%m/%Y} au {dates[-1]:%d/%m/%Y}, départ 1000 €\n")
    resultats = {}
    for nom, options in VARIANTES.items():
        valeurs, trades = simuler(t, noms, **options)
        resultats[nom] = resume(nom, valeurs, dates, trades)
    _, a1, a2 = resultats["Actuelle (tendance + stop)"]
    for nom, (_, m1, m2) in resultats.items():
        if nom != "Actuelle (tendance + stop)":
            mieux = m1 > a1 and m2 > a2
            print(f"{nom} : {'MIEUX sur les deux moitiés' if mieux else 'pas mieux sur les deux moitiés'}")


if __name__ == "__main__":
    main()
