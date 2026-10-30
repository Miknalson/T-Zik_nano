"""Comparaison exploratoire de portefeuilles, sans modifier ni appeler le bot.

Choix de variante sur 2021-2022 seulement ; test descriptif 2023 à hier UTC.
Les résultats 2023+ ont déjà été étudiés dans ce dépôt : ce n'est pas un test prospectif.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import signaux as s
from test_portefeuille import UNIVERS, preparer

VARIANTES = {
    'reference': {'label': 'Bot actuel · filtre Bitcoin 200 j'},
    'cassure_neuve': {'label': 'Nouvelle cassure uniquement', 'neuve': True},
    'pause_5j': {'label': 'Pause de 5 jours après un stop', 'pause': 5},
    'tendance_actif': {'label': 'Actif au-dessus de sa moyenne 200 j', 'actif': True},
    'tendance_neuve': {'label': 'Tendance de l’actif + nouvelle cassure', 'actif': True, 'neuve': True},
}
CAPITAL = 1000.


def simuler(t, noms, dates, debut, fin, options, commission=.004, glissement=.001):
    o, h, l, c = [t[k] for k in ['Open', 'High', 'Low', 'Close']]
    cash, positions, courbe, sorties, achats, couts = CAPITAL, {}, [], [], 0, 0.
    pause = {}
    dernier = np.full(len(noms), np.nan)

    def vendre(j, prix, jour, stop=False):
        nonlocal cash, couts
        q, seuil, cout = positions.pop(j)
        prix_net = prix * (1 - glissement)
        frais = q * prix_net * commission
        recette = q * prix_net - frais
        cash += recette
        couts += frais + q * prix * glissement
        sorties.append(recette - cout)
        if stop:
            pause[j] = jour + pd.Timedelta(days=options.get('pause', 0))

    for i, jour in enumerate(dates):
        if jour < debut:
            dernier = np.where(np.isfinite(c[i]), c[i], dernier)
            continue
        if jour > fin:
            break
        for j in list(positions):
            if np.isfinite(o[i, j]) and t['voulu'][i, j] == 0:
                vendre(j, o[i, j], jour)
        valeur = cash + sum(p[0] * (o[i, j] if np.isfinite(o[i, j]) else dernier[j]) for j, p in positions.items())
        candidats = [j for j in range(len(noms)) if j not in positions
                     and t['voulu'][i, j] == 1 and t['marche'][i] == 1
                     and np.isfinite(o[i, j]) and o[i, j] > 0
                     and np.isfinite(t['atr'][i, j]) and t['atr'][i, j] > 0
                     and np.isfinite(t['elan'][i, j])
                     and (not options.get('neuve') or (i > 0 and t['voulu'][i - 1, j] != 1))
                     and (not options.get('actif') or t['actif'][i, j] == 1)
                     and (j not in pause or jour > pause[j])]
        candidats.sort(key=lambda j: -t['elan'][i, j])
        for j in candidats[:max(5 - len(positions), 0)]:
            prix = o[i, j] * (1 + glissement)
            distance = s.K_STOP * t['atr'][i, j]
            # 1 % de risque prix, 20 % du portefeuille maximum ; aucun levier.
            montant = min(valeur * .01 * prix / distance, valeur / 5, cash / (1 + commission))
            if montant < 5:
                continue
            cout = montant * (1 + commission)
            cash -= cout
            couts += montant * commission + montant / prix * o[i, j] * glissement
            positions[j] = [montant / prix, prix - distance, cout]
            achats += 1
        for j in list(positions):
            if np.isfinite(l[i, j]) and l[i, j] <= positions[j][1]:
                vendre(j, min(o[i, j], positions[j][1]), jour, stop=True)
        dernier = np.where(np.isfinite(c[i]), c[i], dernier)
        courbe.append((str(jour.date()), cash + sum(p[0] * dernier[j] for j, p in positions.items())))
    # Liquidation comptable finale, identique pour toutes les variantes.
    if courbe:
        for j in list(positions):
            vendre(j, dernier[j], pd.Timestamp(courbe[-1][0]))
        courbe[-1] = (courbe[-1][0], cash)
    valeurs = np.array([CAPITAL] + [v for _, v in courbe])
    pertes = -sum(v for v in sorties if v < 0)
    return {'capital_final': float(cash), 'rendement': float(cash / CAPITAL - 1),
            'drawdown': float((valeurs / np.maximum.accumulate(valeurs) - 1).min()),
            'achats': achats, 'clotures': len(sorties), 'gagnantes': sum(v > 0 for v in sorties),
            'profit_factor': float(sum(v for v in sorties if v > 0) / pertes) if pertes else None,
            'couts_estimes': float(couts), 'courbe': courbe}


def enrichir(donnees):
    t, noms, dates = preparer(donnees)
    t['actif'] = pd.DataFrame({n: (df['Close'] > s.sma(df['Close'], 200)).astype(float)
                              for n, df in donnees.items()}).reindex(dates).shift(1).fillna(0).to_numpy(float)
    return t, noms, dates


def comparer(donnees):
    t, noms, dates = enrichir(donnees)
    fin = max(dates)
    periodes = {'selection': (pd.Timestamp('2021-01-01'), pd.Timestamp('2022-12-31')),
                'final': (pd.Timestamp('2023-01-01'), fin)}
    resultats = {}
    for cle, options in VARIANTES.items():
        r = {'label': options['label']}
        for periode, (debut, dernier) in periodes.items():
            r[periode] = simuler(t, noms, dates, debut, dernier, options)
        r['stress'] = simuler(t, noms, dates, *periodes['final'], options, commission=.008, glissement=.002)
        resultats[cle] = r
    reference = resultats['reference']['selection']
    # Critère écrit avant exécution : gain positif et supérieur, drawdown au moins aussi bon.
    eligibles = [k for k, r in resultats.items() if k != 'reference'
                 and r['selection']['rendement'] > max(0, reference['rendement'])
                 and r['selection']['drawdown'] >= reference['drawdown']]
    choisi = max(eligibles, key=lambda k: resultats[k]['selection']['rendement']) if eligibles else 'reference'
    r, base = resultats[choisi], resultats['reference']
    comparables = (fin >= pd.Timestamp('2023-12-31') and all(len(v) >= 365 for v in donnees.values()))
    ameliore = (comparables and choisi != 'reference' and r['final']['rendement'] > max(0, base['final']['rendement'])
                and r['final']['drawdown'] >= base['final']['drawdown']
                and r['stress']['rendement'] > 0 and r['final']['clotures'] >= 30)
    return {'schema': 1, 'date': str(dt.datetime.now(dt.timezone.utc).date()),
            'selection': {'debut': '2021-01-01', 'fin': '2022-12-31'},
            'final': {'debut': '2023-01-01', 'fin': str(fin.date())},
            'choisi_sur_selection': choisi, 'amelioration_descriptive': bool(ameliore),
            'production_activee': False, 'variantes': resultats,
            'limites': ['Étude rétrospective exploratoire, jamais une preuve de gains futurs.',
                       'Univers actuel de 15 cryptos connu après coup : biais de survivance.',
                       'Prix Yahoo en USD ; pas les exécutions Kraken EUR ni les CFD Libertex.',
                       'Commission spot 0,4 % par ordre, glissement 0,1 % ; aucun levier ni financement CFD.',
                       'Capital de 1 000 € réinitialisé par période ; indicateurs du passé conservés.',
                       'Les périodes récentes ont déjà été observées dans les recherches précédentes.',
                       'Le bot et les comptes réels ne sont pas modifiés. Un suivi prospectif serait nécessaire.']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sortie', default=str(Path(s.DOSSIER) / 'recherche_trading.json'))
    ap.add_argument('--donnees', help='dossier de snapshots CSV locaux, sinon téléchargement Yahoo')
    ap.add_argument('--snapshots', help='sauvegarder les prix normalisés pour reproduire ce calcul')
    args = ap.parse_args()
    donnees, sources = {}, []
    hier = pd.Timestamp(dt.datetime.now(dt.timezone.utc).date()) - pd.Timedelta(days=1)
    for nom, ticker in UNIVERS.items():
        if args.donnees:
            df = pd.read_csv(Path(args.donnees) / f'{ticker}.csv', index_col=0, parse_dates=True)
        else:
            df = s.telecharger(ticker, 12)
        df = df.loc[df.index <= hier, ['Open', 'High', 'Low', 'Close']].sort_index()
        if df.index.duplicated().any() or df.empty or not np.isfinite(df.to_numpy()).all():
            raise ValueError(f'Prix invalides : {ticker}')
        if ((df <= 0).any(axis=1) | (df.High < df[['Open', 'Close', 'Low']].max(axis=1))
                | (df.Low > df[['Open', 'Close', 'High']].min(axis=1))).any():
            raise ValueError(f'OHLC incohérents : {ticker}')
        if df.index[-1] < hier - pd.Timedelta(days=3):
            raise ValueError(f'Historique périmé : {ticker}')
        contenu = df.to_csv().encode()
        sources.append({'ticker': ticker, 'debut': str(df.index[0].date()), 'fin': str(df.index[-1].date()),
                        'lignes': len(df), 'sha256': hashlib.sha256(contenu).hexdigest()})
        if args.snapshots:
            Path(args.snapshots).mkdir(parents=True, exist_ok=True)
            (Path(args.snapshots) / f'{ticker}.csv').write_bytes(contenu)
        donnees[nom] = df
    rapport = comparer(donnees)
    rapport['sources'] = sources
    Path(args.sortie).write_text(json.dumps(rapport, ensure_ascii=False, indent=2) + '\n')
    print('VARIANTE | SELECTION 2021-2022 | FINAL 2023+ | DRAWDOWN FINAL | FINAL FRAIS DOUBLES')
    for cle, r in rapport['variantes'].items():
        print(f"{cle}: {r['selection']['rendement']:+.2%} | {r['final']['rendement']:+.2%} | "
              f"{r['final']['drawdown']:+.2%} | {r['stress']['rendement']:+.2%}")
    print('Choisie sans le final :', rapport['choisi_sur_selection'])
    print('Amélioration descriptive selon les critères :', rapport['amelioration_descriptive'])
    print('Production activée : NON')


if __name__ == '__main__':
    main()
