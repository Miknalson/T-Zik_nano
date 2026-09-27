# Signaux quotidiens

Analyse chaque nuit 10 marchés (crypto, gaz, pétrole, or, CAC 40, S&P 500, EUR/USD, GBP/USD)
avec 3 règles simples, et n'affiche un signal que si la règle a battu le hasard sur
l'historique en simulant **exactement les consignes affichées** : entrée à l'ouverture,
stop-loss chez le courtier, frais et financement overnight compris. Sinon : « pas de signal fiable ».

## Sur le téléphone (rien à installer)

GitHub lance le programme tout seul chaque nuit (vers 2 h 40 l'été, 1 h 40 l'hiver, heure
de Paris), une fois toutes les séances de la veille terminées, et publie le rapport sur
https://miknalson.github.io/T-Zik_nano/. Dans Safari : bouton Partager →
« Sur l'écran d'accueil » pour l'avoir comme une app.

La page est publique : le capital n'y apparaît pas, les tailles sont exprimées en
multiple de ton capital. Le journal des signaux est enregistré chaque nuit dans
`journal_signaux.csv`.

Pour relancer à la main : onglet Actions du dépôt → « Signaux quotidiens » → Run workflow.

## Que faire selon la carte

Seules les règles validées donnent une consigne. Consulte la page le matin.

| Carte | Quoi faire |
|---|---|
| **ENTRER — ACHAT / VENTE** | Entre à l'ouverture de la prochaine séance. Pose aussitôt le stop-loss indiqué chez ton courtier. Pas de take-profit. |
| **EN COURS** | Si tu es dedans : ne touche à rien. Si tu n'y es pas : n'entre pas en cours de route, attends le prochain ENTRER. |
| **SORTIR** | Ferme la position à l'ouverture de la prochaine séance. |
| **INVERSER** | Ferme la position et entre dans l'autre sens à l'ouverture, avec le nouveau stop. |
| **STOP TOUCHÉ** | La position a été fermée par le stop. Attends le prochain ENTRER. |
| **Pas de signal fiable** | Ne trade pas ce marché avec cette règle. |

- **Stop-loss** : 2 × l'ATR (variation moyenne d'une séance sur 14 jours), fixé à l'entrée
  et jamais déplacé. Il est affiché en % de ton prix d'entrée : si tu entres à un autre
  prix que celui estimé, garde le même %.
- **Take-profit** : aucun. Les règles de tendance gagnent sur quelques grands mouvements ;
  un take-profit fixe les couperait. La sortie vient de la règle (carte SORTIR) ou du stop.
- **Taille max** : calculée pour qu'un stop touché ne coûte que 1 % du capital.
- Le test historique suppose une entrée au prix d'ouverture. Entrer des heures plus tard
  (par exemple sur le forex ou les matières premières, qui rouvrent la nuit) change le résultat.

## Sur PC — installation (une seule fois)

1. Installer Python 3.10+ : https://www.python.org/downloads/ (Windows : cocher « Add Python to PATH »).
2. Dans un terminal, depuis ce dossier :
   ```
   pip install -r requirements.txt
   ```

```
python signaux.py --capital 1000 --risque 1
```

- `--capital` : taille de ton compte en €.
- `--risque` : % du capital perdu si le stop est touché (1 % recommandé).
- `--demo` : données simulées sans Internet (doit afficher 0 signal : c'est voulu).

Lance-le le matin : la séance du jour, jamais complète, est toujours ignorée.

## Frais

Les coûts par défaut (spread, financement overnight) sont ceux d'un CFD grand public.
Remplace-les par ceux de ton courtier dans le dictionnaire `FRAIS` de `signaux.py` :
des frais sous-estimés font valider des règles qui perdent en réalité.

## Tests

```
python test_validation.py
```
Vérifie que le filtre rejette le hasard pur et reconnaît un vrai avantage, que le stop-loss
est exécuté au bon prix (y compris en cas de gap), que les entrées et sorties se font à
l'ouverture suivante, et qu'aucune règle n'utilise de données futures.
