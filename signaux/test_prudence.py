"""Régressions : coûts, coupure chronologique et entrées non validées."""
import numpy as np
import pandas as pd
import signaux as s
import prudence as p
from test_validation import marche_plat, signal_achat_depuis, resultat
import page_bot


def test_financement_dernier_weekend():
    df = marche_plat()
    voulu = signal_achat_depuis(df, 20)
    voulu.iloc[24:] = 0
    x = s.executer(df, voulu, {'aller_retour': 0., 'financement_jour': .001})
    entree, sortie = [op[0] for op in x['operations']]
    jours = (df.index[sortie] - df.index[entree]).days
    assert abs(x['net'].sum() + jours * .001) < 1e-12


def test_aucune_entree_sans_validation():
    for action in ['ENTRER', 'EN COURS', 'INVERSER']:
        r = resultat('BTC-USD', 'Cassure 20 jours', action, position_sens=1)
        r['eval']['prudent']['valide'] = False
        titre, lignes, _ = s.consigne(r)
        assert 'Instrument :' not in ' '.join(lignes)
        messages = s.notifications([r])
        assert not messages if action != 'INVERSER' else messages[0]['title'].endswith('FERME (démo)')
    assert not p.autorisee({})


def test_sortie_conservee_sans_validation():
    r = resultat('BTC-USD', 'Cassure 20 jours', 'SORTIR', position_sens=1)
    r['eval']['prudent']['valide'] = False
    assert s.consigne(r)[0] == 'FERME ta position'
    assert s.notifications([r])[0]['title'].endswith('FERME (démo)')


def test_coupure_sans_position_heritee():
    df = marche_plat(600)
    voulu = pd.Series(1., index=df.index)
    resultat = p.controler(df, voulu, {'aller_retour': .01, 'financement_jour': .001},
                          {'valide': True, 'p': .00001})
    assert resultat['debut'] == str(df.index[420].date())
    assert resultat['trades'] == 1
    assert resultat['somme_rendements'] < 0 and not resultat['valide']
    assert resultat['stress'] < resultat['somme_rendements']


def test_incertitude_ne_fabrique_pas_un_gain():
    assert p.intervalle_blocs(np.zeros(200)) == [0., 0.]
    assert p.intervalle_blocs(np.ones(30)) is None
    a = p.intervalle_blocs(np.arange(200) / 10000)
    assert a == p.intervalle_blocs(np.arange(200) / 10000)


def test_bilan_inclut_depart_et_pertes():
    b = page_bot.bilan({'depart': 1000., 'valeur': 900., 'positions': {},
                       'historique': [{'valeur': 950.}, {'valeur': 1100.}, {'valeur': 800.}]},
                      [{'operation': 'vente', 'resultat': '10'}, {'operation': 'stop', 'resultat': '-20'}])
    assert abs(b['drawdown'] - (800 / 1100 - 1)) < 1e-12
    assert b['profit_factor'] == .5


if __name__ == '__main__':
    for nom, f in list(globals().items()):
        if nom.startswith('test_'):
            f()
            print('ok', nom)
