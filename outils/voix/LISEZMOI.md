# Voix humaines de l'Hypnose

Les phrases fixes de l’atelier Hypnose (histoires Slow English, dialogues, phrases, glossaire, verbes irréguliers) et chaque mot isolé (mode « mot à mot », clé `w|mot`) ainsi que les phrases anglaises du reste de l'appli (Emma, cours, scènes, TOEIC, test) sont pré-enregistrées avec [Piper](https://github.com/rhasspy/piper) dans `anglais-a2/audio/<hash>.mp3`, listées dans `anglais-a2/audio/index.json`. L'appli (`speak()` et l'Hypnose) joue l'enregistrement s'il existe, sinon la voix de l'appareil (conjugaison générée au hasard et réponses du tuteur IA restent en voix de l'appareil).

Voix utilisées (https://github.com/rhasspy/piper/releases/tag/v0.0.2) :
- `en-us-lessac-medium` : anglais, personne 1
- `en-us-ryan-high` : anglais, personne 2 des dialogues
- `fr-siwis-medium` : français

Après avoir modifié des textes de l'appli :

```
pip install piper-tts && npm i playwright-core   # ffmpeg requis
node outils/voix/extraire.js                     # écrit items.json (textes à enregistrer)
for i in 0 1 2 3; do PIPER_DIR=dossier/des/voix/ python3 outils/voix/generer.py 4 $i & done; wait
```

Les fichiers existants sont gardés : seuls les nouveaux textes sont enregistrés. Le nom de fichier est le hash FNV-1a 32 bits de `voix|texte`, identique à `hypH` dans `index.html`.

## Textes générés et couverture de tous les modules

Les nouvelles phrases sans MP3 sont maintenant lues par le moteur naturel local
[web/README.md](web/README.md). Les MP3 restent prioritaires dans tous les ateliers.
Le premier chargement attend l’index audio afin de ne pas utiliser prématurément une
voix de secours. Les erreurs du moteur local sont signalées avant le recours à la voix
système, et les lectures sont interrompues quand on change d’écran.

L’extracteur inclut explicitement les dialogues TOEIC assemblés, les questions orales,
les phrases d’Emma, les paires de prononciation et les formes verbales. Il accepte
`CHROMIUM_PATH`, `APP_URL` et `ITEMS_PATH` pour utiliser un Chromium système, un serveur
HTTP local et un fichier de sortie extérieur au dépôt.
