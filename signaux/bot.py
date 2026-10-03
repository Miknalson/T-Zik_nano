"""Bot crypto : achète, vend et pose le stop tout seul, sur Kraken.

Méthode : cassure 20 jours en achat seulement (test_spot.py), entrée en cours permise, stop à
2 × ATR posé à l'achat, vente quand le cours clôture sous le plus bas des 10 derniers jours.
Bougies journalières et prix de Kraken (paires en euros). Lancé chaque jour juste après la
clôture de 00 h 00 UTC.

Trois modes :
- papier : ordres simulés au prix Kraken, frais compris, portefeuille fictif de 1 000 €
  (bot_portefeuille.json). Tourne toujours, sert de référence.
- verifier : vérifie la clé d'API (solde) et fait valider par Kraken un achat et un stop par
  crypto, sans rien exécuter (option « validate » de Kraken).
- reel : vrais ordres sur le compte, dans la limite d'un budget (bot_reel.json). Le stop est un
  vrai ordre stop-loss posé chez Kraken : il se déclenche même entre deux passages du bot.
"""
import argparse
import base64
import csv
import datetime as dt
import hashlib
import hmac
import json
import math
import os
import time
import urllib.parse
import urllib.request

import pandas as pd

import signaux as s

# Les 6 méthodes suivies + les 8 grosses cryptos retenues par test_kraken.py (03/10/2026).
PAIRES = {"Bitcoin": "XBTEUR", "Ethereum": "ETHEUR", "XRP": "XRPEUR",
          "Dogecoin": "XDGEUR", "Stellar": "XLMEUR", "VeChain": "VETEUR",
          "Solana": "SOLEUR", "BNB": "BNBEUR", "Tron": "TRXEUR", "Avalanche": "AVAXEUR",
          "NEAR": "NEAREUR", "Hedera": "HBAREUR", "Polkadot": "DOTEUR", "Algorand": "ALGOEUR"}
FRAIS_ORDRE = 0.004   # Kraken, ordre au marché, petit volume
RISQUE = 0.01         # un stop touché coûte 1 % du portefeuille
CAPITAL_DEPART = 1000.0
ORDRE_MIN = 5.0       # en dessous, Kraken refuse l'ordre
MAX_POSITIONS = 5     # cryptos tenues en même temps (variable GitHub BOT_MAX)
ELAN = 90             # jours : quand les places manquent, les plus fortes sur cette durée d'abord
DOSSIER = os.path.dirname(os.path.abspath(__file__))
ETAT = os.path.join(DOSSIER, "bot_portefeuille.json")
JOURNAL = os.path.join(DOSSIER, "bot_journal.csv")
ETAT_REEL = os.path.join(DOSSIER, "bot_reel.json")
JOURNAL_REEL = os.path.join(DOSSIER, "bot_reel_journal.csv")
ARRET = os.path.join(DOSSIER, "bot_arret.json")  # bouton « Bot : arrêter ou reprendre »
API = "https://api.kraken.com"


# ----------------------------------------------------------------------- Kraken
def kraken(chemin, **params):
    url = f"{API}/0/public/{chemin}?{urllib.parse.urlencode(params)}"
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


def signature(chemin, donnees, secret):
    """Signature des requêtes privées Kraken (HMAC-SHA512, voir la doc « Authentication »)."""
    corps = urllib.parse.urlencode(donnees)
    message = chemin.encode() + hashlib.sha256((str(donnees["nonce"]) + corps).encode()).digest()
    return base64.b64encode(hmac.new(base64.b64decode(secret), message, hashlib.sha512).digest()).decode()


class Kraken:
    """Accès privé au compte. La clé ne doit pas avoir le droit de retrait."""

    def __init__(self, cle, secret):
        self.cle, self.secret = cle, secret

    def appel(self, methode, **donnees):
        chemin = f"/0/private/{methode}"
        donnees = {"nonce": str(time.time_ns() // 1000), **donnees}
        requete = urllib.request.Request(
            API + chemin, data=urllib.parse.urlencode(donnees).encode(),
            headers={"API-Key": self.cle, "API-Sign": signature(chemin, donnees, self.secret),
                     "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(requete, timeout=30) as reponse:
            resultat = json.load(reponse)
        if resultat["error"]:
            raise RuntimeError(f"{methode} : {', '.join(resultat['error'])}")
        return resultat["result"]


def arrondi_bas(x, decimales):
    return math.floor(x * 10 ** decimales) / 10 ** decimales


# ------------------------------------------------------------------- courtiers
class Papier:
    """Ordres simulés : exécutés exactement au prix demandé, frais compris."""
    stops_chez_le_courtier = False

    def acheter(self, nom, quantite, prix, stop):
        return {"quantite": quantite, "prix": prix, "cout": quantite * prix * (1 + FRAIS_ORDRE)}

    def vendre(self, nom, position, prix):
        return {"prix": prix, "recette": position["quantite"] * prix * (1 - FRAIS_ORDRE)}

    def stop_execute(self, nom, position):
        return None


class Reel:
    """Vrais ordres Kraken. Le stop est un ordre stop-loss qui vit chez Kraken."""
    stops_chez_le_courtier = True

    def __init__(self, compte, infos_paires, attente=1.0):
        self.compte, self.infos, self.attente = compte, infos_paires, attente

    def _volume(self, paire, quantite):
        return f"{quantite:.{self.infos[paire]['lot_decimals']}f}"

    def _execution(self, txid):
        for _ in range(10):
            ordre = self.compte.appel("QueryOrders", txid=txid)[txid]
            if ordre["status"] == "closed":
                return ordre
            time.sleep(self.attente)
        raise RuntimeError(f"ordre {txid} pas exécuté")

    def _stop(self, paire, quantite, stop):
        prix_stop = f"{stop:.{self.infos[paire]['pair_decimals']}f}"
        return self.compte.appel("AddOrder", pair=paire, type="sell", ordertype="stop-loss",
                                 price=prix_stop, volume=self._volume(paire, quantite))["txid"][0]

    def acheter(self, nom, quantite, prix, stop):
        paire = PAIRES[nom]
        quantite = arrondi_bas(quantite, self.infos[paire]["lot_decimals"])
        if quantite < float(self.infos[paire]["ordermin"]):
            return None
        # « fciq » : frais payés en euros, on reçoit donc exactement la quantité achetée.
        try:
            txid = self.compte.appel("AddOrder", pair=paire, type="buy", ordertype="market",
                                     volume=self._volume(paire, quantite), oflags="fciq")["txid"][0]
        except RuntimeError as exc:  # fonds insuffisants, marché suspendu… : pas d'achat aujourd'hui
            print(f"{nom} : achat refusé par Kraken ({exc})")
            return None
        ordre = self._execution(txid)
        quantite = float(ordre["vol_exec"])
        return {"quantite": quantite, "prix": float(ordre["price"]),
                "cout": float(ordre["cost"]) + float(ordre["fee"]),
                "stop_txid": self._stop(paire, quantite, stop)}

    def vendre(self, nom, position, prix):
        paire = PAIRES[nom]
        self.compte.appel("CancelOrder", txid=position["stop_txid"])
        try:
            txid = self.compte.appel("AddOrder", pair=paire, type="sell", ordertype="market",
                                     volume=self._volume(paire, position["quantite"]))["txid"][0]
        except RuntimeError:
            # Ne jamais laisser une position sans stop.
            position["stop_txid"] = self._stop(paire, position["quantite"], position["stop"])
            raise
        ordre = self._execution(txid)
        return {"prix": float(ordre["price"]), "recette": float(ordre["cost"]) - float(ordre["fee"])}

    def stop_execute(self, nom, position):
        """Recette du stop s'il a été déclenché chez Kraken ; le repose s'il a disparu."""
        ordre = self.compte.appel("QueryOrders", txid=position["stop_txid"])[position["stop_txid"]]
        if ordre["status"] == "closed":
            return {"prix": float(ordre["price"]), "recette": float(ordre["cost"]) - float(ordre["fee"])}
        if ordre["status"] in ("canceled", "expired"):
            position["stop_txid"] = self._stop(PAIRES[nom], position["quantite"], position["stop"])
        return None


# ---------------------------------------------------------------------- logique
def etat_initial(capital=CAPITAL_DEPART):
    return {"cash": capital, "positions": {}, "valeur": capital, "maj": None, "depart": capital}


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


def cloturer(etat, nom, vente, genre, aujourd_hui):
    p = etat["positions"].pop(nom)
    etat["cash"] += vente["recette"]
    return {"date": aujourd_hui, "marche": nom, "genre": genre, "quantite": p["quantite"],
            "prix": vente["prix"], "stop": p["stop"], "resultat": vente["recette"] - p["cout"]}


def elan(df):
    """Hausse sur ELAN jours : sert à choisir les plus fortes quand les places manquent."""
    if len(df) <= ELAN:
        return float("-inf")
    return float(df["Close"].iloc[-1] / df["Close"].iloc[-1 - ELAN] - 1)


def journee(etat, marche, aujourd_hui, courtier=None, operations=None, achats=True, tout_vendre=False,
            max_positions=MAX_POSITIONS):
    """Une passe du bot. `marche` : {nom: (bougies terminées, prix actuel)}. Modifie `etat`.

    Les opérations sont ajoutées à `operations` au fur et à mesure : en cas d'erreur en cours
    de route, celles déjà exécutées restent connues de l'appelant. `achats=False` : bot à
    l'arrêt, il ne fait que gérer ses positions. `tout_vendre` : vend toutes les positions.
    Au plus `max_positions` cryptos en même temps : les plus fortes sur ELAN jours d'abord.
    """
    courtier = courtier or Papier()
    operations = [] if operations is None else operations
    voulu = {nom: s.regle_cassure(df).clip(lower=0).iloc[-1] for nom, (df, _) in marche.items()}

    for nom, (df, prix) in marche.items():
        position = etat["positions"].get(nom)
        if not position:
            continue
        if courtier.stops_chez_le_courtier:
            vente = courtier.stop_execute(nom, position)
        else:
            touche = stop_touche(position, df)
            vente = touche and {"prix": touche[1],
                                "recette": position["quantite"] * touche[1] * (1 - FRAIS_ORDRE)}
        if vente:
            operations.append(cloturer(etat, nom, vente, "stop", aujourd_hui))
        elif voulu[nom] == 0 or tout_vendre:
            operations.append(cloturer(etat, nom, courtier.vendre(nom, position, prix), "vente", aujourd_hui))

    total = valeur(etat, {nom: prix for nom, (_, prix) in marche.items()})
    candidats = [] if not achats or tout_vendre else sorted(
        (nom for nom in marche if nom not in etat["positions"] and voulu[nom] == 1),
        key=lambda nom: -elan(marche[nom][0]))
    for nom in candidats:
        if len(etat["positions"]) >= max_positions:
            break
        df, prix = marche[nom]
        distance = s.K_STOP * float(s.atr(df).iloc[-1])
        montant = min(total * RISQUE * prix / distance, total / max_positions, etat["cash"] / (1 + FRAIS_ORDRE))
        if montant < ORDRE_MIN:
            continue
        achat = courtier.acheter(nom, montant / prix, prix, prix - distance)
        if not achat:
            continue
        etat["cash"] -= achat["cout"]
        etat["positions"][nom] = {"quantite": achat["quantite"], "prix_entree": achat["prix"],
                                  "stop": prix - distance, "cout": achat["cout"], "date": aujourd_hui}
        if "stop_txid" in achat:
            etat["positions"][nom]["stop_txid"] = achat["stop_txid"]
        operations.append({"date": aujourd_hui, "marche": nom, "genre": "achat", "quantite": achat["quantite"],
                           "prix": achat["prix"], "stop": prix - distance, "resultat": 0.0})

    etat["valeur"] = valeur(etat, {nom: prix for nom, (_, prix) in marche.items()})
    etat["maj"] = aujourd_hui
    return operations


def notification(op, mode="papier"):
    nom, montant = op["marche"], op["quantite"] * op["prix"]
    if op["genre"] == "achat":
        return {"title": f"Bot : achat {nom} ({mode})",
                "message": f"Acheté {s.eur(montant)} à {s.prix(op['prix'])} €\n"
                           f"Stop posé à {s.prix(op['stop'])} €", "tags": ["robot"]}
    quoi = "Stop touché" if op["genre"] == "stop" else "Tendance finie"
    return {"title": f"Bot : vente {nom} ({mode})",
            "message": f"{quoi} : vendu à {s.prix(op['prix'])} €\n"
                       f"Résultat : {op['resultat']:+.2f} €", "tags": ["robot"]}


def verifier(compte, infos, prix):
    """Contrôle la clé et fait valider un achat et un stop minimaux par crypto, sans exécution."""
    solde = compte.appel("Balance")
    lignes = [f"Clé d'API valide. Euros disponibles : {float(solde.get('ZEUR', 0)):.2f} €"]
    for nom, paire in PAIRES.items():
        decimales = infos[paire]["lot_decimals"]
        quantite = max(float(infos[paire]["ordermin"]), ORDRE_MIN * 1.2 / prix[nom])
        volume = f"{math.ceil(quantite * 10 ** decimales) / 10 ** decimales:.{decimales}f}"
        stop = f"{prix[nom] * 0.9:.{infos[paire]['pair_decimals']}f}"
        try:
            compte.appel("AddOrder", pair=paire, type="buy", ordertype="market", volume=volume,
                         oflags="fciq", validate="true")
            compte.appel("AddOrder", pair=paire, type="sell", ordertype="stop-loss", price=stop,
                         volume=volume, validate="true")
            lignes.append(f"{nom} : achat et stop acceptés par Kraken (rien n'a été exécuté)")
        except Exception as exc:
            lignes.append(f"{nom} : REFUSÉ — {exc}")
    return lignes


# ------------------------------------------------------------------------- main
def charger(chemin, capital):
    if not os.path.exists(chemin):
        return etat_initial(capital)
    with open(chemin, encoding="utf-8") as f:
        etat = json.load(f)
    for p in etat["positions"].values():  # positions ouvertes avant l'ajout du coût
        p.setdefault("cout", p["quantite"] * p["prix_entree"] * (1 + FRAIS_ORDRE))
    return etat


def enregistrer(etat, operations, chemin_etat, chemin_journal):
    with open(chemin_etat, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, indent=2)
    nouveau = not os.path.exists(chemin_journal)
    with open(chemin_journal, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if nouveau:
            w.writerow(["date", "marche", "operation", "quantite", "prix", "stop", "resultat"])
        for op in operations:
            w.writerow([op["date"], op["marche"], op["genre"], f"{op['quantite']:.8g}",
                        f"{op['prix']:.8g}", f"{op['stop']:.8g}", f"{op['resultat']:.2f}"])


def est_arrete(chemin=ARRET):
    if not os.path.exists(chemin):
        return False
    with open(chemin, encoding="utf-8") as f:
        return json.load(f).get("arret", False)


def regler_arret(arret, chemin=ARRET):
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump({"arret": arret, "depuis": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}, f)


def ajuster_budget(etat, budget):
    """Suit la variable BOT_BUDGET : la différence avec l'ancien budget s'ajoute aux liquidités
    (ou s'en retire, sans descendre sous zéro : le bot n'achète alors plus rien)."""
    if budget > 0 and budget != etat.get("depart", budget):
        etat["cash"] = max(etat["cash"] + budget - etat.get("depart", budget), 0.0)
        etat["depart"] = budget


def passe(mode, marche, courtier, chemin_etat, chemin_journal, capital, sujet, achats=True, tout_vendre=False,
          max_positions=MAX_POSITIONS):
    etat = charger(chemin_etat, capital)
    if courtier.stops_chez_le_courtier:
        ajuster_budget(etat, capital)
    aujourd_hui = dt.datetime.now(dt.timezone.utc).date().isoformat()
    operations = []
    try:
        journee(etat, marche, aujourd_hui, courtier, operations, achats, tout_vendre, max_positions)
    finally:
        # En réel, ce qui a été exécuté avant une erreur doit rester enregistré.
        enregistrer(etat, operations, chemin_etat, chemin_journal)
    for op in operations:
        print(f"[{mode}] {op['marche']:<9} {op['genre']:<6} {op['quantite']:.8g} à {s.prix(op['prix'])} € "
              f"(stop {s.prix(op['stop'])}) {op['resultat']:+.2f} €")
    print(f"[{mode}] Valeur : {etat['valeur']:.2f} € (départ {etat.get('depart', capital):.0f} €), "
          f"liquidités {etat['cash']:.2f} €, positions : {', '.join(etat['positions']) or 'aucune'}")
    for op in operations if sujet else []:
        try:
            s.envoyer(sujet, notification(op, mode))
        except Exception as exc:
            print(f"Notification non envoyée : {exc}")


MESSAGES_COMMANDE = {
    "arreter": ("Bot : arrêté", "Plus aucun achat. Les positions gardent leur stop et seront vendues "
                                "quand la tendance finit. Bouton « Reprendre » pour relancer."),
    "tout-vendre": ("Bot : arrêté, tout vendu", "Toutes les positions ont été vendues. Plus aucun achat "
                                                "jusqu'au bouton « Reprendre »."),
    "reprendre": ("Bot : repris", "Le bot recommence à acheter dès le prochain passage de la nuit."),
}


def main():
    ap = argparse.ArgumentParser(description="Bot crypto Kraken.")
    ap.add_argument("--mode", choices=["papier", "verifier", "reel"], default="papier")
    ap.add_argument("--budget", type=float, default=0, help="mode reel : euros confiés au bot")
    ap.add_argument("--max-positions", default=str(MAX_POSITIONS),
                    help="cryptos tenues en même temps (variable BOT_MAX)")
    ap.add_argument("--commande", choices=list(MESSAGES_COMMANDE),
                    help="bouton d'arrêt : arreter, tout-vendre ou reprendre")
    args = ap.parse_args()
    sujet = os.environ.get("NTFY_TOPIC", "").strip()

    if args.commande in ("arreter", "reprendre"):
        regler_arret(args.commande == "arreter")
        titre, message = MESSAGES_COMMANDE[args.commande]
        print(f"{titre}. {message}")
        if sujet:
            s.envoyer(sujet, {"title": titre, "message": message, "tags": ["robot"]})
        return
    tout_vendre = args.commande == "tout-vendre"
    if tout_vendre:
        regler_arret(True)
    achats = not est_arrete()
    if not achats:
        print("Bot à l'arrêt : aucun achat, positions gérées jusqu'à leur vente.")

    marche = {}
    for nom, paire in PAIRES.items():
        try:
            marche[nom] = (bougies(paire), prix_actuel(paire))
        except Exception as exc:  # un marché en panne ne bloque pas les autres
            print(f"{nom} : données Kraken indisponibles ({exc}), ignoré aujourd'hui")

    try:
        max_positions = max(int(args.max_positions), 1)
    except ValueError:  # BOT_MAX mal tapé dans GitHub : on garde la valeur par défaut
        print(f"BOT_MAX = « {args.max_positions} » n'est pas un nombre : {MAX_POSITIONS} utilisé.")
        max_positions = MAX_POSITIONS
    passe("papier", marche, Papier(), ETAT, JOURNAL, CAPITAL_DEPART, sujet, achats, tout_vendre, max_positions)
    if args.mode == "papier":
        if tout_vendre and sujet:
            s.envoyer(sujet, {"title": MESSAGES_COMMANDE["tout-vendre"][0],
                              "message": MESSAGES_COMMANDE["tout-vendre"][1], "tags": ["robot"]})
        return

    cle = os.environ.get("KRAKEN_API_KEY", "").strip()
    secret = os.environ.get("KRAKEN_API_SECRET", "").strip()
    if not cle or not secret:
        raise SystemExit("KRAKEN_API_KEY et KRAKEN_API_SECRET doivent être dans les secrets GitHub.")
    compte = Kraken(cle, secret)
    infos = {v["altname"]: v for v in kraken("AssetPairs", pair=",".join(PAIRES.values())).values()}
    if args.mode == "verifier":
        lignes = verifier(compte, infos, {nom: p for nom, (_, p) in marche.items()})
        print("\n".join(lignes))
        if sujet:
            s.envoyer(sujet, {"title": "Bot : vérification Kraken", "message": "\n".join(lignes)})
        return
    if tout_vendre and not os.path.exists(ETAT_REEL):
        print("Aucune position réelle à vendre (le bot n'a jamais tourné en réel).")
        return
    if args.budget <= 0 and not tout_vendre:
        raise SystemExit("Mode reel : indique le budget confié au bot (variable BOT_BUDGET).")
    try:
        passe("réel", marche, Reel(compte, infos), ETAT_REEL, JOURNAL_REEL, args.budget, sujet,
              achats, tout_vendre, max_positions)
    except Exception as exc:
        if sujet:
            s.envoyer(sujet, {"title": "Bot : ERREUR (argent réel)", "priority": 5, "tags": ["warning"],
                              "message": f"{exc}\nVérifie tes positions dans Kraken."})
        raise
    if tout_vendre and sujet:
        s.envoyer(sujet, {"title": MESSAGES_COMMANDE["tout-vendre"][0],
                          "message": MESSAGES_COMMANDE["tout-vendre"][1], "tags": ["robot"]})


if __name__ == "__main__":
    main()
