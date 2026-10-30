# Résultat du 30 octobre 2026 — pause après stop

Rapport complet : [recherche_trading.json](recherche_trading.json).
Calcul réussi : https://github.com/Miknalson/T-Zik_nano/actions/runs/41112022286.
Les snapshots de prix normalisés sont dans l’artefact `recherche-prix` de ce calcul.

La variante retenue **sur 2021–2022 seulement** attend cinq jours calendaires complets
après un stop avant de pouvoir racheter le même actif. Elle conserve le filtre Bitcoin
200 jours, les signaux de cassure et les limites de risque du modèle de référence.
Elle n’attend pas cinq jours après les sorties ordinaires. Aucune nouvelle stratégie
n’est activée sur le bot, ni sur un compte réel.

## Comparaison finale rétrospective

Du 01/01/2023 au 29/10/2026, départ 1 000 €, 14 cryptos communes :

| Mesure | Règles de référence | Pause de 5 jours |
|---|---:|---:|
| Capital final, liquidation incluse | 3 023,76 € | 3 184,05 € |
| Gain du capital | +202,38 % | +218,40 % |
| Pire baisse depuis un sommet | −32,34 % | −29,97 % |
| Achats / clôtures, liquidation incluse | 171 | 163 |
| Capital final avec coûts doublés | 2 474,89 € | 2 638,48 € |

Le gain supplémentaire est de 160,29 €, soit **5,30 % du capital final de référence**,
pas 16 % de gain annuel supplémentaire. Ce sont presque quatre ans de simulation,
avec 0,4 % de commission par ordre et 0,1 % de glissement estimé, sans levier.
FLOKI est exclu des cinq variantes car une barre du 09/08/2021 est incohérente.
L’univers choisi après coup reste exposé au biais de survivance.

La pause a amélioré le résultat ET la pire baisse sur la période de choix 2021–2022,
puis sur la comparaison finale. Les autres variantes sont toutes dans le rapport,
y compris celles qui font moins bien. Aucun paramètre n’a été ajusté sur les gains
2023–2026 pour choisir cette variante.

## Limites : elle perd encore sur la période récente

Depuis le 03/10/2026, les extraits des courbes simulées sont encore perdants :
−5,35 % pour la référence et −5,06 % avec la pause. Ces extraits conservent les positions
héritées des années précédentes : ils ne sont pas une simulation neuve débutant
avec 1 000 € en octobre et ne reproduisent pas le compte papier enregistré à −9,24 %.
L’amélioration ne transforme pas une séquence perdante en séquence gagnante.

Un bootstrap exploratoire apparié des différences de rendements logarithmiques
journaliers finaux (blocs de 20 séances, 2 000 tirages, graine 20261030) donne pour
l’avantage relatif final un intervalle à 95 % d’environ **−1,87 % à +14,01 %**.
Il inclut zéro : **l’avantage n’est pas statistiquement établi** par ce calcul.
Cette estimation ne corrige pas toutes les anciennes recherches de stratégies.
La période 2023–2026 a déjà été consultée dans le dépôt : ce n’est pas une preuve
prospective sur des prix inconnus. Les prix USD et coûts spot ne valident pas des
ordres Kraken EUR exacts, ni les CFD Libertex et leur financement.

La suite cohérente serait un suivi papier parallèle, règles figées et sans remise
à zéro des pertes, en conservant la référence pour comparer les deux à coût égal.
Ce document ne déclenche aucun ordre et ne promet pas de rentabilité future.
