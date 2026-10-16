"""Le bot rachète trop vite et achète en marché baissier ? Test des entrées sur 10 ans.

Règles fixées AVANT de voir les résultats (16/10/2026), même portefeuille que le bot :
- actuelle : achat dès que la cassure est en hausse, même en cours de route ou le lendemain d'un stop ;
- A, nouvelle cassure seulement : achat uniquement le jour où la cassure apparaît ;
- B, marché en hausse seulement : achat uniquement si Bitcoin est au-dessus de sa moyenne 200 jours ;
- A + B.
Une variante remplace l'actuelle seulement si elle fait mieux sur les deux moitiés des 10 ans ;
si plusieurs y arrivent, celle qui finit avec le plus d'argent.
"""
import signaux as s
from test_portefeuille import UNIVERS, preparer, resume, simuler

VARIANTES = {"Actuelle": {},
             "A. Nouvelle cassure seulement": {"nouveau_seulement": True},
             "B. Marché en hausse seulement": {"filtre_marche": True},
             "A + B": {"nouveau_seulement": True, "filtre_marche": True}}


def main():
    donnees = {}
    for nom, ticker in UNIVERS.items():
        df = s.seances_terminees(s.telecharger(ticker, 10), "crypto")
        donnees[nom] = df[(df > 0).all(axis=1)]
    t, noms, dates = preparer(donnees)
    print(f"Du {dates[0]:%d/%m/%Y} au {dates[-1]:%d/%m/%Y}, départ 1000 €\n")
    resultats = {}
    for nom, options in VARIANTES.items():
        valeurs, achats = simuler(t, noms, **options)
        resultats[nom] = resume(nom, valeurs, dates, achats)
    final0, a1, a2 = resultats["Actuelle"]
    gagnantes = {nom: r for nom, r in resultats.items() if nom != "Actuelle" and r[1] > a1 and r[2] > a2}
    for nom in resultats:
        if nom != "Actuelle":
            print(f"{nom} : {'MIEUX sur les deux moitiés' if nom in gagnantes else 'pas mieux sur les deux moitiés'}")
    choix = max(gagnantes, key=lambda n: gagnantes[n][0]) if gagnantes else "Actuelle"
    print(f"\nÀ retenir : {choix}")


if __name__ == "__main__":
    main()
