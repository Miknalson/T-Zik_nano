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
    [op] = bot.journee(etat, {"Bitcoin": (df, 117.0)}, "2026-02-10")
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


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
            print("ok", nom)
