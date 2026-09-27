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
    pos = pd.Series(1.0, index=df.index)
    assert s.p_valeur(pos.shift(1).fillna(0).values, df["Close"].pct_change().fillna(0).values) > s.P_MAX


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
