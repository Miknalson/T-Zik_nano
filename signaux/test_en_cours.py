"""Test historique : peut-on entrer quand la carte dit EN COURS ?

Variante testée : dès que tu es à plat et que la règle est en position, tu entres à
l'ouverture suivante avec un stop neuf à 2 × ATR (y compris le lendemain d'un stop).
Mêmes règles, mêmes frais Libertex, même filtre anti-hasard qu'en quotidien.
"""
import signaux as s


def main():
    lignes, valides, testees = [], 0, 0
    for ticker, nom, classe in s.MARCHES:
        try:
            df = s.telecharger(ticker, 15)
            if classe == "crypto":
                df = s.completer_crypto(ticker, df)
            df = s.seances_terminees(df, classe)
        except Exception as exc:
            print(f"{nom:<13} données indisponibles : {exc}")
            continue
        for nom_regle, regle in s.REGLES.items():
            voulu = regle(df)
            avant = s.evaluer(df, voulu, s.FRAIS[classe])
            e = s.evaluer(df, voulu, s.FRAIS[classe], en_cours=True)
            testees += 1
            valides += e["valide"]
            etoile = " ★" if s.METHODE_SUIVIE.get(ticker) == nom_regle else ""
            lignes.append(f"{nom:<13} {nom_regle:<30} actuelle {avant['rendement_annuel']:+6.1%}/an p = {avant['p']:.2f}"
                          f" | en cours {e['nb_trades']:>4} trades {e['rendement_annuel']:+6.1%}/an p = {e['p']:.3f}  "
                          f"{'VALIDÉE' if e['valide'] else 'rejetée : ' + ', '.join(e['raisons'])}{etoile}")
    print("\n".join(lignes))
    print(f"\nEntrée en cours : {valides} règle(s) validée(s) sur {testees}. "
          f"Par pur hasard, on en attendrait environ {testees * s.P_MAX:.1f}.")


if __name__ == "__main__":
    main()
