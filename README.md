<p align="center">
  <img src="docs/icone.png" width="96" alt="Icône">
</p>

<h1 align="center">Gestionnaire de modèles Ollama</h1>

<p align="center">
  Télécharger, organiser, sauvegarder et évaluer vos modèles de langage locaux.<br>
  <sub>Windows x64 · Version 1.0 · Licence MIT · Développé par Henrick PIETTE (2026)</sub>
</p>

<p align="center">
  <img src="docs/capture.png" width="800" alt="Capture d'écran">
</p>

## Télécharger

Rendez-vous dans la page **[Releases](../../releases/latest)** et téléchargez
`GestModOllama-v1.0-windows-x64.exe`. Aucune installation : double-cliquez sur le fichier.

> [Ollama](https://ollama.com) doit être installé et lancé sur le PC.
> Au premier lancement, Windows SmartScreen peut afficher « Windows a protégé votre ordinateur » :
> cliquez sur **Informations complémentaires**, puis **Exécuter quand même**
> (le programme n'est pas signé numériquement).

## Fonctions

**Onglet Modèles** (ouvert au démarrage)
- Liste des modèles installés : paramètres, quantification, taille, contexte maximal, date,
  occupation de la mémoire GPU ; recherche et tri par colonne.
- Carte de détails : famille, capacités (outils, réflexion, vision...), empreinte, Modelfile.
- Télécharger un modèle (comme `ollama pull`) : nom Ollama, commande `ollama pull ...` ou lien Hugging Face.
- Mettre à jour, copier sous un autre nom (`ollama cp`), supprimer (`ollama rm`), décharger de la mémoire.
- Exporter / importer des modèles dans un fichier (sauvegarde ou copie vers un autre PC sans Internet),
  avec vérification de chaque fichier.

**Onglet Benchmark** : évaluation des capacités de codage
- 9 exercices difficiles (40 points) : décompilation d'assembleur x86, pseudo-C Ghidra,
  bytecode Python, exécution de x86 et de Z80 « de tête », écriture d'un mini-interpréteur.
- Réponses vérifiées automatiquement ; classement global et par capacité ; rapport PDF.
- Attention : le code Python écrit par les modèles est exécuté sur le PC
  (dossier temporaire, 20 secondes au maximum).

**Réglages** (roue dentée en bas à gauche) : langue (français, English, español, Deutsch)
et taille du contexte du benchmark.

## Lancer depuis le code source

Python 3 (bibliothèque standard uniquement, aucune dépendance) :

```
python comparer_hardcode.py
```

Pour fabriquer le `.exe` : double-cliquez sur `compiler.bat` (installe PyInstaller, crée l'icône et compile).

---

*English:* a Windows desktop manager for local [Ollama](https://ollama.com) models (download, update,
copy, delete, unload, export/import) with a built-in coding benchmark (assembly, decompilation,
reasoning). Interface available in English, French, Spanish and German. MIT License.

## Licence

[MIT](LICENSE) © 2026 Henrick PIETTE
