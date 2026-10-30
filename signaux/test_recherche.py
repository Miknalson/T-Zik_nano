"""Prix synthétiques pour vérifier le moteur, jamais pour estimer la rentabilité."""
import numpy as np
import pandas as pd
import recherche_trading as r


def donnees():
    index = pd.date_range('2019-01-01', '2025-12-31')
    c = 100 * np.exp(np.cumsum(np.random.default_rng(12).normal(.0006, .018, len(index))))
    return {'Bitcoin': pd.DataFrame({'Open': c, 'High': c * 1.02, 'Low': c * .98, 'Close': c}, index=index)}


def test_pas_de_futur():
    d = donnees(); t, noms, dates = r.enrichir(d)
    limite = pd.Timestamp('2024-01-01')
    tronque = {n: df.loc[:limite] for n, df in d.items()}
    a, _, jours = r.enrichir(tronque)
    for k in t:
        np.testing.assert_allclose(t[k][:len(jours)], a[k], equal_nan=True)
    x = r.simuler(t, noms, dates, pd.Timestamp('2021-01-01'), limite, {}, commission=.004)
    y = r.simuler(a, noms, jours, pd.Timestamp('2021-01-01'), limite, {}, commission=.004)
    assert x == y


def test_capital_et_couts():
    t, noms, dates = r.enrichir(donnees())
    periode = (pd.Timestamp('2021-01-01'), pd.Timestamp('2025-12-31'))
    x = r.simuler(t, noms, dates, *periode, {})
    assert x['capital_final'] > 0 and x['achats'] == x['clotures']
    assert x['couts_estimes'] > 0 and -1 < x['drawdown'] <= 0
    # Sans signal d'entrée : capital strictement inchangé, aucun faux rendement.
    t['voulu'] = np.zeros_like(t['voulu'])
    y = r.simuler(t, noms, dates, *periode, {})
    assert y['capital_final'] == 1000 and y['achats'] == 0 and y['couts_estimes'] == 0


def test_selection_independante_du_final():
    d = donnees(); a = r.comparer(d)
    for df in d.values():
        df.loc['2023-01-01':, ['Open', 'High', 'Low', 'Close']] *= 2
    b = r.comparer(d)
    assert a['choisi_sur_selection'] == b['choisi_sur_selection']
    for k in r.VARIANTES:
        assert a['variantes'][k]['selection'] == b['variantes'][k]['selection']
    assert a['production_activee'] is False


if __name__ == '__main__':
    for nom, f in list(globals().items()):
        if nom.startswith('test_'):
            f(); print('ok', nom)
