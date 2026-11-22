<p align="center">
  <img src="docs/icone.png" width="96" alt="Icône">
</p>

<h1 align="center">Gestionnaire de modèles Ollama</h1>

<p align="center">
  Télécharger, organiser, sauvegarder et évaluer vos modèles de langage locaux.<br>
  <sub>Windows x64 · Version 1.1 · Licence MIT · Développé par Henrick PIETTE (2026)</sub>
</p>

<p align="center">
  <img src="docs/capture.png" width="800" alt="Capture d'écran">
</p>

## Télécharger

Rendez-vous dans la page **[Releases](../../releases/latest)** et téléchargez
`GestModOllama-windows-x64.exe`. Aucune installation : double-cliquez sur le fichier.
Ensuite, le programme se met à jour tout seul : au démarrage, il vérifie s'il existe une nouvelle
version et propose de l'installer (vérification désactivable dans les Réglages).

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

**Réglages** (roue dentée en bas à gauche) : langue (français, English, español, Deutsch),
taille du contexte du benchmark, vérification des mises à jour au démarrage.

**Mises à jour** : vérification au démarrage (ou menu Aide > Rechercher les mises à jour),
téléchargement depuis GitHub avec contrôle de l'empreinte SHA-256, installation et redémarrage
automatiques. Le programme garde son nom : les raccourcis continuent de fonctionner.

## Lancer depuis le code source

Python 3 (bibliothèque standard uniquement, aucune dépendance) :

```
python comparer_hardcode.py
```

Pour fabriquer le `.exe` : double-cliquez sur `compiler.bat` (installe PyInstaller, crée l'icône et compile).

---

*English:* a Windows desktop manager for local [Ollama](https://ollama.com) models (download, update,
copy, delete, unload, export/import) with a built-in coding benchmark (assembly, decompilation,
reasoning) and automatic updates from GitHub Releases. Interface available in English, French, Spanish and German. MIT License.

## Licence

[MIT](LICENSE) © 2026 Henrick PIETTE
