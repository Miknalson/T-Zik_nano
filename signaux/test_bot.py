"""Vérifie que le bot achète, pose le stop, vend et rachète exactement comme la méthode testée."""
import pandas as pd

import bot
import signaux as s


def marche_en_hausse(n_hausse=15):
    # 25 jours plats à 100, puis une hausse de 1 par jour : la cassure achète.
    close = [100.0] * 25 + [102.0 + i for i in range(n_hausse)]
    index = pd.date_range("2026-01-01", periods=len(close), freq="D")
    return pd.DataFrame({"Open": close, "High": [x + 1 for x in close],
                         "Low": [x - 1 for x in close], "Close": close}, index=index)


def lendemain(df, o, h, l, c):
    jour = df.index[-1] + pd.Timedelta(days=1)
    return pd.concat([df, pd.DataFrame({"Open": [o], "High": [h], "Low": [l], "Close": [c]}, index=[jour])])


def test_achat_avec_stop_et_taille_au_risque():
    df = marche_en_hausse()
    etat = bot.etat_initial()
    # max_positions=1 : seule la règle du risque limite la taille (pas le plafond d'1/N du portefeuille).
    [op] = bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10", max_positions=1)
    distance = s.K_STOP * float(s.atr(df).iloc[-1])
    assert op["genre"] == "achat" and op["prix"] == 117.0 and op["stop"] == 117.0 - distance
    montant = 1000 * bot.RISQUE * 117.0 / distance
    assert abs(op["quantite"] * 117.0 - montant) < 1e-9
    assert abs(etat["cash"] - (1000 - montant * (1 + bot.FRAIS_ORDRE))) < 1e-9
    # Le stop coûte bien environ 1 % du portefeuille.
    assert abs(op["quantite"] * distance - 10.0) < 1e-9


def test_deuxieme_passage_le_meme_jour_ne_rachete_pas():
    df = marche_en_hausse()
    etat = bot.etat_initial()
    bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10")
    assert bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10") == []


def test_stop_touche_puis_rachat_si_la_tendance_continue():
    df = marche_en_hausse()
    etat = bot.etat_initial()
    [achat] = bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10")
    # La bougie du 10/02 plonge sous le stop mais clôture encore au-dessus du plus bas des 10 jours.
    df2 = lendemain(df, 117.0, 118.0, achat["stop"] - 1, 116.0)
    df2.index = df2.index[:-1].append(pd.DatetimeIndex(["2026-02-10"]))
    vente, rachat = bot.journee(etat, {"Bitcoin": (df2, 116.5)}, "2026-02-11")
    assert vente["genre"] == "stop" and vente["prix"] == achat["stop"]
    assert rachat["genre"] == "achat" and rachat["prix"] == 116.5


def test_vente_quand_la_tendance_est_finie():
    df = marche_en_hausse()
    etat = bot.etat_initial()
    bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10")
    niveau = s.niveau_sortie(df, "Cassure 20 jours", 1)
    df2 = lendemain(df, 117.0, 117.5, niveau - 0.5, niveau - 0.1)  # clôture sous le plus bas des 10 jours
    df2.index = df2.index[:-1].append(pd.DatetimeIndex(["2026-02-10"]))
    etat["positions"]["Bitcoin"]["stop"] = niveau - 10  # stop assez loin pour ne pas être touché
    [vente] = bot.journee(etat, {"Bitcoin": (df2, niveau)}, "2026-02-11")
    assert vente["genre"] == "vente" and vente["prix"] == niveau
    assert "Bitcoin" not in etat["positions"]
    cout = vente["quantite"] * 117.0 * (1 + bot.FRAIS_ORDRE)
    assert abs(vente["resultat"] - (vente["quantite"] * niveau * (1 - bot.FRAIS_ORDRE) - cout)) < 1e-9


def test_rien_sans_tendance():
    close = [100.0] * 40
    index = pd.date_range("2026-01-01", periods=40, freq="D")
    df = pd.DataFrame({"Open": close, "High": 101.0, "Low": 99.0, "Close": close}, index=index)
    etat = bot.etat_initial()
    assert bot.journee(etat, {"Bitcoin": (df, 100.0)}, "2026-02-10") == []
    assert etat["cash"] == 1000.0 and etat["valeur"] == 1000.0


def test_notifications():
    achat = {"marche": "Bitcoin", "genre": "achat", "quantite": 0.001, "prix": 72000.0, "stop": 68000.0,
             "resultat": 0.0}
    assert bot.notification(achat) == {"title": "Bot : achat Bitcoin (papier)",
                                       "message": "Acheté 72 € à 72 000 €\nStop posé à 68 000 €",
                                       "tags": ["robot"]}
    stop = dict(achat, genre="stop", prix=68000.0, resultat=-4.29)
    assert bot.notification(stop)["message"] == "Stop touché : vendu à 68 000 €\nRésultat : -4.29 €"


def test_a_l_arret_le_bot_n_achete_plus_mais_gere_ses_positions():
    df = marche_en_hausse()
    etat = bot.etat_initial()
    assert bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10", achats=False) == []
    assert etat["positions"] == {}
    bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10")
    niveau = s.niveau_sortie(df, "Cassure 20 jours", 1)
    df2 = lendemain(df, 117.0, 117.5, niveau - 0.5, niveau - 0.1)
    etat["positions"]["Bitcoin"]["stop"] = niveau - 10
    [vente] = bot.journee(etat, {"Bitcoin": (df2, niveau)}, "2026-02-11", achats=False)
    assert vente["genre"] == "vente"


def test_tout_vendre_vend_tout_et_ne_rachete_pas():
    df = marche_en_hausse()
    compte = FauxCompte()
    etat = bot.etat_initial(200.0)
    courtier = bot.Reel(compte, INFOS, attente=0)
    bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10", courtier)
    [vente] = bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10", courtier, tout_vendre=True)
    assert vente["genre"] == "vente" and etat["positions"] == {}
    assert compte.ordres["O2"]["status"] == "canceled"  # le stop chez Kraken est annulé
    assert [m for m, _ in compte.appels[-4:]] == ["QueryOrders", "CancelOrder", "AddOrder", "QueryOrders"]
    assert compte.appels[-2][1]["type"] == "sell" and compte.appels[-2][1]["ordertype"] == "market"


def test_changer_le_budget_ajoute_ou_retire_des_liquidites():
    etat = bot.etat_initial(100.0)
    etat["cash"] = 40.0  # 60 € déjà investis
    bot.ajuster_budget(etat, 150.0)
    assert etat["cash"] == 90.0 and etat["depart"] == 150.0
    bot.ajuster_budget(etat, 150.0)
    assert etat["cash"] == 90.0
    bot.ajuster_budget(etat, 50.0)  # moins que ce qui est investi : plus d'achats
    assert etat["cash"] == 0.0 and etat["depart"] == 50.0


def test_au_plus_max_positions_et_les_plus_fortes_d_abord():
    lente = marche_en_hausse()
    # Même cassure mais hausse plus forte : son élan sur 90 jours est plus grand.
    forte = lente.copy()
    forte[["Open", "High", "Low", "Close"]] = forte[["Open", "High", "Low", "Close"]] * 1.0
    forte.iloc[-15:, :] = forte.iloc[-15:, :] * 1.5
    longues = {nom: pd.concat([lente.iloc[:1].reindex(pd.date_range("2025-09-01", periods=100, freq="D"),
                                                       method="ffill").fillna(100.0), df])
               for nom, df in {"Lente": lente, "Forte": forte}.items()}
    marche = {"Bitcoin": (longues["Lente"], 117.0), "Ethereum": (longues["Forte"], 175.5)}
    etat = bot.etat_initial()
    [achat] = bot.journee(etat, marche, "2026-02-10", max_positions=1)
    assert achat["marche"] == "Ethereum" and list(etat["positions"]) == ["Ethereum"]
    assert bot.journee(etat, marche, "2026-02-10", max_positions=1) == []  # plus de place
    bot.journee(etat, marche, "2026-02-10", max_positions=2)
    assert set(etat["positions"]) == {"Bitcoin", "Ethereum"}


def test_une_position_ne_depasse_pas_sa_part_du_portefeuille():
    df = marche_en_hausse()
    etat = bot.etat_initial()
    [achat] = bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10", max_positions=20)
    assert achat["quantite"] * achat["prix"] <= 1000 / 20 + 1e-9


def test_historique_un_point_par_jour_et_prix_actuel():
    df = marche_en_hausse()
    etat = bot.etat_initial()
    bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10")
    bot.journee(etat, {"Bitcoin": (df, 118.0)}, "2026-02-10")
    assert [h["date"] for h in etat["historique"]] == ["2026-02-10"]
    assert etat["positions"]["Bitcoin"]["prix_actuel"] == 118.0
    bot.journee(etat, {"Bitcoin": (df, 119.0)}, "2026-02-11")
    assert [h["date"] for h in etat["historique"]] == ["2026-02-10", "2026-02-11"]
    assert etat["historique"][-1]["valeur"] == round(etat["valeur"], 2)


def test_valeur_garde_le_dernier_prix_si_kraken_ne_repond_pas():
    df = marche_en_hausse()
    etat = bot.etat_initial()
    bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10")
    assert bot.journee(etat, {}, "2026-02-11") == []  # aucune donnée : pas de plantage
    assert abs(etat["valeur"] - bot.valeur(etat, {"Bitcoin": 117.0})) < 1e-9


def test_page_du_bot():
    import json, os, tempfile
    import page_bot
    dossier = tempfile.mkdtemp()
    etat = {"cash": 900.0, "valeur": 1012.5, "maj": "2026-10-04", "depart": 1000.0,
            "historique": [{"date": "2026-10-03", "valeur": 998.0}, {"date": "2026-10-04", "valeur": 1012.5}],
            "positions": {"Solana": {"quantite": 1.0, "prix_entree": 100.0, "prix_actuel": 112.5, "stop": 90.0,
                                     "cout": 100.4, "date": "2026-10-03"}}}
    with open(os.path.join(dossier, "bot_portefeuille.json"), "w") as f:
        json.dump(etat, f)
    with open(os.path.join(dossier, "bot_journal.csv"), "w") as f:
        f.write("date;marche;operation;quantite;prix;stop;resultat\n"
                "2026-10-03;Bitcoin;achat;0.001;70000;66000;0.00\n"
                "2026-10-03;Bitcoin;stop;0.001;66000;66000;-4.56\n"
                "2026-10-03;Solana;achat;1;100;90;0.00\n")
    sortie = os.path.join(dossier, "bot.html")
    page_bot.ecrire(sortie, dossier)
    page = open(sortie, encoding="utf-8").read()
    nb = " "
    assert f"1{nb}012,50{nb}€" in page and f"▲ +12,50{nb}€ (+1,25{nb}%)" in page
    assert f"▼ −4,56{nb}€" in page and "Stop touché" in page   # perte réalisée
    assert f"▲ +12,10{nb}€" in page                          # gain en cours sur Solana
    assert "1 sur 1" not in page and "0 sur 1" in page        # ventes gagnantes
    assert "Réel" not in page.split("<main>")[1].split("</main>")[0]  # pas de section réelle sans fichier
    assert "<polyline" in page


def test_interrupteur_d_arret():
    import tempfile, os
    chemin = os.path.join(tempfile.mkdtemp(), "arret.json")
    assert not bot.est_arrete(chemin)
    bot.regler_arret(True, chemin)
    assert bot.est_arrete(chemin)
    bot.regler_arret(False, chemin)
    assert not bot.est_arrete(chemin)


def test_signature_kraken_exemple_de_la_documentation():
    secret = "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3pd5nE9qa99HAZtuZuj6F1huXg=="
    donnees = {"nonce": "1616492376594", "ordertype": "limit", "pair": "XBTUSD", "price": "37500",
               "type": "buy", "volume": "1.25"}
    assert bot.signature("/0/private/AddOrder", donnees, secret) == (
        "4/dpxb3iT4tp/ZCVEwSnEsLxx0bqyhLpdfOpc6fn7OR8+UClSV5n9E6aSS8MPtnRfp32bAb0nmbRn6H8ndwLUQ==")


INFOS = {"XBTEUR": {"lot_decimals": 8, "pair_decimals": 1, "ordermin": "0.00005"}}


class FauxCompte:
    """Imite l'API privée Kraken : enregistre les appels, exécute les ordres au marché."""

    def __init__(self, prix=117.0, refuser=()):
        self.appels, self.ordres, self.prix, self.refuser = [], {}, prix, set(refuser)

    def appel(self, methode, **donnees):
        self.appels.append((methode, donnees))
        if (methode, donnees.get("ordertype")) in self.refuser:
            raise RuntimeError(f"{methode} : EOrder:Insufficient funds")
        if methode == "AddOrder":
            txid = f"O{len(self.ordres) + 1}"
            vol = float(donnees["volume"])
            if donnees["ordertype"] == "market":
                cout = vol * self.prix
                self.ordres[txid] = {"status": "closed", "vol_exec": donnees["volume"], "price": str(self.prix),
                                     "cost": str(cout), "fee": str(cout * 0.004)}
            else:
                self.ordres[txid] = {"status": "open"}
            return {"txid": [txid]}
        if methode == "QueryOrders":
            return {donnees["txid"]: self.ordres[donnees["txid"]]}
        if methode == "CancelOrder":
            self.ordres[donnees["txid"]]["status"] = "canceled"
            return {"count": 1}
        raise AssertionError(methode)


def test_reel_achete_au_marche_puis_pose_un_vrai_stop():
    df = marche_en_hausse()
    compte = FauxCompte()
    etat = bot.etat_initial(200.0)
    [op] = bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10", bot.Reel(compte, INFOS, attente=0))
    (m1, achat), (m2, _), (m3, stop) = compte.appels
    assert (m1, m2, m3) == ("AddOrder", "QueryOrders", "AddOrder")
    assert achat["type"] == "buy" and achat["ordertype"] == "market" and achat["oflags"] == "fciq"
    assert "e" not in achat["volume"] and len(achat["volume"].split(".")[1]) == 8
    assert stop["type"] == "sell" and stop["ordertype"] == "stop-loss" and stop["volume"] == achat["volume"]
    assert stop["price"] == f"{op['stop']:.1f}"
    position = etat["positions"]["Bitcoin"]
    assert position["stop_txid"] == "O2"
    vol = float(achat["volume"])
    assert abs(etat["cash"] - (200 - vol * 117 * 1.004)) < 1e-9


def test_reel_stop_execute_chez_kraken_puis_rachat():
    df = marche_en_hausse()
    compte = FauxCompte()
    etat = bot.etat_initial(200.0)
    courtier = bot.Reel(compte, INFOS, attente=0)
    bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10", courtier)
    vol = etat["positions"]["Bitcoin"]["quantite"]
    compte.ordres["O2"] = {"status": "closed", "price": "110.0", "cost": str(vol * 110), "fee": str(vol * 110 * 0.004)}
    vente, rachat = bot.journee(etat, {"Bitcoin": (df, 116.0)}, "2026-02-11", courtier)
    assert vente["genre"] == "stop" and vente["prix"] == 110.0
    assert rachat["genre"] == "achat" and etat["positions"]["Bitcoin"]["stop_txid"] == "O4"


def test_reel_repose_le_stop_s_il_a_disparu():
    df = marche_en_hausse()
    compte = FauxCompte()
    etat = bot.etat_initial(200.0)
    courtier = bot.Reel(compte, INFOS, attente=0)
    bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10", courtier)
    compte.ordres["O2"]["status"] = "canceled"
    assert bot.journee(etat, {"Bitcoin": (df, 118.0)}, "2026-02-11", courtier) == []
    assert etat["positions"]["Bitcoin"]["stop_txid"] == "O3"
    assert compte.appels[-1][1]["ordertype"] == "stop-loss"


def test_reel_vente_refusee_remet_le_stop():
    df = marche_en_hausse()
    compte = FauxCompte()
    etat = bot.etat_initial(200.0)
    courtier = bot.Reel(compte, INFOS, attente=0)
    bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10", courtier)
    position = etat["positions"]["Bitcoin"]
    compte.refuser.add(("AddOrder", "market"))
    try:
        courtier.vendre("Bitcoin", position, 116.0)
        raise AssertionError("la vente aurait dû échouer")
    except RuntimeError:
        pass
    assert compte.ordres["O2"]["status"] == "canceled" and position["stop_txid"] == "O3"


def test_reel_achat_refuse_ne_change_rien():
    df = marche_en_hausse()
    compte = FauxCompte(refuser=[("AddOrder", "market")])
    etat = bot.etat_initial(200.0)
    assert bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10", bot.Reel(compte, INFOS, attente=0)) == []
    assert etat["cash"] == 200.0 and etat["positions"] == {}


def test_erreur_en_cours_de_route_garde_les_operations_deja_faites():
    df = marche_en_hausse()
    compte = FauxCompte()
    etat = bot.etat_initial(1000.0)
    courtier = bot.Reel(compte, {**INFOS, "ETHEUR": INFOS["XBTEUR"]}, attente=0)
    bot.journee(etat, {"Bitcoin": (df, 117.0), "Ethereum": (df, 117.0)}, "2026-02-10", courtier)
    vol = etat["positions"]["Bitcoin"]["quantite"]
    stop_btc, stop_eth = etat["positions"]["Bitcoin"]["stop_txid"], etat["positions"]["Ethereum"]["stop_txid"]
    compte.ordres[stop_btc] = {"status": "closed", "price": "110.0", "cost": str(vol * 110), "fee": "0"}
    del compte.ordres[stop_eth]  # Kraken ne trouve plus l'ordre : erreur au 2e marché
    operations = []
    try:
        bot.journee(etat, {"Bitcoin": (df, 117.0), "Ethereum": (df, 117.0)}, "2026-02-11", courtier, operations)
        raise AssertionError("une erreur était attendue")
    except KeyError:
        pass
    assert [op["genre"] for op in operations] == ["stop"] and "Bitcoin" not in etat["positions"]


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
            print("ok", nom)
