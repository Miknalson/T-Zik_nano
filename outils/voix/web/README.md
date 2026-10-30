# Voix naturelles locales

Les MP3 dans `anglais-a2/audio/` restent prioritaires. Pour un texte nouveau (conjugaison,
dictionnaire, réponse IA), `audio/natural-voice.js` fait travailler Piper dans un Web Worker.
Il utilise Lessac en anglais et Siwis en français, sans clé API ni service distant.
Les voix sont des voix de synthèse naturelles, pas des comédiens enregistrés.

Le premier chargement coûte environ 85 à 100 Mo par langue (modèle + phonémiseur + ONNX).
Les fichiers proviennent du même site et utilisent le cache prioritaire `speakup-voices-v1` du service worker. Ils ne sont pas
retéléchargés à chaque séance tant que le navigateur conserve ce cache.
Les modèles ne sont pas téléchargés au lancement de l’application. L’inférence reste locale.
Un navigateur sans les capacités requises, un téléchargement échoué ou une lecture audio
refusée fait apparaître un message et utilise la voix de l’appareil en secours.
Les voix premium de l’appareil restent sélectionnables dans Hypnose.

## Reconstruction

Depuis ce dossier, avec Node 20+ :

```sh
npm ci
npm run build
```

Le bundle et ses fichiers WASM sont volontairement conservés dans le dépôt pour GitHub
Pages : aucune compilation n’est nécessaire lors de la publication. Les fichiers ONNX
existants dans `anglais-a2/audio/runtime/models/` sont conservés par la reconstruction.
Ils viennent des archives officielles :

- https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-lessac-medium.tar.gz
- https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-fr-siwis-medium.tar.gz

Les `.onnx` et `.onnx.json` de ces archives sont renommés `en.onnx`, `en.onnx.json`,
`fr.onnx` et `fr.onnx.json`. Les cartes de modèles et licences se trouvent avec le runtime.
Le worker adapte la table des identifiants phonétiques aux modèles historiques : ne pas
remplacer cette étape par les identifiants par défaut du phonémiseur web.
ONNX tourne avec un seul thread pour fonctionner sans en-têtes COOP/COEP sur GitHub Pages.
Les changements de langue libèrent la session ONNX précédente pour limiter la mémoire.

## Vérification

Servir le dépôt avec un serveur HTTP, puis ouvrir `anglais-a2/` dans un navigateur moderne.
Vérifier un MP3 de chaque atelier, une nouvelle phrase anglaise et une phrase française de
conjugaison. L’annulation ou le changement d’onglet doit interrompre la lecture.
Sur iPhone, vérifier sur un appareil réel le premier chargement, l’autorisation audio,
la mémoire et la durée de synthèse ; l’émulation Chromium ne valide pas Safari iOS.

## Écoute en veille et Emma

`audio/continuous-audio.js` assemble les trames MP3 de même format (y compris les
silences, répétitions et mots isolés) dans un seul Blob MP3. Les anciens en-têtes ID3
et Xing/Info sont retirés pour ne pas conserver la durée du premier petit clip.
La piste est coupée au minuteur choisi, compte tenu de la vitesse, avant sa lecture.
La lecture native continue sans enchaînement de fichiers ou timers JavaScript.
Le mode sans minuteur boucle sur un tour complet du corpus.

Les histoires, la grammaire, les phrases métier/quotidien, le glossaire, les verbes
irréguliers et les dialogues enregistrés utilisent ce mode. Les sources générées
(conjugaison, mélange et mots personnels) gardent la lecture phrase par phrase et
restent soumises aux restrictions de veille d’iOS. Le fond musical n’est pas utilisé
pendant les pistes continues. Les commandes Media Session pilotent le même média.

Emma demande explicitement la voix naturelle, indépendamment du réglage d’Hypnose.
Une vidéo facultative est muette et ne remplace plus son enregistrement vocal.

```sh
npm ci
npm run test:mp3
# Avec le dépôt servi par un serveur HTTP local :
APP_URL=http://127.0.0.1:8000/anglais-a2/ CHROMIUM_PATH=/usr/bin/chromium npm run test:background
```

Le second test suspend la page via Chrome DevTools et vérifie que le média avance,
puis vérifie Emma avec une vidéo disponible et le réglage « voix de l’appareil ».
Cela ne remplace pas un test d’écran verrouillé sur un iPhone réel.
