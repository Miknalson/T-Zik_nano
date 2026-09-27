# Signaux quotidiens

Analyse chaque soir 10 marchés (crypto, gaz, pétrole, or, CAC 40, S&P 500, EUR/USD, GBP/USD)
avec 3 règles simples, et n'affiche un signal que si la règle a battu le hasard sur
l'historique, **frais et financement overnight compris**. Sinon : « pas de signal fiable ».

## Sur le téléphone (rien à installer)

GitHub lance le programme tout seul chaque soir (vers 23 h 30 l'été, 22 h 30 l'hiver)
et publie le rapport sur https://miknalson.github.io/T-Zik_nano/. Dans Safari :
bouton Partager → « Sur l'écran d'accueil » pour l'avoir comme une app.

La page est publique : le capital n'y apparaît pas, les tailles sont exprimées en
multiple de ton capital. Le journal des signaux est enregistré chaque soir dans
`journal_signaux.csv`.

Pour relancer à la main : onglet Actions du dépôt → « Signaux quotidiens » → Run workflow.

## Sur PC — installation (une seule fois)

1. Installer Python 3.10+ : https://www.python.org/downloads/ (Windows : cocher « Add Python to PATH »).
2. Dans un terminal, depuis ce dossier :
   ```
   pip install -r requirements.txt
   ```

## Utilisation

```
python signaux.py --capital 1000 --risque 1
```

- `--capital` : taille de ton compte en €.
- `--risque` : % du capital perdu si le stop est touché (1 % recommandé).
- `--demo` : données simulées sans Internet (doit afficher 0 signal : c'est voulu).

Lance-le **le soir, après la clôture** (après 22 h 30 pour les marchés US).

Le programme produit :
- `rapport_signaux.html` : à ouvrir sur le téléphone (iCloud Drive, AirDrop, e-mail…) ;
- `journal_signaux.csv` : historique de tous les signaux, pour vérifier après coup
  s'ils auraient vraiment gagné avant d'y mettre de l'argent.

## Lire un signal

| Champ | Sens |
|---|---|
| ACHAT / VENTE | position proposée pour la séance suivante |
| stop | niveau de sortie si le marché va contre toi |
| nominal max | taille de position pour ne perdre que `--risque` % au stop |
| p | probabilité que le résultat historique soit dû au hasard (< 0,01 exigé) |

## Frais

Les coûts par défaut (spread, financement overnight) sont ceux d'un CFD grand public.
Remplace-les par ceux de ton courtier dans le dictionnaire `FRAIS` de `signaux.py` :
des frais sous-estimés font valider des règles qui perdent en réalité.

## Tests

```
python test_validation.py
```
Vérifie que le filtre rejette le hasard pur, reconnaît un vrai avantage, et qu'aucune
règle n'utilise de données futures.
