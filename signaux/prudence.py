"""Contrôle expérimental chronologique ; aucune sélection par le gain final."""
import numpy as np
import pandas as pd


def intervalle_blocs(net, taille=20, tirages=2000):
    """IC exploratoire de la moyenne journalière, bootstrap de blocs de séances."""
    net = np.asarray(net, dtype=float)
    if len(net) < taille * 3:
        return None
    blocs = [net[i:i + taille] for i in range(0, len(net), taille)]
    sommes = np.array([b.sum() for b in blocs])
    longueurs = np.array([len(b) for b in blocs])
    choix = np.random.default_rng(20261030).integers(0, len(blocs), (tirages, len(blocs)))
    moyennes = sommes[choix].sum(axis=1) / longueurs[choix].sum(axis=1)
    return [float(v) for v in np.quantile(moyennes, [.025, .975])]


def controler(df, voulu, frais, evaluation, en_cours=False, nombre_tests=45):
    from signaux import executer
    # Les indicateurs utilisent le passé complet ; aucune position ne traverse la coupure.
    coupure = int(len(df) * .7)
    signaux = voulu.copy()
    signaux.iloc[:coupure] = 0
    x = executer(df, signaux, frais, en_cours=en_cours)
    net = x['net'][coupure:]
    stress = executer(df, signaux, {k: v * 2 for k, v in frais.items()}, en_cours=en_cours)
    ic = intervalle_blocs(net)
    sous_periodes = [float(b.sum()) for b in np.array_split(net, 3)]
    p_corrige = min(1., float(evaluation['p']) * nombre_tests)
    raisons = []
    if not evaluation['valide']:
        raisons.append("Le contrôle historique initial n'est pas validé.")
    if p_corrige >= .05:
        raisons.append(f"Avantage non confirmé après correction des {nombre_tests} essais.")
    if x['nb_trades'] < 30:
        raisons.append(f"Seulement {x['nb_trades']} entrées sur la période récente (minimum 30).")
    if not all(v > 0 for v in sous_periodes):
        raisons.append("Au moins un des trois segments récents est perdant ou sans gain.")
    if ic is None or ic[0] <= 0:
        raisons.append("L'intervalle d'incertitude récent inclut un résultat nul ou négatif.")
    stress_net = float(stress['net'][coupure:].sum())
    if stress_net <= 0:
        raisons.append("La période récente ne résiste pas au doublement des frais.")
    return {'valide': not raisons, 'raisons': raisons, 'debut': str(df.index[coupure].date()),
            'fin': str(df.index[-1].date()), 'trades': x['nb_trades'],
            'somme_rendements': float(net.sum()), 'segments': sous_periodes,
            'stress': stress_net, 'ic_moyenne_seance': ic, 'p_corrige': p_corrige,
            'nombre_tests': nombre_tests}


def autorisee(r):
    return bool((r.get('eval') or {}).get('prudent', {}).get('valide', False))


def diagnostic_html(r):
    import html
    e = r.get('eval') or {}
    p = e.get('prudent')
    if not p:
        return ''
    raisons = ''.join(f'<li>{html.escape(x)}</li>' for x in p['raisons'])
    ic = p['ic_moyenne_seance']
    incertitude = (f"IC 95 % de la moyenne par séance : {ic[0]:+.3%} à {ic[1]:+.3%}." if ic
                   else "Historique récent trop court pour estimer l'incertitude.")
    return (f'<details class="validation"><summary>Voir les tests de cette méthode</summary>'
            f'<p>Période récente séparée : {p["debut"]} → {p["fin"]} · {p["trades"]} entrées.</p>'
            f'<p>Somme des rendements de position : {p["somme_rendements"]:+.1%}. '
            f'Frais doublés : {p["stress"]:+.1%}. Ce n’est pas le rendement du capital.</p>'
            f'<p>{incertitude} Estimation exploratoire par blocs de 20 séances.</p>'
            f'<ul>{raisons}</ul><p>Une période passée séparée ne constitue pas une validation prospective. '
            f'Les coûts réels et la qualité des prix restent à vérifier.</p></details>')


def recherche_html(chemin):
    import html
    import json
    from pathlib import Path
    if not Path(chemin).exists():
        return ('<section><div class="eyebrow">Recherche de rentabilité</div>'
                '<h2>Comparaison en préparation</h2><p>Les variantes seront calculées avec des prix réels. '
                'Aucun résultat synthétique ne sert à choisir une stratégie.</p></section>')
    r = json.loads(Path(chemin).read_text())
    lignes = []
    for cle, v in r['variantes'].items():
        choisi = ' · retenue sur 2021–2022' if cle == r['choisi_sur_selection'] else ''
        lignes.append(f'<tr><td>{html.escape(v["label"] + choisi)}</td>'
                      f'<td>{v["selection"]["rendement"]:+.1%}</td><td>{v["final"]["rendement"]:+.1%}</td>'
                      f'<td>{v["final"]["drawdown"]:+.1%}</td><td>{v["stress"]["rendement"]:+.1%}</td></tr>')
    verdict = ('Une variante améliore le résultat historique selon les critères fixés. '
               'Elle reste expérimentale et ne remplace pas le bot.' if r['amelioration_descriptive'] else
               'Aucune amélioration ne franchit tous les critères fixés. Le bot reste inchangé.')
    return ('<section><div class="eyebrow">Recherche de rentabilité · bot au comptant</div>'
            f'<h2>Cinq variantes, un même capital.</h2><p>{verdict}</p>'
            '<details class="validation"><summary>Comparer les résultats chiffrés</summary>'
            '<div class="defile"><table><thead><tr><th>Variante</th><th>2021–2022</th>'
            '<th>2023+ · gain</th><th>Pire baisse</th><th>Frais doublés</th></tr></thead><tbody>'
            + ''.join(lignes) + '</tbody></table></div>'
            f'<p>Fin du test : {html.escape(r["final"]["fin"])}. Capital de départ : 1 000 € par période. '
            'Choix sur 2021–2022 uniquement ; comparaison finale sur 2023 et les années suivantes.</p>'
            '<p>Étude rétrospective, univers connu après coup. Prix USD et coûts spot estimés : '
            'cela ne valide pas une méthode sur les CFD Libertex. Aucun gain futur garanti.</p>'
            '<p><a href="recherche_trading.json">Rapport et hypothèses (JSON)</a></p></details></section>')
