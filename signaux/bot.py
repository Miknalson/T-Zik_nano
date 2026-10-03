"""Bot crypto : achète, vend et pose le stop tout seul. Mode papier (argent fictif) pour l'instant.

Méthode : cassure 20 jours en achat seulement (test_spot.py), entrée en cours permise, stop à
2 × ATR posé à l'achat, vente quand le cours clôture sous le plus bas des 10 derniers jours.
Bougies journalières et prix de Kraken (paires en euros). Lancé chaque jour juste après la
clôture de 00 h 00 UTC. En mode papier, les ordres sont simulés au prix du marché Kraken, frais
compris, sur un portefeuille de 1 000 € enregistré dans bot_portefeuille.json.
"""
import argparse
import csv
import datetime as dt
import json
import os
import urllib.parse
import urllib.request

import pandas as pd

import signaux as s

PAIRES = {"Bitcoin": "XBTEUR", "Ethereum": "ETHEUR", "XRP": "XRPEUR",
          "Dogecoin": "XDGEUR", "Stellar": "XLMEUR", "VeChain": "VETEUR"}
FRAIS_ORDRE = 0.004   # Kraken, ordre au marché, petit volume
RISQUE = 0.01         # un stop touché coûte 1 % du portefeuille
CAPITAL_DEPART = 1000.0
ORDRE_MIN = 5.0       # en dessous, Kraken refuse l'ordre
DOSSIER = os.path.dirname(os.path.abspath(__file__))
ETAT = os.path.join(DOSSIER, "bot_portefeuille.json")
JOURNAL = os.path.join(DOSSIER, "bot_journal.csv")


# ----------------------------------------------------------------------- Kraken
def kraken(chemin, **params):
    url = f"https://api.kraken.com/0/public/{chemin}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as reponse:
        donnees = json.load(reponse)
    if donnees["error"]:
        raise RuntimeError(", ".join(donnees["error"]))
    return donnees["result"]


def bougies(paire):
    """Bougies journalières terminées (celle du jour, en cours, est retirée)."""
    resultat = kraken("OHLC", pair=paire, interval=1440)
    lignes = next(v for k, v in resultat.items() if k != "last")
    df = pd.DataFrame(lignes, columns=["t", "Open", "High", "Low", "Close", "vwap", "volume", "nb"])
    df.index = pd.to_datetime(df["t"], unit="s")
    return df[["Open", "High", "Low", "Close"]].astype(float).iloc[:-1]


def prix_actuel(paire):
    return float(next(iter(kraken("Ticker", pair=paire).values()))["c"][0])


# ---------------------------------------------------------------------- logique
def etat_initial():
    return {"cash": CAPITAL_DEPART, "positions": {}, "valeur": CAPITAL_DEPART, "maj": None}


def stop_touche(position, df):
    """(date, prix de sortie) si le stop a été touché depuis l'achat, sinon None."""
    achat = pd.Timestamp(position["date"])
    for date, b in df[df.index >= achat].iterrows():
        if b["Low"] <= position["stop"]:
            # Le jour de l'achat, l'ouverture précède l'achat : sortie au stop.
            return date, position["stop"] if date == achat else min(b["Open"], position["stop"])
    return None


def valeur(etat, prix):
    return etat["cash"] + sum(p["quantite"] * prix[nom] for nom, p in etat["positions"].items())


def vendre(etat, nom, prix, genre, aujourd_hui):
    p = etat["positions"].pop(nom)
    recette = p["quantite"] * prix * (1 - FRAIS_ORDRE)
    etat["cash"] += recette
    cout = p["quantite"] * p["prix_entree"] * (1 + FRAIS_ORDRE)
    return {"date": aujourd_hui, "marche": nom, "genre": genre, "quantite": p["quantite"],
            "prix": prix, "stop": p["stop"], "resultat": recette - cout}


def journee(etat, marche, aujourd_hui):
    """Une passe du bot. `marche` : {nom: (bougies terminées, prix actuel)}. Modifie `etat`."""
    operations = []
    voulu = {nom: s.regle_cassure(df).clip(lower=0).iloc[-1] for nom, (df, _) in marche.items()}

    for nom, (df, prix) in marche.items():
        position = etat["positions"].get(nom)
        if not position:
            continue
        touche = stop_touche(position, df)
        if touche:
            operations.append(vendre(etat, nom, touche[1], "stop", aujourd_hui))
        elif voulu[nom] == 0:
            operations.append(vendre(etat, nom, prix, "vente", aujourd_hui))

    total = valeur(etat, {nom: prix for nom, (_, prix) in marche.items()})
    for nom, (df, prix) in marche.items():
        if nom in etat["positions"] or voulu[nom] != 1:
            continue
        distance = s.K_STOP * float(s.atr(df).iloc[-1])
        montant = min(total * RISQUE * prix / distance, etat["cash"] / (1 + FRAIS_ORDRE))
        if montant < ORDRE_MIN:
            continue
        quantite = montant / prix
        etat["cash"] -= montant * (1 + FRAIS_ORDRE)
        etat["positions"][nom] = {"quantite": quantite, "prix_entree": prix, "stop": prix - distance,
                                  "date": aujourd_hui}
        operations.append({"date": aujourd_hui, "marche": nom, "genre": "achat", "quantite": quantite,
                           "prix": prix, "stop": prix - distance, "resultat": 0.0})

    etat["valeur"] = valeur(etat, {nom: prix for nom, (_, prix) in marche.items()})
    etat["maj"] = aujourd_hui
    return operations


def notification(op):
    nom, montant = op["marche"], op["quantite"] * op["prix"]
    if op["genre"] == "achat":
        return {"title": f"Bot : achat {nom} (papier)",
                "message": f"Acheté {s.eur(montant)} à {s.prix(op['prix'])} €\n"
                           f"Stop posé à {s.prix(op['stop'])} €", "tags": ["robot"]}
    quoi = "Stop touché" if op["genre"] == "stop" else "Tendance finie"
    return {"title": f"Bot : vente {nom} (papier)",
            "message": f"{quoi} : vendu à {s.prix(op['prix'])} €\n"
                       f"Résultat : {op['resultat']:+.2f} €", "tags": ["robot"]}


# ------------------------------------------------------------------------- main
def charger():
    if not os.path.exists(ETAT):
        return etat_initial()
    with open(ETAT, encoding="utf-8") as f:
        return json.load(f)


def enregistrer(etat, operations):
    with open(ETAT, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=2)
    nouveau = not os.path.exists(JOURNAL)
    with open(JOURNAL, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if nouveau:
            w.writerow(["date", "marche", "operation", "quantite", "prix", "stop", "resultat"])
        for op in operations:
            w.writerow([op["date"], op["marche"], op["genre"], f"{op['quantite']:.8g}",
                        f"{op['prix']:.8g}", f"{op['stop']:.8g}", f"{op['resultat']:.2f}"])


def main():
    argparse.ArgumentParser(description="Bot crypto Kraken, mode papier.").parse_args()
    etat = charger()
    marche = {}
    for nom, paire in PAIRES.items():
        try:
            marche[nom] = (bougies(paire), prix_actuel(paire))
        except Exception as exc:  # un marché en panne ne bloque pas les autres
            print(f"{nom} : données Kraken indisponibles ({exc}), ignoré aujourd'hui")
    aujourd_hui = dt.datetime.now(dt.timezone.utc).date().isoformat()
    operations = journee(etat, marche, aujourd_hui)
    enregistrer(etat, operations)

    for op in operations:
        print(f"{op['marche']:<9} {op['genre']:<6} {op['quantite']:.8g} à {s.prix(op['prix'])} € "
              f"(stop {s.prix(op['stop'])}) {op['resultat']:+.2f} €")
    print(f"Valeur du portefeuille papier : {etat['valeur']:.2f} € (départ {CAPITAL_DEPART:.0f} €), "
          f"liquidités {etat['cash']:.2f} €, positions : {', '.join(etat['positions']) or 'aucune'}")

    sujet = os.environ.get("NTFY_TOPIC", "").strip()
    for op in operations if sujet else []:
        try:
            s.envoyer(sujet, notification(op))
        except Exception as exc:
            print(f"Notification non envoyée : {exc}")


if __name__ == "__main__":
    main()
