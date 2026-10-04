# Signaux quotidiens

Analyse chaque matin 14 marchés (crypto, gaz, pétrole, or, CAC 40, S&P 500, EUR/USD, GBP/USD)
avec 3 règles simples, et n'affiche un signal que si la règle a battu le hasard sur
l'historique en simulant **exactement les consignes affichées** : entrée à l'ouverture,
stop-loss chez le courtier, frais et financement overnight compris. Sinon : « pas de signal fiable ».

## Sur le téléphone (rien à installer)

GitHub lance le programme tout seul chaque nuit (vers 2 h 40 l'été, 1 h 40 l'hiver, heure
de Paris), une fois toutes les séances de la veille terminées, et publie le rapport sur
https://miknalson.github.io/T-Zik_nano/. Dans Safari : bouton Partager →
« Sur l'écran d'accueil » pour l'avoir comme une app.

La page est publique. Les tailles y sont calculées pour un capital de 1 000 € (réglable
avec `--capital` dans `.github/workflows/signaux.yml`). Le journal des signaux est enregistré chaque nuit dans
`journal_signaux.csv`.

Pour relancer à la main : onglet Actions du dépôt → « Signaux quotidiens » → Run workflow.

## Que faire selon la carte

Seules les règles validées donnent une consigne. Consulte la page le matin.

| Carte | Quoi faire |
|---|---|
| **ENTRER — ACHAT / VENTE** | Entre à l'ouverture de la prochaine séance. Pose aussitôt le stop-loss indiqué chez ton courtier. Pas de take-profit. |
| **EN COURS** | Si tu es dedans : ne touche à rien. Si tu n'y es pas : méthode suivie (★), tu peux entrer à l'ouverture avec le montant et le stop-loss affichés ; autre méthode, attends le prochain ENTRER. |
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

## Notifications sur le téléphone

Chaque matin vers 7 h 15 (6 h 15 l'hiver), une notification arrive dans l'app **ntfy**
seulement s'il y a une action à faire sur une **méthode suivie** (★ sur la page) :
ACHÈTE / VENDS (avec les cases de l'ordre Libertex : direction, montant, multiplicateur ×2,
stop loss), FERME, ou stop touché.

| Marché | Méthode suivie |
|---|---|
| Bitcoin, Ethereum, XRP | Cassure 20 jours |
| Dogecoin, Stellar, VeChain (ajoutés le 30/09/2026) | Cassure 20 jours |
| EUR/GBP (ajouté le 04/10/2026, multiplicateur ×10) | Retour à la moyenne (RSI 2) |
| S&P 500 | Retour à la moyenne (RSI 2) |

Ces méthodes ont été fixées le 27/09/2026 et ne doivent pas changer pendant le test.

Depuis le 29/09/2026, ces méthodes permettent d'**entrer en cours de route** : si la carte
dit EN COURS et que tu n'es pas dedans, entre à l'ouverture avec un stop-loss neuf (2 × ATR
depuis ton prix d'entrée), indiqué sur la carte. Après un stop touché, si la tendance
continue, la notification ACHÈTE/VENDS arrive le matin même pour rentrer. Test historique
(`test_en_cours.py`) : résultat équivalent à l'attente d'un nouveau signal
(Bitcoin +52 %/an contre +44 %, Ethereum +52 % contre +50 %, XRP +46 % contre +46 %,
S&P 500 +1,9 % contre +1,7 %), toujours sans battre nettement le hasard.
Le canal ntfy est dans le secret GitHub `NTFY_TOPIC`. Pour vérifier que tout marche :
onglet Actions → « Signaux quotidiens » → Run workflow → cocher « Envoyer aussi une
notification de test ».

## Tester sur compte démo (Libertex)

Chaque carte affiche l'orientation de la règle (↑ HAUSSE, ↓ BAISSE, → NEUTRE). Les règles
non validées gardent une ligne « Démo : … » avec la même consigne, **à suivre uniquement
sur le compte démo** : elles n'ont pas battu le hasard sur l'historique.

- Suis les consignes à la lettre : entrée seulement sur ENTRER, stop-loss posé tout de suite,
  sortie sur SORTIR. Si tu improvises, le suivi ne correspondra plus à tes résultats.
- Sur Libertex, la taille de la position = montant investi × multiplicateur. Pour une
  « taille max 200 € » : par exemple 100 € × 2, ou 40 € × 5. Garde un multiplicateur bas
  (×1 à ×5) : le montant investi doit rester bien supérieur à la perte au stop (10 € pour
  1 000 €), sinon Libertex peut fermer la position avant le stop. Le stop-loss se règle au
  niveau de prix indiqué.
- La ligne « Suivi démo » compte, depuis le 28/09/2026, les trades ouverts par chaque règle
  et leur résultat en % de la position. Compare-la à ton compte démo.
- Libertex facture surtout une commission par trade : relève celle affichée dans le ticket
  d'ordre et mets-la dans `FRAIS` pour que le test historique soit juste.

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

## Bot crypto Kraken (argent fictif pour l'instant)

`bot.py` passe les ordres tout seul, chaque jour juste après 00 h 00 UTC (2 h du matin à
Paris l'été) : achat quand la cassure 20 jours est en tendance haussière, stop à 2 × ATR posé
à l'achat, vente quand le cours clôture sous le plus bas des 10 derniers jours, rachat si la
tendance continue après un stop. Achat seulement : une plateforme au comptant ne permet pas de
parier sur la baisse (`test_spot.py` : la méthode reste gagnante en achat seul sur les 6 cryptos).

- Marchés : Bitcoin, Ethereum, XRP, Dogecoin, Stellar, VeChain, plus Solana, BNB, Tron,
  Avalanche, NEAR, Hedera, Polkadot, Algorand et FLOKI (retenues par `test_kraken.py`), en euros sur
  Kraken.
- **Au plus 5 cryptos en même temps** (variable GitHub `BOT_MAX` pour changer ce nombre) :
  quand il y a plus de candidates que de places, il prend celles qui ont le plus monté sur
  90 jours. Chaque position est plafonnée à 1/`BOT_MAX` du portefeuille. Test sur 10 ans
  (`test_portefeuille.py`) : 1 000 € → 30 377 € avec 5 maximum (pire baisse −38 %), contre
  108 859 € sans limite (pire baisse −47 %) ; le classement « les plus fortes d'abord » ne fait
  pas nettement mieux qu'un choix au hasard (p = 0,21). Binance
  refuse les serveurs de GitHub (pays interdit), Kraken les accepte.
- Mode papier : portefeuille fictif de 1 000 €, ordres simulés au prix Kraken avec 0,4 % de
  frais par ordre. État dans `bot_portefeuille.json`, opérations dans `bot_journal.csv`,
  résumé en haut de la page, notification « Bot : … » à chaque achat ou vente.
- Le mode papier tourne toujours, même quand l'argent réel est branché : il sert de référence.
- **Page du bot** (`bot.html`, lien depuis la carte « 🤖 Bot Kraken ») : valeur, gain ou perte
  depuis le départ, gains réalisés et en cours, courbe de la valeur jour après jour (touche la
  courbe pour lire une date), positions ouvertes et historique de toutes les opérations. Une
  partie « Réel » apparaît dès que le bot a tourné en argent réel. Mise à jour après chaque
  passage du bot.

### Brancher l'argent réel

1. **Clé d'API Kraken** (Kraken → Paramètres → API → créer une clé). Cocher seulement :
   consulter les fonds, consulter les ordres ouverts et fermés, créer et modifier des ordres,
   annuler des ordres. **Ne jamais cocher le retrait** : même volée, la clé ne pourrait pas
   sortir l'argent du compte.
2. **Secrets GitHub** (dépôt → Settings → Secrets and variables → Actions → New repository
   secret) : `KRAKEN_API_KEY` (la clé) et `KRAKEN_API_SECRET` (la clé privée). Ne jamais les
   copier ailleurs.
3. **Vérification** : Actions → « Bot crypto Kraken » → Run workflow → cocher « Vérifier la clé
   Kraken ». Kraken valide un achat et un stop par crypto **sans rien exécuter** ; le résultat
   arrive en notification.
4. **Mise en route** : même page, onglet **Variables** → `BOT_BUDGET` = euros confiés au bot
   (ex. `100`) puis `BOT_MODE` = `reel`. Il faut au moins ce montant en euros sur Kraken.
   Le budget peut être modifié à tout moment : la différence est ajoutée aux liquidités du bot
   (ou retirée) au passage suivant. Le bot ne dépense jamais plus que ses liquidités.
5. **Arrêt** : voir le bouton ci-dessous. Pour débrancher complètement l'argent réel,
   supprimer la variable `BOT_MODE`.

### Bouton d'arrêt

Actions → « 🛑 Bot : arrêter ou reprendre » → Run workflow, puis choisir :

- **Arrêter (garder les positions)** : plus aucun achat. Les positions gardent leur stop et
  sont vendues normalement quand la tendance finit.
- **Arrêter et tout vendre** : vend tout de suite toutes les positions (stops annulés chez
  Kraken), puis plus aucun achat.
- **Reprendre** : le bot recommence à acheter dès le passage de la nuit.

L'état est dans `bot_arret.json` ; la carte du bot sur la page affiche « ⏸ ARRÊTÉ ».
Une notification confirme chaque commande.

En réel, le stop est un vrai ordre stop-loss posé chez Kraken : il protège la position même
entre deux passages du bot. État dans `bot_reel.json`, opérations dans `bot_reel_journal.csv`.
En cas d'erreur, une notification « Bot : ERREUR (argent réel) » arrive.
