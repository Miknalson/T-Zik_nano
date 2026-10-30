# Composants distribués

- ONNX Runtime Web 1.18.0, Microsoft, licence MIT (`licenses/ONNXRuntime.txt`).
  Sources : https://github.com/microsoft/onnxruntime/tree/v1.18.0
- Piper WASM 1.0.0, Diffusion Studio, licence MIT ; phonémiseur Piper et eSpeak NG.
  Sources et recette de construction : https://github.com/diffusion-studio/piper-wasm
  https://github.com/wide-video/piper-phonemize et https://github.com/rhasspy/espeak-ng
  eSpeak NG : GPL v3 (`licenses/GPL-3.txt`). La recette de compilation amont est jointe dans `licenses/piper-wasm-build.md`.
  Le paquet npm piper-wasm déclare MIT ; ses crédits sont indiqués dans `licenses/piper-wasm-package.json`.
- Modèles Lessac (en-US) et Siwis (fr), publication Piper v0.0.2.
  Provenance et conditions des jeux de données : `models/en.MODEL_CARD` et `models/fr.MODEL_CARD`.

Les voix produites sont synthétiques. Les modèles et les calculs sont locaux au navigateur.
