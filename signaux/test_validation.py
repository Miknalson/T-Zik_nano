"""Vérifie que le filtre de fiabilité rejette le bruit et reconnaît un vrai avantage."""
import numpy as np
import pandas as pd

import signaux as s

FRAIS_TEST = s.FRAIS["indice"]


def serie(rendements, graine):
    rng = np.random.default_rng(graine)
    close = 100 * np.exp(np.cumsum(rendements))
    ecart = np.abs(rng.normal(0, 0.008, len(close))) * close
    index = pd.bdate_range("2012-01-02", periods=len(close))
    return pd.DataFrame({"Open": close, "High": close + ecart, "Low": close - ecart, "Close": close}, index=index)


def marche_aleatoire(graine, n=2500):
    return serie(np.random.default_rng(graine).normal(0, 0.012, n), graine)


def marche_a_tendances(graine, n=2500, duree=80, derive=0.0025):
    # Des régimes haussiers/baissiers durables : exactement ce qu'une règle de
    # tendance doit capter si elle fonctionne.
    rng = np.random.default_rng(graine)
    sens = np.repeat(rng.choice([-1, 1], n // duree + 1), duree)[:n]
    return serie(sens * derive + rng.normal(0, 0.012, n), graine)


def test_bruit_rejete():
    valides = sum(
        s.evaluer(df, regle(df), FRAIS_TEST)["valide"]
        for g in range(40)
        for df in [marche_aleatoire(g)]
        for regle in s.REGLES.values()
    )
    # 120 tests sur du pur hasard : on tolère au plus 2 faux positifs.
    assert valides <= 2, f"{valides} règles validées sur du bruit"


def test_avantage_reel_reconnu():
    valides = sum(s.evaluer(df, s.regle_cassure(df), FRAIS_TEST)["valide"]
                  for g in range(10) for df in [marche_a_tendances(g)])
    assert valides >= 8, f"seulement {valides}/10 marchés à tendance reconnus"


def test_position_toujours_identique_rejetee():
    df = marche_a_tendances(0)
    assert s.evaluer(df, pd.Series(1.0, index=df.index), FRAIS_TEST)["p"] > s.P_MAX


def marche_plat(n=40):
    # Cours à 100, séances de 99 à 101 : ATR = 2, donc stop à 2 × 2 = 4 points.
    index = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0}, index=index)


def signal_achat_depuis(df, i):
    voulu = pd.Series(0.0, index=df.index)
    voulu.iloc[i:] = 1
    return voulu


SANS_FRAIS = {"aller_retour": 0.0, "financement_jour": 0.0}


def marche_qui_monte_a_103():
    # Signal à la clôture 24 ; à partir de la séance 25, le cours tourne autour de 103.
    df = marche_plat()
    df.iloc[25:] = [103.0, 104.0, 102.0, 103.0]
    return df


def test_entree_a_l_ouverture_suivante_et_stop_au_bon_prix():
    df = marche_qui_monte_a_103()
    df.iloc[27, df.columns.get_loc("Low")] = 90.0       # plonge sous le stop
    x = s.executer(df, signal_achat_depuis(df, 24), SANS_FRAIS)
    assert x["operations"][0] == (25, "entree", 1.0, 103.0)
    assert x["operations"][1] == (27, "stop", 1.0, 99.0)  # 103 - 2 × ATR(2)
    assert abs(x["net"].sum() - (99 / 103 - 1)) < 1e-4
    assert x["sens"] == 0 and len(x["operations"]) == 2  # pas de nouvelle entrée sans nouveau signal


def test_gap_sous_le_stop_execute_a_l_ouverture():
    df = marche_qui_monte_a_103()
    df.iloc[27] = [95.0, 96.0, 90.0, 92.0]
    x = s.executer(df, signal_achat_depuis(df, 24), SANS_FRAIS)
    assert x["operations"][1] == (27, "stop", 1.0, 95.0)


def test_entree_en_cours_reprend_le_lendemain_du_stop():
    df = marche_qui_monte_a_103()
    df.iloc[27, df.columns.get_loc("Low")] = 90.0
    x = s.executer(df, signal_achat_depuis(df, 24), SANS_FRAIS, en_cours=True)
    assert x["operations"][:3] == [(25, "entree", 1.0, 103.0), (27, "stop", 1.0, 99.0),
                                   (28, "entree", 1.0, 103.0)]


def test_sortie_a_l_ouverture_quand_le_signal_s_arrete():
    df = marche_plat()
    voulu = signal_achat_depuis(df, 24)
    voulu.iloc[30:] = 0
    df.iloc[31, df.columns.get_loc("Open")] = 100.5
    x = s.executer(df, voulu, SANS_FRAIS)
    assert x["operations"][-1] == (31, "sortie", 1.0, 100.5)
    c = s.conseil_du_jour(df.iloc[:31], voulu.iloc[:31],
                          s.executer(df.iloc[:31], voulu.iloc[:31], SANS_FRAIS), 1000, 1)
    assert c["action"] == "SORTIR"


def test_suivi_ne_compte_que_depuis_le_debut():
    df = marche_qui_monte_a_103()
    df.iloc[27, df.columns.get_loc("Low")] = 90.0
    x = s.executer(df, signal_achat_depuis(df, 24), SANS_FRAIS)
    apres_le_trade = s.suivi_depuis(df, x, SANS_FRAIS, debut=df.index[30])
    avant_le_trade = s.suivi_depuis(df, x, SANS_FRAIS, debut=df.index[20])
    assert apres_le_trade == {"trades": 0, "resultat": 0.0, "commence": True}
    assert avant_le_trade["trades"] == 1 and abs(avant_le_trade["resultat"] - (99 / 103 - 1)) < 1e-9
    assert not s.suivi_depuis(df, x, SANS_FRAIS, debut=df.index[-1] + pd.Timedelta(days=1))["commence"]


def test_suivi_ignore_une_position_ouverte_avant_le_debut():
    df = marche_qui_monte_a_103()
    x = s.executer(df, signal_achat_depuis(df, 24), SANS_FRAIS)  # entrée en 25, jamais sortie
    assert s.suivi_depuis(df, x, SANS_FRAIS, debut=df.index[26])["trades"] == 0
    encore_ouvert = s.suivi_depuis(df, x, SANS_FRAIS, debut=df.index[25])
    assert encore_ouvert["trades"] == 1 and encore_ouvert["resultat"] == 0.0  # 103 → 103


def resultat(ticker, regle, action, sens=1, position_sens=0):
    conseil = {"action": action, "orientation": sens, "sens": sens, "position_sens": position_sens,
               "cloture": 84914.6, "stop_estime": 81745.2, "nominal": 150.7, "stop_pct": 0.0664}
    return {"ticker": ticker, "nom": "Bitcoin", "regle": regle, "erreur": None, "conseil": conseil}


def test_notification_entrer_reprend_les_cases_libertex():
    [m] = s.notifications([resultat("BTC-USD", "Cassure 20 jours", "ENTRER")])
    assert m["title"] == "Bitcoin : ACHÈTE (démo)"
    assert m["message"].startswith(
        "Instrument : BTCUSD\n"
        "Direction : Acheter\n"
        "Montant : 75 €\n"
        "Multiplicateur : ×2\n"
        "Take Profit : laisser vide\n"
        "Stop Loss : 81 745 (≈ −10 € si touché)\n"
        "Prix de référence : 84 915\n")
    assert "notification FERME" in m["message"]


def test_notification_vente():
    [m] = s.notifications([resultat("BTC-USD", "Cassure 20 jours", "ENTRER", sens=-1)])
    assert m["title"] == "Bitcoin : VENDS (démo)" and "Direction : Vendre" in m["message"]


def test_notification_inverser_ferme_puis_ouvre():
    [m] = s.notifications([resultat("BTC-USD", "Cassure 20 jours", "INVERSER", sens=-1, position_sens=1)])
    assert m["message"].startswith("1) Ferme ta position ACHAT")
    assert "2) Nouvel ordre :\nInstrument : BTCUSD\nDirection : Vendre" in m["message"]


def test_pas_de_notification_hors_methode_suivie_ou_sans_action():
    assert s.notifications([resultat("BTC-USD", "Tendance (moyennes 50/200)", "ENTRER")]) == []
    assert s.notifications([resultat("BTC-USD", "Cassure 20 jours", "EN COURS")]) == []
    assert s.notifications([resultat("BTC-USD", "Cassure 20 jours", "RIEN", sens=0)]) == []


def test_notification_sortir():
    [m] = s.notifications([resultat("BTC-USD", "Cassure 20 jours", "SORTIR", sens=1, position_sens=1)])
    assert m["title"] == "Bitcoin : FERME (démo)"
    assert m["message"] == "Ferme ta position ACHAT : onglet « Actif » → ta position BTCUSD → « Fermer »"


def test_methodes_suivies_existent():
    marches = {t for t, _, _ in s.MARCHES}
    assert all(t in marches and regle in s.REGLES for t, regle in s.METHODE_SUIVIE.items())
    assert set(s.NOM_LIBERTEX) == set(s.METHODE_SUIVIE)


def test_journee_crypto_manquante_reconstituee_depuis_les_barres_horaires():
    quotidien = pd.DataFrame({"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0], "Close": [1.0, 2.0]},
                             index=pd.to_datetime(["2026-09-25", "2026-09-26"]))
    aujourd_hui = pd.Timestamp("2026-09-28")
    manquants = s.jours_crypto_manquants(quotidien, aujourd_hui)
    assert manquants == [pd.Timestamp("2026-09-27")]

    heures = pd.date_range("2026-09-27 00:00", "2026-09-28 05:00", freq="h", tz="UTC")
    prix = np.arange(len(heures), dtype=float) + 100
    horaire = pd.DataFrame({"Open": prix, "High": prix + 5, "Low": prix - 5, "Close": prix + 1}, index=heures)
    ajout = s.barres_journalieres(horaire, manquants + [aujourd_hui])
    assert list(ajout.index) == [pd.Timestamp("2026-09-27")]  # le 28, incomplet, est laissé de côté
    jour = ajout.iloc[0]
    assert (jour["Open"], jour["High"], jour["Low"], jour["Close"]) == (100, 128, 95, 124)


def test_rien_a_reconstituer_quand_hier_est_publie():
    quotidien = pd.DataFrame({"Close": [1.0, 2.0]}, index=pd.to_datetime(["2026-09-26", "2026-09-27"]))
    assert s.jours_crypto_manquants(quotidien, pd.Timestamp("2026-09-28")) == []


def test_journal_renvoie_seulement_les_nouvelles_clotures():
    import tempfile, os
    r = {"erreur": None, "date_cloture": pd.Timestamp("2026-09-27"), "ticker": "BTC-USD",
         "regle": "Cassure 20 jours", "eval": {"valide": False},
         "conseil": {"action": "ENTRER", "sens": 1, "cloture": 1.0, "stop_estime": 0.9, "stop_position": 0}}
    chemin = os.path.join(tempfile.mkdtemp(), "journal.csv")
    assert s.journaliser([r], chemin) == {("2026-09-27", "BTC-USD", "Cassure 20 jours")}
    assert s.journaliser([r], chemin) == set()  # 2e passage du matin : pas de nouvelle notification


def test_conseil_entrer_sur_nouveau_signal():
    df = marche_plat()
    voulu = signal_achat_depuis(df, len(df) - 1)
    c = s.conseil_du_jour(df, voulu, s.executer(df, voulu, SANS_FRAIS), 1000, 1)
    assert c["action"] == "ENTRER" and c["sens"] == 1
    assert abs(c["stop_pct"] - 0.04) < 1e-9 and abs(c["nominal"] - 250) < 1e-6  # 10 € / 4 %


def test_aucune_regle_ne_voit_le_futur():
    df = marche_aleatoire(1)
    for regle in s.REGLES.values():
        complet = regle(df)
        tronque = regle(df.iloc[:-50])
        pd.testing.assert_series_equal(complet.iloc[:-50], tronque, check_names=False)


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
            print("ok", nom)
