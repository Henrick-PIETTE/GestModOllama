"""
Gestionnaire de modèles Ollama - avec un benchmark de code "hardcore" (assembleur, décompilation).
Version 1.0 - PixtrekCoder - Développé par Henrick PIETTE - Licence MIT - 2026

FONCTION PRINCIPALE (onglet « Modèles », ouvert au démarrage) : gérer les modèles d'Ollama
  - liste des modèles installés (paramètres, quantification, taille, contexte, mémoire GPU),
    recherche, tri, carte de détails (capacités : outils, réflexion, vision...) ;
  - télécharger (ollama pull), mettre à jour, copier sous un autre nom (ollama cp),
    supprimer (ollama rm), décharger de la mémoire, voir le Modelfile ;
  - exporter / importer des modèles (fichier ZIP) pour les sauvegarder ou les copier sur un autre PC.

ONGLET « BENCHMARK » : évaluation des capacités de codage.
9 exercices, tous vérifiés automatiquement :
  0. Test de base (très simple) : vérifie que le modèle sait répondre avec du code Python
  1. Décompiler une fonction x86-64 optimisée (gcc -O2) -> Python
  2. Décompiler une boucle x86-64 sur un tableau -> Python
  3. Pseudo-C style Ghidra (hachage avec masques 32 bits) -> Python
  4. Bytecode Python (sortie de dis) -> Python
  5. Exécuter "de tête" du x86-64 : donner la valeur retournée
  6. Exécuter "de tête" une routine Z80 (Amstrad CPC) : registres A et C
  7. Écrire un mini-interpréteur d'assembleur en Python
  8. Comprendre du x86 32 bits "classique" PC (pile, ebp, idiv, cdq, cmovns) -> Python

Les exercices sont regroupés en "capacités" (bases, décompilation, lecture de code,
exécution de tête, programmation) : le résumé donne un classement global ET par capacité.

Résultats : resume_hardcode.md, resultats_hardcode.csv, reponses_hardcode.md
(suffixe _reflexion si le mode réflexion est coché, ce qui est le cas par défaut)
Réglages (roue dentée en bas à gauche) : langue, taille du contexte. Ils sont gardés
dans reglages_hardcode.json, à côté du programme.
Utilisation : double-cliquez sur le fichier (ou : python comparer_hardcode.py).

ATTENTION : le script exécute sur votre PC le code Python écrit par les modèles.
"""

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request

VERSION = "1.0"
SIGNATURE = "PixtrekCoder"
AUTEUR = "Henrick PIETTE"
LICENCE = "MIT"
ANNEE = "2026"
DEPOT_GITHUB = ""        # adresse du dépôt GitHub (affichée dans « À propos » si elle est remplie)

# ---------------------------------------------------------------
# 1) RÉGLAGES
# ---------------------------------------------------------------
NB_CHAMPS = 8         # nombre de champs "Modèle" dans la fenêtre

URL = "http://localhost:11434"
CONTEXTE = 8192      # les listings sont longs : un peu plus de contexte
MAX_TOKENS = 3000
# Avec le mode réflexion, le modèle "pense" avant de répondre : il faut plus de place
CONTEXTE_REFLEXION = 16384
MAX_TOKENS_REFLEXION = 12000

# Les fichiers de résultats sont créés dans le dossier du programme
if getattr(sys, "frozen", False):
    # Programme compilé en .exe : les résultats vont à côté du .exe
    DOSSIER = os.path.dirname(os.path.abspath(sys.executable))
else:
    DOSSIER = os.path.dirname(os.path.abspath(__file__))

# Ce que l'utilisateur choisit dans la fenêtre « Réglages » (sauvegardé dans un fichier)
FICHIER_REGLAGES = os.path.join(DOSSIER, "reglages_hardcode.json")
LANGUE = "fr"            # fr, en, es ou de
CONTEXTE_CHOISI = 0      # 0 = automatique (8192 sans réflexion, 16384 avec)
LANGUES = [("fr", "Français"), ("en", "English"), ("es", "Español"), ("de", "Deutsch")]


def charger_reglages():
    global LANGUE, CONTEXTE_CHOISI
    try:
        with open(FICHIER_REGLAGES, encoding="utf-8") as f:
            r = json.load(f)
        if r.get("langue") in [code for code, _ in LANGUES]:
            LANGUE = r["langue"]
        c = int(r.get("contexte", 0) or 0)
        CONTEXTE_CHOISI = c if 2048 <= c <= 262144 else 0
    except Exception:
        pass       # pas de fichier ou fichier abîmé : on garde les valeurs par défaut


def sauver_reglages():
    try:
        with open(FICHIER_REGLAGES, "w", encoding="utf-8") as f:
            json.dump({"langue": LANGUE, "contexte": CONTEXTE_CHOISI}, f, indent=2)
        return True
    except Exception:
        return False


def contexte_utilise(reflexion):
    """Taille du contexte réellement envoyée à Ollama (num_ctx)."""
    if CONTEXTE_CHOISI:
        return CONTEXTE_CHOISI
    return CONTEXTE_REFLEXION if reflexion else CONTEXTE


# ---------------------------------------------------------------
# 2) LES TEXTES DANS LES 4 LANGUES
# ---------------------------------------------------------------
# Chaque texte : (français, anglais, espagnol, allemand).
# Les {n}, {e}... sont remplacés par des valeurs au moment de l'affichage.
# Les questions posées aux modèles restent en français : ainsi les scores restent
# comparables d'une langue à l'autre.
TEXTES = {
    # ----- Fenêtre principale -----
    "titre_fenetre": ("Gestionnaire de modèles Ollama", "Ollama Model Manager",
                      "Gestor de modelos Ollama", "Ollama-Modellverwaltung"),
    "sous_titre": ("Télécharger, organiser, sauvegarder et évaluer vos modèles de langage locaux",
                   "Download, organize, back up and evaluate your local language models",
                   "Descargar, organizar, guardar y evaluar sus modelos de lenguaje locales",
                   "Lokale Sprachmodelle herunterladen, verwalten, sichern und bewerten"),
    "ollama_ok": ("Ollama {v} connecté", "Ollama {v} connected", "Ollama {v} conectado", "Ollama {v} verbunden"),
    "ollama_ko": ("Ollama ne répond pas", "Ollama is not responding", "Ollama no responde", "Ollama antwortet nicht"),
    "ollama_attente": ("Connexion à Ollama...", "Connecting to Ollama...", "Conectando con Ollama...",
                       "Verbindung zu Ollama..."),
    "onglet_modeles": ("Modèles", "Models", "Modelos", "Modelle"),
    "onglet_bench": ("Benchmark", "Benchmark", "Benchmark", "Benchmark"),
    "journal_titre": ("Journal", "Log", "Registro", "Protokoll"),
    "journal_effacer": ("Effacer", "Clear", "Borrar", "Leeren"),
    "credit": ("Développé par {a}  ·  Licence {l}  ·  {y}", "Developed by {a}  ·  {l} License  ·  {y}",
               "Desarrollado por {a}  ·  Licencia {l}  ·  {y}", "Entwickelt von {a}  ·  {l}-Lizenz  ·  {y}"),
    "lien_github": ("Page du projet sur GitHub", "Project page on GitHub", "Página del proyecto en GitHub",
                    "Projektseite auf GitHub"),
    "unite_go": ("Go", "GB", "GB", "GB"),
    "unite_mo": ("Mo", "MB", "MB", "MB"),
    "touche_suppr": ("Suppr", "Del", "Supr", "Entf"),
    "fermer": ("Fermer", "Close", "Cerrar", "Schließen"),
    "copier_tout": ("Tout copier", "Copy all", "Copiar todo", "Alles kopieren"),
    "quitter_t": ("Quitter", "Quit", "Salir", "Beenden"),
    "quitter_q": ("Un test ou un transfert est en cours : il sera interrompu.\n\nQuitter quand même ?",
                  "A test or a transfer is running: it will be interrupted.\n\nQuit anyway?",
                  "Hay una prueba o una transferencia en curso: se interrumpirá.\n\n¿Salir de todos modos?",
                  "Ein Test oder eine Übertragung läuft: sie wird abgebrochen.\n\nTrotzdem beenden?"),

    # ----- Barre de menus -----
    "m_fichier": ("Fichier", "File", "Archivo", "Datei"),
    "m_modeles": ("Modèles", "Models", "Modelos", "Modelle"),
    "m_outils": ("Outils", "Tools", "Herramientas", "Extras"),
    "m_aide": ("Aide", "Help", "Ayuda", "Hilfe"),
    "m_importer": ("Importer un modèle...", "Import a model...", "Importar un modelo...", "Modell importieren..."),
    "m_ouvrir_modeles": ("Ouvrir le dossier des modèles", "Open models folder",
                         "Abrir la carpeta de modelos", "Modellordner öffnen"),
    "m_telecharger": ("Télécharger un modèle...", "Download a model...", "Descargar un modelo...",
                      "Modell herunterladen..."),
    "m_maj": ("Mettre à jour la sélection", "Update selection", "Actualizar la selección", "Auswahl aktualisieren"),
    "m_copier_sous": ("Copier sous un autre nom...", "Copy under another name...", "Copiar con otro nombre...",
                      "Unter anderem Namen kopieren..."),
    "m_supprimer": ("Supprimer la sélection...", "Delete selection...", "Eliminar la selección...",
                    "Auswahl löschen..."),
    "m_decharger": ("Décharger de la mémoire", "Unload from memory", "Descargar de la memoria",
                    "Aus dem Speicher entladen"),
    "m_modelfile": ("Voir le Modelfile...", "Show Modelfile...", "Ver el Modelfile...", "Modelfile anzeigen..."),
    "m_actualiser": ("Actualiser la liste", "Refresh list", "Actualizar la lista", "Liste aktualisieren"),
    "m_rechercher": ("Rechercher", "Search", "Buscar", "Suchen"),
    "m_voir_bench": ("Ouvrir l'onglet Benchmark", "Open the Benchmark tab", "Abrir la pestaña Benchmark",
                     "Registerkarte Benchmark öffnen"),
    "m_apropos": ("À propos...", "About...", "Acerca de...", "Über..."),
    "apropos_texte": ("Gestion des modèles de langage locaux d'Ollama : téléchargement, mise à jour, copie, "
                      "suppression, export et import, suivi de la mémoire GPU.\n\n"
                      "Onglet Benchmark : évaluation des capacités de codage (assembleur, décompilation, "
                      "raisonnement).",
                      "Management of Ollama's local language models: download, update, copy, delete, "
                      "export and import, GPU memory monitoring.\n\n"
                      "Benchmark tab: evaluation of coding skills (assembly, decompilation, reasoning).",
                      "Gestión de los modelos de lenguaje locales de Ollama: descarga, actualización, copia, "
                      "eliminación, exportación e importación, seguimiento de la memoria GPU.\n\n"
                      "Pestaña Benchmark: evaluación de las capacidades de programación (ensamblador, "
                      "descompilación, razonamiento).",
                      "Verwaltung der lokalen Sprachmodelle von Ollama: Herunterladen, Aktualisieren, Kopieren, "
                      "Löschen, Export und Import, Überwachung des GPU-Speichers.\n\n"
                      "Registerkarte Benchmark: Bewertung der Programmierfähigkeiten (Assembler, "
                      "Dekompilierung, logisches Denken)."),

    # ----- Onglet Modèles -----
    "tb_telecharger": ("+  Télécharger...", "+  Download...", "+  Descargar...", "+  Herunterladen..."),
    "tb_exporter": ("Exporter...", "Export...", "Exportar...", "Exportieren..."),
    "tb_maj": ("Mettre à jour", "Update", "Actualizar", "Aktualisieren"),
    "tb_decharger": ("Décharger", "Unload", "Descargar de memoria", "Entladen"),
    "tb_actualiser": ("Actualiser", "Refresh", "Actualizar lista", "Neu laden"),
    "rechercher": ("Rechercher :", "Search:", "Buscar:", "Suchen:"),
    "col_params": ("Paramètres", "Parameters", "Parámetros", "Parameter"),
    "col_quantif": ("Quantif.", "Quant.", "Cuantif.", "Quant."),
    "col_contexte": ("Contexte max", "Max context", "Contexto máx.", "Max. Kontext"),
    "col_memoire": ("En mémoire", "In memory", "En memoria", "Im Speicher"),
    "mem_gpu": ("● {p} % GPU", "● {p} % GPU", "● {p} % GPU", "● {p} % GPU"),
    "resume_liste": ("{n} modèle(s) - {t} sur le disque", "{n} model(s) - {t} on disk",
                     "{n} modelo(s) - {t} en el disco", "{n} Modell(e) - {t} auf der Festplatte"),
    "resume_libre": ("espace libre : {l}", "free space: {l}", "espacio libre: {l}", "freier Platz: {l}"),
    "resume_filtre": ("{a} affiché(s)", "{a} shown", "{a} mostrado(s)", "{a} angezeigt"),
    "liste_vide_ollama": ("Ollama ne répond pas.\nLancez Ollama : la liste se mettra à jour toute seule.",
                          "Ollama is not responding.\nStart Ollama: the list will update by itself.",
                          "Ollama no responde.\nInicie Ollama: la lista se actualizará sola.",
                          "Ollama antwortet nicht.\nStarten Sie Ollama: die Liste aktualisiert sich von selbst."),
    "liste_vide": ("Aucun modèle installé.\nCliquez sur « Télécharger... » pour en ajouter un.",
                   "No model installed.\nClick \"Download...\" to add one.",
                   "Ningún modelo instalado.\nPulse «Descargar...» para añadir uno.",
                   "Kein Modell installiert.\nKlicken Sie auf „Herunterladen...“, um eines hinzuzufügen."),
    "liste_vide_filtre": ("Aucun modèle ne correspond à la recherche.", "No model matches the search.",
                          "Ningún modelo coincide con la búsqueda.", "Kein Modell entspricht der Suche."),
    "sb_pret": ("Prêt", "Ready", "Listo", "Bereit"),
    "sb_chargement": ("Lecture de la liste des modèles...", "Reading the model list...",
                      "Leyendo la lista de modelos...", "Modellliste wird gelesen..."),
    "sb_telech": ("Téléchargement : {n}", "Downloading: {n}", "Descargando: {n}", "Herunterladen: {n}"),
    "sb_export": ("Export en cours...", "Exporting...", "Exportando...", "Export läuft..."),
    "sb_import": ("Import en cours...", "Importing...", "Importando...", "Import läuft..."),
    "sb_test": ("Benchmark en cours : {n} modèle(s)", "Benchmark running: {n} model(s)",
                "Benchmark en curso: {n} modelo(s)", "Benchmark läuft: {n} Modell(e)"),
    "det_titre": ("Détails du modèle", "Model details", "Detalles del modelo", "Modelldetails"),
    "det_aucun": ("Sélectionnez un modèle dans la liste pour voir ses détails.",
                  "Select a model in the list to see its details.",
                  "Seleccione un modelo en la lista para ver sus detalles.",
                  "Wählen Sie ein Modell in der Liste, um die Details zu sehen."),
    "det_plusieurs": ("{n} modèles sélectionnés", "{n} models selected", "{n} modelos seleccionados",
                      "{n} Modelle ausgewählt"),
    "det_total": ("{t} au total", "{t} in total", "{t} en total", "{t} insgesamt"),
    "det_base": ("Basé sur : {p}", "Based on: {p}", "Basado en: {p}", "Basiert auf: {p}"),
    "det_famille": ("Famille", "Family", "Familia", "Familie"),
    "det_params": ("Paramètres", "Parameters", "Parámetros", "Parameter"),
    "det_quantif": ("Quantification", "Quantization", "Cuantificación", "Quantisierung"),
    "det_format": ("Format", "Format", "Formato", "Format"),
    "det_taille": ("Taille", "Size", "Tamaño", "Größe"),
    "det_contexte": ("Contexte max", "Max context", "Contexto máx.", "Max. Kontext"),
    "det_capacites": ("Capacités", "Capabilities", "Capacidades", "Fähigkeiten"),
    "det_date": ("Modifié le", "Modified on", "Modificado el", "Geändert am"),
    "det_empreinte": ("Empreinte", "Digest", "Huella", "Prüfsumme"),
    "det_memoire": ("En mémoire", "In memory", "En memoria", "Im Speicher"),
    "det_non": ("non", "no", "no", "nein"),
    "det_oui_mem": ("oui - {p} % sur le GPU ({t})", "yes - {p} % on the GPU ({t})",
                    "sí - {p} % en la GPU ({t})", "ja - {p} % auf der GPU ({t})"),
    "det_chargement": ("chargement...", "loading...", "cargando...", "wird geladen..."),
    "cap_completion": ("texte", "text", "texto", "Text"),
    "cap_tools": ("outils", "tools", "herramientas", "Werkzeuge"),
    "cap_thinking": ("réflexion", "thinking", "razonamiento", "Denkmodus"),
    "cap_vision": ("vision (images)", "vision (images)", "visión (imágenes)", "Bilderkennung"),
    "cap_embedding": ("embeddings", "embeddings", "embeddings", "Embeddings"),
    "cap_insert": ("complétion de code", "code completion", "completado de código", "Code-Vervollständigung"),
    "btn_bench": ("Ajouter au benchmark", "Add to benchmark", "Añadir al benchmark", "Zum Benchmark hinzufügen"),
    "bench_ajoute": ("Ajouté au benchmark : {n}", "Added to benchmark: {n}", "Añadido al benchmark: {n}",
                     "Zum Benchmark hinzugefügt: {n}"),
    "cp_titre": ("Copier sous un autre nom", "Copy under another name", "Copiar con otro nombre",
                 "Unter anderem Namen kopieren"),
    "cp_question": ("Nouveau nom pour la copie de « {n} » :", "New name for the copy of \"{n}\":",
                    "Nuevo nombre para la copia de «{n}»:", "Neuer Name für die Kopie von „{n}“:"),
    "cp_aide": ("Comme « ollama cp ». Les gros fichiers sont partagés : la copie ne prend presque pas de place.\n"
                "Exemple : mon-gemma:latest",
                "Like \"ollama cp\". Large files are shared: the copy takes almost no space.\n"
                "Example: my-gemma:latest",
                "Como «ollama cp». Los archivos grandes se comparten: la copia casi no ocupa espacio.\n"
                "Ejemplo: mi-gemma:latest",
                "Wie „ollama cp“. Große Dateien werden geteilt: die Kopie braucht fast keinen Platz.\n"
                "Beispiel: mein-gemma:latest"),
    "cp_bouton": ("Copier", "Copy", "Copiar", "Kopieren"),
    "cp_ok": ("Copie créée : {n}", "Copy created: {n}", "Copia creada: {n}", "Kopie erstellt: {n}"),
    "cp_echec": ("La copie a échoué :\n{e}", "The copy failed:\n{e}", "La copia ha fallado:\n{e}",
                 "Das Kopieren ist fehlgeschlagen:\n{e}"),
    "cp_un_seul": ("Sélectionnez un seul modèle.", "Select only one model.", "Seleccione un solo modelo.",
                   "Wählen Sie nur ein Modell aus."),
    "cp_existe": ("Un modèle porte déjà ce nom.", "A model already has this name.",
                  "Ya existe un modelo con este nombre.", "Ein Modell mit diesem Namen existiert bereits."),
    "maj_q": ("Mettre à jour depuis Internet :\n- {n}\n\nSeuls les morceaux qui ont changé sont téléchargés.",
              "Update from the Internet:\n- {n}\n\nOnly the parts that changed are downloaded.",
              "Actualizar desde Internet:\n- {n}\n\nSolo se descargan las partes que han cambiado.",
              "Aus dem Internet aktualisieren:\n- {n}\n\nNur geänderte Teile werden heruntergeladen."),
    "maj_ok": ("Mise à jour terminée.", "Update finished.", "Actualización terminada.", "Aktualisierung abgeschlossen."),
    "decharge_ok": ("Déchargé de la mémoire : {n}", "Unloaded from memory: {n}", "Descargado de la memoria: {n}",
                    "Aus dem Speicher entladen: {n}"),
    "modelfile_titre": ("Modelfile - {n}", "Modelfile - {n}", "Modelfile - {n}", "Modelfile - {n}"),

    # ----- Onglet Benchmark -----
    "bench_titre": ("Évaluation des capacités de codage", "Coding skills evaluation",
                    "Evaluación de las capacidades de programación", "Bewertung der Programmierfähigkeiten"),
    "bench_texte": ("Ce test pose {n} exercices difficiles à chaque modèle ({p} points) : décompilation "
                    "d'assembleur x86, lecture de pseudo-C Ghidra et de bytecode Python, exécution de x86 et de "
                    "Z80 de tête, écriture d'un mini-interpréteur. Chaque réponse est vérifiée automatiquement ; "
                    "le résumé donne un classement global et par capacité.",
                    "This test gives each model {n} hard exercises ({p} points): x86 assembly decompilation, "
                    "reading Ghidra pseudo-C and Python bytecode, running x86 and Z80 in its head, writing a "
                    "mini interpreter. Every answer is checked automatically; the summary gives an overall "
                    "ranking and a ranking per skill.",
                    "Esta prueba plantea {n} ejercicios difíciles a cada modelo ({p} puntos): descompilación "
                    "de ensamblador x86, lectura de pseudo-C de Ghidra y de bytecode Python, ejecución mental "
                    "de x86 y Z80, escritura de un mini intérprete. Cada respuesta se verifica automáticamente; "
                    "el resumen da una clasificación global y por capacidad.",
                    "Dieser Test stellt jedem Modell {n} schwierige Aufgaben ({p} Punkte): x86-Assembler "
                    "dekompilieren, Ghidra-Pseudo-C und Python-Bytecode lesen, x86 und Z80 im Kopf ausführen, "
                    "einen Mini-Interpreter schreiben. Jede Antwort wird automatisch geprüft; die "
                    "Zusammenfassung zeigt eine Gesamtrangliste und eine Rangliste pro Fähigkeit."),
    "bench_attention": ("Attention : le code Python écrit par les modèles est exécuté sur ce PC (dans un dossier "
                        "temporaire, 20 secondes au maximum). Les questions restent en français dans toutes les "
                        "langues.",
                        "Warning: the Python code written by the models is run on this PC (in a temporary "
                        "folder, 20 seconds at most). The questions stay in French whatever the language.",
                        "Atención: el código Python escrito por los modelos se ejecuta en este PC (en una carpeta "
                        "temporal, 20 segundos como máximo). Las preguntas siguen en francés en todos los idiomas.",
                        "Achtung: der von den Modellen geschriebene Python-Code wird auf diesem PC ausgeführt (in "
                        "einem temporären Ordner, höchstens 20 Sekunden). Die Fragen bleiben in jeder Sprache "
                        "auf Französisch."),
    "bench_selection": ("Ajouter la sélection de l'onglet Modèles", "Add the selection from the Models tab",
                        "Añadir la selección de la pestaña Modelos", "Auswahl aus „Modelle“ hinzufügen"),
    "bench_avance": ("{a} / {b} exercices", "{a} / {b} exercises", "{a} / {b} ejercicios", "{a} / {b} Aufgaben"),
    "cadre_modeles": ("Modèles à évaluer (choisissez dans la liste ou collez un nom ; champs vides et doublons ignorés)",
                      "Models to evaluate (pick from the list or paste a name; empty fields and duplicates are ignored)",
                      "Modelos a evaluar (elija en la lista o pegue un nombre; se ignoran los campos vacíos y los duplicados)",
                      "Zu bewertende Modelle (aus der Liste wählen oder Namen einfügen; leere Felder und Doppelte werden ignoriert)"),
    "champ_modele": ("Modèle {n} :", "Model {n}:", "Modelo {n}:", "Modell {n}:"),
    "reflexion": ("Mode réflexion (plus juste mais beaucoup plus lent)",
                  "Thinking mode (more accurate but much slower)",
                  "Modo razonamiento (más preciso pero mucho más lento)",
                  "Denkmodus (genauer, aber viel langsamer)"),
    "vider": ("Vider les champs", "Clear fields", "Vaciar los campos", "Felder leeren"),
    "lancer": ("▶  Lancer le test", "▶  Run the test", "▶  Iniciar la prueba", "▶  Test starten"),
    "arreter": ("Arrêter", "Stop", "Detener", "Anhalten"),
    "pdf": ("Exporter le rapport PDF", "Export PDF report", "Exportar el informe PDF", "PDF-Bericht exportieren"),
    "ouvrir_dossier": ("Ouvrir le dossier des résultats", "Open results folder",
                       "Abrir la carpeta de resultados", "Ergebnisordner öffnen"),
    "msg_dossier": ("Les résultats du benchmark seront enregistrés dans : {d}",
                    "Benchmark results will be saved in: {d}",
                    "Los resultados del benchmark se guardarán en: {d}",
                    "Die Benchmark-Ergebnisse werden gespeichert in: {d}"),
    "msg_n_installes": ("{n} modèle(s) installé(s) trouvé(s).", "{n} installed model(s) found.",
                        "{n} modelo(s) instalado(s) encontrado(s).", "{n} installierte(s) Modell(e) gefunden."),
    "msg_ollama_debut": ("Ollama ne répond pas pour l'instant : lancez-le, la liste des modèles se mettra à jour toute seule.",
                         "Ollama is not responding yet: start it, the model list will update by itself.",
                         "Ollama no responde por ahora: inícielo, la lista de modelos se actualizará sola.",
                         "Ollama antwortet noch nicht: starten Sie es, die Modellliste aktualisiert sich von selbst."),
    "saisir_un": ("Saisissez au moins un modèle.", "Enter at least one model.",
                  "Introduzca al menos un modelo.", "Geben Sie mindestens ein Modell ein."),
    "lancement": ("\nLancement : {n} modèle(s).", "\nStarting: {n} model(s).",
                  "\nInicio: {n} modelo(s).", "\nStart: {n} Modell(e)."),
    "arret_demande": ("Arrêt demandé : le test s'arrêtera après l'exercice en cours.",
                      "Stop requested: the test will stop after the current exercise.",
                      "Parada solicitada: la prueba se detendrá tras el ejercicio en curso.",
                      "Abbruch angefordert: der Test stoppt nach der laufenden Aufgabe."),
    "termine": ("\nTerminé. Vous pouvez exporter le rapport PDF.", "\nDone. You can export the PDF report.",
                "\nTerminado. Puede exportar el informe PDF.", "\nFertig. Sie können den PDF-Bericht exportieren."),
    "erreur_inattendue": ("Erreur inattendue : {e}", "Unexpected error: {e}",
                          "Error inesperado: {e}", "Unerwarteter Fehler: {e}"),

    # ----- Fenêtre Réglages -----
    "reglages": ("Réglages", "Settings", "Ajustes", "Einstellungen"),
    "version": ("Version du logiciel : {v}", "Software version: {v}",
                "Versión del programa: {v}", "Softwareversion: {v}"),
    "langue": ("Langue :", "Language:", "Idioma:", "Sprache:"),
    "contexte": ("Taille du contexte (context length) :", "Context length:",
                 "Tamaño del contexto (context length):", "Kontextlänge (context length):"),
    "auto": ("Auto", "Auto", "Auto", "Auto"),
    "contexte_bulle": (
        "Taille du contexte (context length, « num_ctx » dans Ollama) : c'est la mémoire de travail du "
        "modèle, comptée en tokens (1 token = 3 à 4 caractères environ). Elle doit contenir la question, "
        "la réflexion du modèle et sa réponse.\n\n"
        "Plus grande : le modèle peut traiter des listings plus longs, mais il utilise plus de mémoire "
        "(VRAM puis RAM) et peut devenir beaucoup plus lent.\n"
        "Trop petite : la question ou la réponse est coupée et le score baisse.\n\n"
        "Auto (conseillé) : 8192 sans réflexion, 16384 avec réflexion.",
        "Context length (\"num_ctx\" in Ollama) is the model's working memory, counted in tokens "
        "(1 token is about 3 to 4 characters). It must hold the question, the model's thinking and "
        "its answer.\n\n"
        "Larger: the model can handle longer listings, but it uses more memory (VRAM, then RAM) and "
        "may become much slower.\n"
        "Too small: the question or the answer gets cut off and the score drops.\n\n"
        "Auto (recommended): 8192 without thinking, 16384 with thinking.",
        "Tamaño del contexto (context length, «num_ctx» en Ollama): es la memoria de trabajo del "
        "modelo, contada en tokens (1 token = unos 3 a 4 caracteres). Debe contener la pregunta, el "
        "razonamiento del modelo y su respuesta.\n\n"
        "Más grande: el modelo puede tratar listados más largos, pero usa más memoria (VRAM y luego "
        "RAM) y puede volverse mucho más lento.\n"
        "Demasiado pequeño: la pregunta o la respuesta se cortan y la puntuación baja.\n\n"
        "Auto (recomendado): 8192 sin razonamiento, 16384 con razonamiento.",
        "Kontextlänge (context length, „num_ctx“ in Ollama): das Arbeitsgedächtnis des Modells, "
        "gemessen in Tokens (1 Token = etwa 3 bis 4 Zeichen). Es muss die Frage, das Nachdenken des "
        "Modells und seine Antwort enthalten.\n\n"
        "Größer: das Modell kann längere Listings verarbeiten, braucht aber mehr Speicher (VRAM, dann "
        "RAM) und kann viel langsamer werden.\n"
        "Zu klein: Frage oder Antwort werden abgeschnitten und die Punktzahl sinkt.\n\n"
        "Auto (empfohlen): 8192 ohne Denkmodus, 16384 mit Denkmodus."),
    "enregistrer": ("Enregistrer", "Save", "Guardar", "Speichern"),
    "annuler": ("Annuler", "Cancel", "Cancelar", "Abbrechen"),
    "contexte_invalide": ("La taille du contexte doit être « Auto » ou un nombre entre 2048 et 262144.",
                          "Context length must be \"Auto\" or a number between 2048 and 262144.",
                          "El tamaño del contexto debe ser «Auto» o un número entre 2048 y 262144.",
                          "Die Kontextlänge muss „Auto“ oder eine Zahl zwischen 2048 und 262144 sein."),
    "langue_plus_tard": ("Un test ou un transfert est en cours : la nouvelle langue sera appliquée au prochain démarrage.",
                         "A test or a transfer is running: the new language will be applied at next start.",
                         "Hay una prueba o una transferencia en curso: el nuevo idioma se aplicará en el próximo inicio.",
                         "Ein Test oder eine Übertragung läuft: die neue Sprache wird beim nächsten Start übernommen."),
    "reglages_ok": ("Réglages enregistrés : langue {l}, contexte {c}.", "Settings saved: language {l}, context {c}.",
                    "Ajustes guardados: idioma {l}, contexto {c}.", "Einstellungen gespeichert: Sprache {l}, Kontext {c}."),
    "reglages_non_sauves": ("Attention : impossible d'écrire {f} (les réglages seront perdus à la fermeture).",
                            "Warning: cannot write {f} (settings will be lost on exit).",
                            "Atención: no se puede escribir {f} (los ajustes se perderán al cerrar).",
                            "Achtung: {f} kann nicht geschrieben werden (Einstellungen gehen beim Beenden verloren)."),

    # ----- Déroulement du test -----
    "ollama_absent": ("Ollama ne répond pas (ou aucun modèle installé). Lancez Ollama puis réessayez.",
                      "Ollama is not responding (or no model installed). Start Ollama and try again.",
                      "Ollama no responde (o no hay modelos instalados). Inicie Ollama y vuelva a intentarlo.",
                      "Ollama antwortet nicht (oder kein Modell installiert). Starten Sie Ollama und versuchen Sie es erneut."),
    "mode_reflexion": ("Mode réflexion : {etat}", "Thinking mode: {etat}", "Modo razonamiento: {etat}", "Denkmodus: {etat}"),
    "active": ("activé", "on", "activado", "an"),
    "desactive": ("désactivé", "off", "desactivado", "aus"),
    "ctx_info": ("Taille du contexte : {c} tokens", "Context length: {c} tokens",
                 "Tamaño del contexto: {c} tokens", "Kontextlänge: {c} Tokens"),
    "ignore": ("\n[ignoré] {m} n'est pas installé (vérifiez le nom avec 'ollama list').",
               "\n[skipped] {m} is not installed (check the name with 'ollama list').",
               "\n[ignorado] {m} no está instalado (compruebe el nombre con 'ollama list').",
               "\n[übersprungen] {m} ist nicht installiert (Namen mit 'ollama list' prüfen)."),
    "erreur_ex": ("  {ex} : ERREUR {e}", "  {ex}: ERROR {e}", "  {ex}: ERROR {e}", "  {ex}: FEHLER {e}"),
    "echec_base": ("  ATTENTION : {m} échoue au test de base. Il répond sans doute au mauvais format "
                   "(pas de code Python) : ses autres résultats seront probablement à 0.",
                   "  WARNING: {m} fails the basic test. It probably answers in the wrong format "
                   "(no Python code): its other results will probably be 0.",
                   "  ATENCIÓN: {m} falla la prueba básica. Probablemente responde en un formato incorrecto "
                   "(sin código Python): sus otros resultados serán probablemente 0.",
                   "  ACHTUNG: {m} besteht den Basistest nicht. Es antwortet wohl im falschen Format "
                   "(kein Python-Code): die übrigen Ergebnisse werden wahrscheinlich 0 sein."),
    "ecriture_impossible": ("Impossible d'écrire les fichiers : {e}", "Cannot write the files: {e}",
                            "No se pueden escribir los archivos: {e}", "Dateien können nicht geschrieben werden: {e}"),
    "aucun_resultat": ("\nAucun résultat à résumer.", "\nNo results to summarize.",
                       "\nNingún resultado que resumir.", "\nKeine Ergebnisse zum Zusammenfassen."),
    "resume_impossible": ("Impossible d'écrire le résumé : {e}", "Cannot write the summary: {e}",
                          "No se puede escribir el resumen: {e}", "Zusammenfassung kann nicht geschrieben werden: {e}"),
    "titre_global": ("===== SCORE GLOBAL PAR MODÈLE =====", "===== OVERALL SCORE PER MODEL =====",
                     "===== PUNTUACIÓN GLOBAL POR MODELO =====", "===== GESAMTPUNKTZAHL PRO MODELL ====="),
    "titre_capacites": ("===== CLASSEMENT PAR CAPACITÉ =====", "===== RANKING BY SKILL =====",
                        "===== CLASIFICACIÓN POR CAPACIDAD =====", "===== RANGLISTE NACH FÄHIGKEIT ====="),
    "fichiers_crees": ("\nFichiers créés dans : {d}", "\nFiles created in: {d}",
                       "\nArchivos creados en: {d}", "\nDateien erstellt in: {d}"),
    "resume_titre": ("Résultats du {date} - réflexion {etat} - contexte {c}",
                     "Results of {date} - thinking {etat} - context {c}",
                     "Resultados del {date} - razonamiento {etat} - contexto {c}",
                     "Ergebnisse vom {date} - Denkmodus {etat} - Kontext {c}"),
    "md_global": ("Classement global", "Overall ranking", "Clasificación global", "Gesamtrangliste"),
    "md_capacites": ("Classement par capacité", "Ranking by skill", "Clasificación por capacidad", "Rangliste nach Fähigkeit"),
    "md_meilleurs": ("Meilleur modèle par capacité", "Best model per skill",
                     "Mejor modelo por capacidad", "Bestes Modell pro Fähigkeit"),
    "reflexion_md": ("Réflexion", "Thinking", "Razonamiento", "Nachdenken"),
    "col_rang": ("Rang", "Rank", "Puesto", "Rang"),
    "col_modele": ("Modèle", "Model", "Modelo", "Modell"),
    "col_score": ("Score global", "Overall score", "Puntuación global", "Gesamtpunktzahl"),
    "col_points": ("Points", "Points", "Puntos", "Punkte"),
    "col_parfaits": ("Parfaits", "Perfect", "Perfectos", "Perfekt"),
    "col_detail": ("Détail ex. {a} à {b}", "Detail ex. {a} to {b}", "Detalle ej. {a} a {b}", "Detail Aufg. {a} bis {b}"),
    "col_vitesse": ("tokens/s", "tokens/s", "tokens/s", "Tokens/s"),
    "col_temps": ("temps total", "total time", "tiempo total", "Gesamtzeit"),
    "col_ppm": ("points/min", "points/min", "puntos/min", "Punkte/Min"),
    "col_gpu": ("% GPU", "% GPU", "% GPU", "% GPU"),
    "col_global": ("Global", "Overall", "Global", "Gesamt"),
    "aucun": ("aucun", "none", "ninguno", "keins"),

    # ----- Capacités -----
    "cat_base": ("Bases", "Basics", "Básico", "Grundlagen"),
    "cat_decomp": ("Décompilation assembleur", "Assembly decompilation", "Descompilación de ensamblador", "Assembler-Dekompilierung"),
    "cat_lecture": ("Lecture de code (Ghidra, bytecode)", "Code reading (Ghidra, bytecode)",
                    "Lectura de código (Ghidra, bytecode)", "Code lesen (Ghidra, Bytecode)"),
    "cat_tete": ("Exécution de tête", "Mental execution", "Ejecución mental", "Im Kopf ausführen"),
    "cat_prog": ("Programmation", "Programming", "Programación", "Programmierung"),
    # versions courtes pour les en-têtes de tableau du PDF
    "catc_base": ("Bases", "Basics", "Básico", "Basis"),
    "catc_decomp": ("Décompil.", "Decompil.", "Descompil.", "Dekompil."),
    "catc_lecture": ("Lecture", "Reading", "Lectura", "Lesen"),
    "catc_tete": ("De tête", "Mental", "Mental", "Im Kopf"),
    "catc_prog": ("Progr.", "Coding", "Progr.", "Progr."),

    # ----- Noms des exercices (affichage) -----
    "ex0": ("0 Test de base (Python simple)", "0 Basic test (simple Python)",
            "0 Prueba básica (Python sencillo)", "0 Basistest (einfaches Python)"),
    "ex1": ("1 Décompiler x86 (division optimisée)", "1 Decompile x86 (optimized division)",
            "1 Descompilar x86 (división optimizada)", "1 x86 dekompilieren (optimierte Division)"),
    "ex2": ("2 Décompiler x86 (tableau)", "2 Decompile x86 (array)",
            "2 Descompilar x86 (tabla)", "2 x86 dekompilieren (Array)"),
    "ex3": ("3 Pseudo-C Ghidra -> Python", "3 Ghidra pseudo-C -> Python",
            "3 Pseudo-C de Ghidra -> Python", "3 Ghidra-Pseudo-C -> Python"),
    "ex4": ("4 Bytecode Python -> source", "4 Python bytecode -> source",
            "4 Bytecode Python -> código fuente", "4 Python-Bytecode -> Quelltext"),
    "ex5": ("5 Exécuter du x86 de tête", "5 Run x86 in your head",
            "5 Ejecutar x86 mentalmente", "5 x86 im Kopf ausführen"),
    "ex6": ("6 Exécuter du Z80 de tête", "6 Run Z80 in your head",
            "6 Ejecutar Z80 mentalmente", "6 Z80 im Kopf ausführen"),
    "ex7": ("7 Écrire un mini-interpréteur", "7 Write a mini interpreter",
            "7 Escribir un mini intérprete", "7 Einen Mini-Interpreter schreiben"),
    "ex8": ("8 Comprendre du x86 32 bits (pile)", "8 Understand 32-bit x86 (stack)",
            "8 Entender x86 de 32 bits (pila)", "8 32-Bit-x86 verstehen (Stack)"),

    # ----- Rapport PDF -----
    "pdf_titre": ("Rapport de comparaison de modèles", "Model comparison report",
                  "Informe de comparación de modelos", "Modellvergleichsbericht"),
    "pdf_sous_titre": ("Code hardcore : assembleur, décompilation, raisonnement",
                       "Hardcore code: assembly, decompilation, reasoning",
                       "Código hardcore: ensamblador, descompilación, razonamiento",
                       "Hardcore-Code: Assembler, Dekompilierung, Denken"),
    "pdf_date": ("Date des résultats", "Results date", "Fecha de resultados", "Datum der Ergebnisse"),
    "pdf_mode": ("Mode réflexion", "Thinking mode", "Modo razonamiento", "Denkmodus"),
    "pdf_ctx": ("Contexte", "Context", "Contexto", "Kontext"),
    "pdf_nb_modeles": ("Modèles testés", "Models tested", "Modelos probados", "Getestete Modelle"),
    "pdf_machine": ("Machine : 8 Go de VRAM, 16 Go de RAM  -  {n} exercices, {p} points au total",
                    "Machine: 8 GB VRAM, 16 GB RAM  -  {n} exercises, {p} points in total",
                    "Equipo: 8 GB de VRAM, 16 GB de RAM  -  {n} ejercicios, {p} puntos en total",
                    "Rechner: 8 GB VRAM, 16 GB RAM  -  {n} Aufgaben, {p} Punkte insgesamt"),
    "pdf_classement": ("Classement global", "Overall ranking", "Clasificación global", "Gesamtrangliste"),
    "pdf_ligne_modele": ("{p}/{s} points  -  {f}/{n} exercices parfaits  -  {v} tokens/s  -  {t}",
                         "{p}/{s} points  -  {f}/{n} perfect exercises  -  {v} tokens/s  -  {t}",
                         "{p}/{s} puntos  -  {f}/{n} ejercicios perfectos  -  {v} tokens/s  -  {t}",
                         "{p}/{s} Punkte  -  {f}/{n} perfekte Aufgaben  -  {v} Tokens/s  -  {t}"),
    "pdf_echec_base": ("échoue au test de base", "fails the basic test", "falla la prueba básica", "besteht den Basistest nicht"),
    "pdf_capacites": ("Classement par capacité", "Ranking by skill", "Clasificación por capacidad", "Rangliste nach Fähigkeit"),
    "pdf_meilleurs": ("Meilleur modèle par capacité", "Best model per skill",
                      "Mejor modelo por capacidad", "Bestes Modell pro Fähigkeit"),
    "pdf_detail": ("Détail par exercice (points obtenus / points possibles)",
                   "Detail per exercise (points scored / possible points)",
                   "Detalle por ejercicio (puntos obtenidos / puntos posibles)",
                   "Detail pro Aufgabe (erreichte / mögliche Punkte)"),
    "pdf_perf": ("Vitesse et temps", "Speed and time", "Velocidad y tiempo", "Geschwindigkeit und Zeit"),
    "pdf_liste_ex": ("Les exercices", "The exercises", "Los ejercicios", "Die Aufgaben"),
    "pdf_ex_ligne": ("{p} points  -  capacité : {c}", "{p} points  -  skill: {c}",
                     "{p} puntos  -  capacidad: {c}", "{p} Punkte  -  Fähigkeit: {c}"),
    "pdf_rappel": ("Rappel : un écart de 2 ou 3 points peut varier d'un lancement à l'autre. "
                   "Les questions posées aux modèles sont en français dans toutes les langues.",
                   "Note: a gap of 2 or 3 points can vary from one run to another. "
                   "The questions asked to the models are in French whatever the language.",
                   "Nota: una diferencia de 2 o 3 puntos puede variar de una ejecución a otra. "
                   "Las preguntas a los modelos están en francés en todos los idiomas.",
                   "Hinweis: ein Unterschied von 2 oder 3 Punkten kann von Lauf zu Lauf schwanken. "
                   "Die Fragen an die Modelle sind in jeder Sprache auf Französisch."),
    "pdf_legende": ("Couleurs : vert = 67 % et plus, orange = 34 à 66 %, rouge = 33 % et moins.",
                    "Colors: green = 67 % and more, orange = 34 to 66 %, red = 33 % and less.",
                    "Colores: verde = 67 % o más, naranja = 34 a 66 %, rojo = 33 % o menos.",
                    "Farben: grün = 67 % und mehr, orange = 34 bis 66 %, rot = 33 % und weniger."),
    "pdf_source": ("Source : {f}", "Source: {f}", "Fuente: {f}", "Quelle: {f}"),
    "pdf_box": ("Rapport PDF", "PDF report", "Informe PDF", "PDF-Bericht"),
    "pdf_aucun_test": ("Aucun résultat : lancez d'abord un test.", "No results: run a test first.",
                       "Sin resultados: inicie primero una prueba.", "Keine Ergebnisse: starten Sie zuerst einen Test."),
    "pdf_cree": ("Rapport PDF créé : {c}", "PDF report created: {c}", "Informe PDF creado: {c}", "PDF-Bericht erstellt: {c}"),
    "pdf_ouvrir": ("Rapport créé :\n{n}\n\nL'ouvrir maintenant ?", "Report created:\n{n}\n\nOpen it now?",
                   "Informe creado:\n{n}\n\n¿Abrirlo ahora?", "Bericht erstellt:\n{n}\n\nJetzt öffnen?"),
    "pdf_impossible": ("Impossible de créer le rapport :\n{e}", "Cannot create the report:\n{e}",
                       "No se puede crear el informe:\n{e}", "Bericht kann nicht erstellt werden:\n{e}"),
    "pdf_vide": ("aucun résultat exploitable", "no usable results", "ningún resultado utilizable", "keine verwertbaren Ergebnisse"),
    "pdf_page": ("Page {i} / {n}", "Page {i} / {n}", "Página {i} / {n}", "Seite {i} / {n}"),

    # ----- Fenêtre Gestion des modèles -----
    "gm_col_nom": ("Nom du modèle", "Model name", "Nombre del modelo", "Modellname"),
    "gm_col_taille": ("Taille", "Size", "Tamaño", "Größe"),
    "gm_col_date": ("Modifié le", "Modified", "Modificado", "Geändert"),
    "gm_champs_pleins": ("Les {n} champs sont déjà remplis.", "All {n} fields are already filled.",
                         "Los {n} campos ya están llenos.", "Alle {n} Felder sind bereits ausgefüllt."),
    "gm_patientez_t": ("Patientez", "Please wait", "Espere", "Bitte warten"),
    "gm_patientez": ("Un téléchargement, un export ou un import est déjà en cours.",
                     "A download, an export or an import is already running.",
                     "Ya hay una descarga, una exportación o una importación en curso.",
                     "Ein Download, Export oder Import läuft bereits."),
    "erreur": ("ERREUR : {e}", "ERROR: {e}", "ERROR: {e}", "FEHLER: {e}"),
    "gm_exporter_t": ("Exporter", "Export", "Exportar", "Exportieren"),
    "gm_selection": ("Sélectionnez d'abord un ou plusieurs modèles.", "First select one or more models.",
                     "Seleccione primero uno o varios modelos.", "Wählen Sie zuerst ein oder mehrere Modelle aus."),
    "gm_exporter_dialog": ("Exporter le modèle", "Export the model", "Exportar el modelo", "Modell exportieren"),
    "gm_type_fichier": ("Fichier ZIP", "ZIP file", "Archivo ZIP", "ZIP-Datei"),
    "gm_export_de": ("\nExport de : {n}", "\nExporting: {n}", "\nExportación de: {n}", "\nExport von: {n}"),
    "gm_export_echec": ("L'export a échoué :\n{e}", "The export failed:\n{e}", "La exportación ha fallado:\n{e}", "Der Export ist fehlgeschlagen:\n{e}"),
    "gm_export_ok": ("Export terminé :\n{r}", "Export finished:\n{r}", "Exportación terminada:\n{r}", "Export abgeschlossen:\n{r}"),
    "gm_importer_t": ("Importer", "Import", "Importar", "Importieren"),
    "gm_importer_dialog": ("Importer un modèle", "Import a model", "Importar un modelo", "Ein Modell importieren"),
    "gm_import_invalide": ("Ce fichier n'est pas un export valable :\n{e}", "This file is not a valid export:\n{e}",
                           "Este archivo no es una exportación válida:\n{e}", "Diese Datei ist kein gültiger Export:\n{e}"),
    "gm_contenu": ("Modèle(s) contenu(s) :", "Model(s) inside:", "Modelo(s) contenido(s):", "Enthaltene(s) Modell(e):"),
    "gm_remplace": ("Déjà installé(s), sera remplacé : {n}", "Already installed, will be replaced: {n}",
                    "Ya instalado(s), se reemplazará: {n}", "Bereits installiert, wird ersetzt: {n}"),
    "gm_dossier_ollama": ("Dossier des modèles d'Ollama :\n{d}", "Ollama models folder:\n{d}",
                          "Carpeta de modelos de Ollama:\n{d}", "Ollama-Modellordner:\n{d}"),
    "gm_lancer_import": ("Lancer l'import ?", "Start the import?", "¿Iniciar la importación?", "Import starten?"),
    "gm_import_de": ("\nImport de : {c}", "\nImporting: {c}", "\nImportación de: {c}", "\nImport von: {c}"),
    "gm_import_echec": ("L'import a échoué :\n{e}", "The import failed:\n{e}", "La importación ha fallado:\n{e}", "Der Import ist fehlgeschlagen:\n{e}"),
    "gm_import_absents": ("Fichiers copiés, mais Ollama ne montre pas encore : {n}\nQuittez puis relancez Ollama.",
                          "Files copied, but Ollama does not show yet: {n}\nQuit and restart Ollama.",
                          "Archivos copiados, pero Ollama todavía no muestra: {n}\nCierre y vuelva a iniciar Ollama.",
                          "Dateien kopiert, aber Ollama zeigt noch nicht an: {n}\nOllama beenden und neu starten."),
    "gm_import_ok": ("Import terminé, le modèle est disponible.", "Import finished, the model is available.",
                     "Importación terminada, el modelo está disponible.", "Import abgeschlossen, das Modell ist verfügbar."),
    "gm_supprimer_t": ("Supprimer", "Delete", "Eliminar", "Löschen"),
    "gm_supprimer_q": ("Supprimer définitivement de votre disque :\n- {n}\n\nCette action ne peut pas être annulée.",
                       "Permanently delete from your disk:\n- {n}\n\nThis cannot be undone.",
                       "Eliminar definitivamente de su disco:\n- {n}\n\nEsta acción no se puede deshacer.",
                       "Endgültig von der Festplatte löschen:\n- {n}\n\nDies kann nicht rückgängig gemacht werden."),
    "gm_supprime": ("Modèle supprimé : {n}", "Model deleted: {n}", "Modelo eliminado: {n}", "Modell gelöscht: {n}"),
    "gm_supp_erreur": ("ERREUR suppression {n} : {e}", "ERROR deleting {n}: {e}", "ERROR al eliminar {n}: {e}", "FEHLER beim Löschen von {n}: {e}"),
    "gm_supp_echec": ("Échec pour :\n{e}", "Failed for:\n{e}", "Fallo para:\n{e}", "Fehlgeschlagen für:\n{e}"),
    "gm_ajouter_t": ("Télécharger un modèle", "Download a model", "Descargar un modelo", "Modell herunterladen"),
    "gm_ajouter_q": ("Nom du modèle à télécharger (comme pour « ollama pull ») :",
                     "Name of the model to download (as for \"ollama pull\"):",
                     "Nombre del modelo a descargar (como para «ollama pull»):",
                     "Name des herunterzuladenden Modells (wie bei „ollama pull“):"),
    "gm_exemples": ("Exemples : gemma4:e4b   gpt-oss:20b   hf.co/auteur/depot-GGUF:Q4_K_M\n"
                    "Un lien huggingface.co ou une commande « ollama pull ... » sont aussi acceptés.",
                    "Examples: gemma4:e4b   gpt-oss:20b   hf.co/author/repo-GGUF:Q4_K_M\n"
                    "A huggingface.co link or an \"ollama pull ...\" command are also accepted.",
                    "Ejemplos: gemma4:e4b   gpt-oss:20b   hf.co/autor/repo-GGUF:Q4_K_M\n"
                    "También se aceptan un enlace huggingface.co o un comando «ollama pull ...».",
                    "Beispiele: gemma4:e4b   gpt-oss:20b   hf.co/autor/repo-GGUF:Q4_K_M\n"
                    "Ein huggingface.co-Link oder ein Befehl „ollama pull ...“ werden auch akzeptiert."),
    "gm_coller": ("Coller", "Paste", "Pegar", "Einfügen"),
    "gm_telecharger": ("Télécharger", "Download", "Descargar", "Herunterladen"),
    "gm_presse_vide": ("Le presse-papier est vide ou ne contient pas de texte.",
                       "The clipboard is empty or contains no text.",
                       "El portapapeles está vacío o no contiene texto.",
                       "Die Zwischenablage ist leer oder enthält keinen Text."),
    "gm_space": ("Ce lien est un « Space » Hugging Face (une application en ligne), pas un modèle : "
                 "il ne peut pas être installé dans Ollama.",
                 "This link is a Hugging Face \"Space\" (an online app), not a model: "
                 "it cannot be installed in Ollama.",
                 "Este enlace es un «Space» de Hugging Face (una aplicación en línea), no un modelo: "
                 "no se puede instalar en Ollama.",
                 "Dieser Link ist ein Hugging-Face-„Space“ (eine Online-App), kein Modell: "
                 "er kann nicht in Ollama installiert werden."),
    "gm_telechargement": ("\nTéléchargement de : {n}", "\nDownloading: {n}", "\nDescarga de: {n}", "\nHerunterladen von: {n}"),
    "gm_telech_echec": ("Le téléchargement a échoué :\n{e}", "The download failed:\n{e}",
                        "La descarga ha fallado:\n{e}", "Der Download ist fehlgeschlagen:\n{e}"),
    "gm_ajoute": ("Modèle ajouté : {n}", "Model added: {n}", "Modelo añadido: {n}", "Modell hinzugefügt: {n}"),
    "gm_btn_exporter": ("Exporter la sélection...", "Export selection...", "Exportar la selección...", "Auswahl exportieren..."),
    "gm_btn_importer": ("Importer...", "Import...", "Importar...", "Importieren..."),
    "gm_btn_dossier": ("Dossier des modèles...", "Models folder...", "Carpeta de modelos...", "Modellordner..."),
    "gm_lbl_dossier": ("Modèles d'Ollama : {d}", "Ollama models: {d}", "Modelos de Ollama: {d}", "Ollama-Modelle: {d}"),
    "gm_dossier_dialog": ("Dossier des modèles d'Ollama (celui qui contient « manifests » et « blobs »)",
                          "Ollama models folder (the one containing \"manifests\" and \"blobs\")",
                          "Carpeta de modelos de Ollama (la que contiene «manifests» y «blobs»)",
                          "Ollama-Modellordner (der „manifests“ und „blobs“ enthält)"),
    "gm_dossier_t": ("Dossier des modèles", "Models folder", "Carpeta de modelos", "Modellordner"),
    "gm_pas_manifests": ("Ce dossier ne contient pas de sous-dossier « manifests » : ce n'est pas le dossier des modèles d'Ollama.",
                         "This folder has no \"manifests\" subfolder: it is not the Ollama models folder.",
                         "Esta carpeta no contiene la subcarpeta «manifests»: no es la carpeta de modelos de Ollama.",
                         "Dieser Ordner hat keinen Unterordner „manifests“: es ist nicht der Ollama-Modellordner."),
    "gm_dossier_choisi": ("Dossier des modèles choisi : {d} ({n} manifeste(s))", "Models folder chosen: {d} ({n} manifest(s))",
                          "Carpeta de modelos elegida: {d} ({n} manifiesto(s))", "Gewählter Modellordner: {d} ({n} Manifest(e))"),
    "gm_menu_copier": ("Copier le nom", "Copy name", "Copiar el nombre", "Namen kopieren"),
    "gm_copie": ("Copié dans le presse-papier : {n}", "Copied to clipboard: {n}",
                 "Copiado al portapapeles: {n}", "In die Zwischenablage kopiert: {n}"),

    # ----- Messages des fonctions d'export / import / téléchargement -----
    "z_trouve": ("  {n} : trouvé dans {d}", "  {n}: found in {d}", "  {n}: encontrado en {d}", "  {n}: gefunden in {d}"),
    "z_manquant": ("fichier manquant : {c}", "missing file: {c}", "archivo que falta: {c}", "fehlende Datei: {c}"),
    "z_place": ("place insuffisante : il faut {a}, il reste {b}", "not enough space: {a} needed, {b} left",
                "espacio insuficiente: se necesitan {a}, quedan {b}", "zu wenig Platz: {a} benötigt, {b} frei"),
    "z_export_de": ("Export de {m} modèle(s), {f} fichiers, {t}...", "Exporting {m} model(s), {f} files, {t}...",
                    "Exportación de {m} modelo(s), {f} archivos, {t}...", "Export von {m} Modell(en), {f} Dateien, {t}..."),
    "z_export_fini": ("Export terminé : {c}", "Export finished: {c}", "Exportación terminada: {c}", "Export abgeschlossen: {c}"),
    "z_inattendu": ("fichier inattendu dans l'export : {n}", "unexpected file in the export: {n}",
                    "archivo inesperado en la exportación: {n}", "unerwartete Datei im Export: {n}"),
    "z_dangereux": ("chemin dangereux dans l'export : {n}", "dangerous path in the export: {n}",
                    "ruta peligrosa en la exportación: {n}", "gefährlicher Pfad im Export: {n}"),
    "z_aucun": ("ce fichier ne contient aucun modèle Ollama", "this file contains no Ollama model",
                "este archivo no contiene ningún modelo de Ollama", "diese Datei enthält kein Ollama-Modell"),
    "z_import": ("Import : {f} fichier(s) à copier, {t}...", "Import: {f} file(s) to copy, {t}...",
                 "Importación: {f} archivo(s) que copiar, {t}...", "Import: {f} Datei(en) zu kopieren, {t}..."),
    "z_verif": ("  Vérification de {n}...", "  Checking {n}...", "  Verificando {n}...", "  Prüfe {n}..."),
    "z_abime": ("fichier abîmé : {n}", "damaged file: {n}", "archivo dañado: {n}", "beschädigte Datei: {n}"),
    "z_import_fini": ("Import terminé : {n}", "Import finished: {n}", "Importación terminada: {n}", "Import abgeschlossen: {n}"),
    "z_introuvable": ("modèle « {n} » introuvable sur le disque.\nDossiers cherchés :\n{d}\n"
                      "Utilisez le bouton « Dossier des modèles... » pour indiquer le bon dossier.",
                      "model \"{n}\" not found on disk.\nFolders searched:\n{d}\n"
                      "Use the \"Models folder...\" button to point to the right folder.",
                      "modelo «{n}» no encontrado en el disco.\nCarpetas buscadas:\n{d}\n"
                      "Use el botón «Carpeta de modelos...» para indicar la carpeta correcta.",
                      "Modell „{n}“ nicht auf der Festplatte gefunden.\nDurchsuchte Ordner:\n{d}\n"
                      "Geben Sie mit „Modellordner...“ den richtigen Ordner an."),
    "z_n_manifestes": ("{n} manifeste(s)", "{n} manifest(s)", "{n} manifiesto(s)", "{n} Manifest(e)"),
    "z_introuvable_ollama": ("modèle « {n} » introuvable dans Ollama", "model \"{n}\" not found in Ollama",
                             "modelo «{n}» no encontrado en Ollama", "Modell „{n}“ nicht in Ollama gefunden"),
    "z_telech_ok": ("Téléchargement terminé : {n}", "Download finished: {n}", "Descarga terminada: {n}", "Download abgeschlossen: {n}"),
    "z_telech_coupe": ("le téléchargement s'est arrêté avant la fin", "the download stopped before the end",
                       "la descarga se detuvo antes del final", "der Download wurde vor dem Ende abgebrochen"),
    "z_lbl_export": ("Export", "Export", "Exportación", "Export"),
    "z_lbl_import": ("Import", "Import", "Importación", "Import"),
    "z_de": ("{p} % de {t}", "{p} % of {t}", "{p} % de {t}", "{p} % von {t}"),
}


def T(cle, **valeurs):
    """Texte traduit dans la langue choisie, avec les {valeurs} remplacées."""
    traductions = TEXTES.get(cle)
    if traductions is None:
        return cle
    index = [code for code, _ in LANGUES].index(LANGUE) if LANGUE in [c for c, _ in LANGUES] else 0
    texte = traductions[index]
    try:
        return texte.format(**valeurs)
    except (KeyError, IndexError, ValueError):
        return texte


CONSIGNE_CODE = " Réponds uniquement avec le code Python dans un seul bloc de code, sans explication."

# ---------------------------------------------------------------
# 3) LES EXERCICES
# ---------------------------------------------------------------
ASM1 = """mystere1:
	xor	edx, edx
	test	edi, edi
	je	.L1
	mov	r8d, 3435973837
.L3:
	mov	eax, edi
	lea	esi, [rdx+rdx*4]
	mov	ecx, edi
	imul	rax, r8
	shr	rax, 35
	lea	edx, [rax+rax*4]
	add	edx, edx
	sub	ecx, edx
	lea	edx, [rcx+rsi*2]
	mov	ecx, edi
	mov	edi, eax
	cmp	ecx, 9
	ja	.L3
.L1:
	mov	eax, edx
	ret"""

ASM2 = """mystere2:
	test	esi, esi
	jle	.L11
	movsx	rsi, esi
	xor	eax, eax
	xor	edx, edx
	lea	rcx, [rdi+rsi*4]
.L10:
	mov	esi, DWORD PTR [rdi]
	add	eax, 1
	test	esi, esi
	jg	.L9
	xor	eax, eax
.L9:
	cmp	edx, eax
	cmovl	edx, eax
	add	rdi, 4
	cmp	rcx, rdi
	jne	.L10
	mov	eax, edx
	ret
.L11:
	xor	edx, edx
	mov	eax, edx
	ret"""

GHIDRA = """uint mystere3(char *param_1)
{
  char cVar1;
  uint uVar2;

  uVar2 = 0x811c9dc5;
  while( true ) {
    cVar1 = *param_1;
    if (cVar1 == '\\0') break;
    uVar2 = (uVar2 ^ (uint)(byte)cVar1) * 0x1000193;
    param_1 = param_1 + 1;
  }
  return uVar2 >> 0x10 ^ uVar2 & 0xffff;
}"""

BYTECODE = """  3           RESUME                   0
  4           BUILD_MAP                0
              STORE_FAST               1 (res)
  5           LOAD_FAST                0 (mots)
              GET_ITER
      L1:     FOR_ITER                71 (to L3)
              STORE_FAST               2 (m)
  6           LOAD_GLOBAL              1 (len + NULL)
              LOAD_FAST                2 (m)
              CALL                     1
              LOAD_CONST               1 (3)
              COMPARE_OP              18 (bool(<))
              POP_JUMP_IF_FALSE        2 (to L2)
  7           JUMP_BACKWARD           20 (to L1)
  8   L2:     LOAD_FAST                2 (m)
              LOAD_CONST               2 (0)
              BINARY_SUBSCR
              LOAD_ATTR                3 (lower + NULL|self)
              CALL                     0
              STORE_FAST               3 (cle)
  9           LOAD_FAST                1 (res)
              LOAD_ATTR                5 (get + NULL|self)
              LOAD_FAST                3 (cle)
              LOAD_CONST               2 (0)
              CALL                     2
              LOAD_GLOBAL              1 (len + NULL)
              LOAD_FAST                2 (m)
              CALL                     1
              BINARY_OP                0 (+)
              LOAD_FAST_LOAD_FAST     19 (res, cle)
              STORE_SUBSCR
              JUMP_BACKWARD           73 (to L1)
  5   L3:     END_FOR
              POP_TOP
 10           LOAD_GLOBAL              7 (sorted + NULL)
              LOAD_FAST                1 (res)
              LOAD_ATTR                9 (items + NULL|self)
              CALL                     0
              LOAD_CONST               3 (<code object <lambda>, line 10>)
              MAKE_FUNCTION
              LOAD_CONST               4 (('key',))
              CALL_KW                  2
              RETURN_VALUE

Disassembly of <code object <lambda>, line 10>:
 10           RESUME                   0
              LOAD_FAST                0 (kv)
              LOAD_CONST               1 (1)
              BINARY_SUBSCR
              UNARY_NEGATIVE
              LOAD_FAST                0 (kv)
              LOAD_CONST               2 (0)
              BINARY_SUBSCR
              BUILD_TUPLE              2
              RETURN_VALUE"""

ASM_TRACE = """trace:
	test	edi, edi
	jle	.L19
	xor	eax, eax
.L18:
	lea	edx, [rax+rsi]
	sub	eax, 1
	test	dil, 1
	cmovne	eax, edx
	add	esi, esi
	sar	edi
	jne	.L18
	xor	eax, 85
	ret
.L19:
	mov	eax, 85
	ret"""

Z80 = """        LD   A,0
        LD   B,7
        LD   C,3
BOUCLE: ADD  A,C
        SLA  C
        DJNZ BOUCLE
        XOR  0FFh"""

ASM8 = """mystere8:
	push	ebp
	mov	ebp, esp
	sub	esp, 16
	jmp	.L2
.L3:
	mov	eax, DWORD PTR [ebp+8]
	cdq
	idiv	DWORD PTR [ebp+12]
	mov	DWORD PTR [ebp-4], edx
	mov	eax, DWORD PTR [ebp+12]
	mov	DWORD PTR [ebp+8], eax
	mov	eax, DWORD PTR [ebp-4]
	mov	DWORD PTR [ebp+12], eax
.L2:
	cmp	DWORD PTR [ebp+12], 0
	jne	.L3
	mov	eax, DWORD PTR [ebp+8]
	mov	edx, eax
	neg	edx
	cmovns	eax, edx
	leave
	ret"""

PREP_HASH = '''def _ref3(s):
    h = 0x811c9dc5
    for c in s.encode():
        h = ((h ^ c) * 0x1000193) & 0xFFFFFFFF
    return (h >> 16) ^ (h & 0xFFFF)
'''

PREP_INTERP = '''P1 = ["MOV A 5", "MOV B 1", "MUL B A", "DEC A", "JNZ A -2"]
P2 = ["MOV A 12", "MOV B 3", "SUB A B", "ADD C 1", "JNZ A -2"]
P3 = ["MOV A 7", "MOV B A", "ADD B B", "ADD B 1"]
'''

EXERCICES = [
    {
        # Exercice très simple : si un modèle rate celui-ci, il ne sait pas répondre au format
        # demandé (code Python dans un bloc) et ses autres résultats ne veulent rien dire.
        "nom": "0 Test de base (Python simple)", "id": 0, "cat": "cat_base",
        "type": "python", "fonction": "somme_pairs",
        "prompt": "Écris une fonction Python `somme_pairs(liste)` qui retourne la somme des nombres "
                  "pairs d'une liste d'entiers (0 si la liste est vide).",
        "tests": [
            "assert somme_pairs([]) == 0",
            "assert somme_pairs([1, 2, 3, 4]) == 6",
            "assert somme_pairs([-2, 5, 7, 10]) == 8",
        ],
    },
    {
        "nom": "1 Décompiler x86 (division optimisée)", "id": 1, "cat": "cat_decomp",
        "type": "python", "fonction": "mystere1",
        "prompt": "Voici une fonction x86-64 (syntaxe Intel, convention System V : 1er argument "
                  "dans edi, entier non signé 32 bits ; résultat dans eax), compilée avec gcc -O2. "
                  "Décompile-la : écris une fonction Python `mystere1(n)` qui fait exactement la même "
                  "chose (n entier positif).\n\n" + ASM1,
        "tests": [
            "assert mystere1(0) == 0",
            "assert mystere1(7) == 7",
            "assert mystere1(1234) == 4321",
            "assert mystere1(1200) == 21",
            "assert mystere1(90817) == 71809",
            "assert mystere1(4000000000) == 4",
        ],
    },
    {
        "nom": "2 Décompiler x86 (tableau)", "id": 2, "cat": "cat_decomp",
        "type": "python", "fonction": "mystere2",
        "prompt": "Voici une fonction x86-64 (syntaxe Intel, System V : rdi = pointeur vers un "
                  "tableau d'int 32 bits signés, esi = nombre d'éléments ; résultat dans eax), "
                  "compilée avec gcc -O2. Décompile-la : écris une fonction Python `mystere2(t)` où t "
                  "est une liste d'entiers.\n\n" + ASM2,
        "tests": [
            "assert mystere2([]) == 0",
            "assert mystere2([-1, 0, -5]) == 0",
            "assert mystere2([1, 2, 3]) == 3",
            "assert mystere2([1, 0, 4, 5, 6, -1, 2]) == 3",
            "assert mystere2([5, -2, 7, 8]) == 2",
            "assert mystere2([0, 1, 0, 1, 1]) == 2",
        ],
    },
    {
        "nom": "3 Pseudo-C Ghidra -> Python", "id": 3, "cat": "cat_lecture",
        "type": "python", "fonction": "mystere3",
        "prompt": "Voici le pseudo-code C produit par le décompilateur Ghidra (uint = entier non "
                  "signé 32 bits, byte = 8 bits). Réécris-le en Python : fonction `mystere3(s)` où s "
                  "est une chaîne ASCII. Attention aux débordements 32 bits et aux priorités des "
                  "opérateurs C.\n\n" + GHIDRA,
        "prep": PREP_HASH,
        "tests": [
            "assert mystere3('') == _ref3('')",
            "assert mystere3('a') == _ref3('a')",
            "assert mystere3('Amstrad') == _ref3('Amstrad')",
            "assert mystere3('CPC 6128') == _ref3('CPC 6128')",
            "assert mystere3('x' * 50) == _ref3('x' * 50)",
        ],
    },
    {
        "nom": "4 Bytecode Python -> source", "id": 4, "cat": "cat_lecture",
        "type": "python", "fonction": "mystere4",
        "prompt": "Voici le désassemblage (module dis, Python 3.13) d'une fonction `mystere4(mots)`. "
                  "Reconstitue son code source Python.\n\n" + BYTECODE,
        "tests": [
            "assert mystere4([]) == []",
            "assert mystere4(['a', 'ab', 'abc']) == [('a', 3)]",
            "assert mystere4(['Chat', 'chien', 'Ane', 'bus', 'ok']) == [('c', 9), ('a', 3), ('b', 3)]",
            "assert mystere4(['Zebre', 'zoo', 'Arbre']) == [('z', 8), ('a', 5)]",
        ],
    },
    {
        "nom": "5 Exécuter du x86 de tête", "id": 5, "cat": "cat_tete",
        "type": "valeurs", "attendu": [115, 72],
        "prompt": "Voici une fonction x86-64 (syntaxe Intel, System V : edi = 1er argument, "
                  "esi = 2e argument, entiers signés 32 bits ; résultat dans eax).\n\n" + ASM_TRACE +
                  "\n\nQue retournent trace(13, 3) et trace(6, 5) ? Termine ta réponse par une ligne "
                  "exactement de la forme :\nRESULTAT: <valeur1> <valeur2>",
    },
    {
        "nom": "6 Exécuter du Z80 de tête", "id": 6, "cat": "cat_tete",
        "type": "valeurs", "attendu": [130, 128],
        "prompt": "Voici une routine en assembleur Z80 (Amstrad CPC, registres 8 bits). DJNZ "
                  "décrémente B et saute tant que B n'est pas nul.\n\n" + Z80 +
                  "\n\nQuelles sont les valeurs décimales des registres A et C à la fin ? Termine ta "
                  "réponse par une ligne exactement de la forme :\nRESULTAT: <A> <C>",
    },
    {
        "nom": "7 Écrire un mini-interpréteur", "id": 7, "cat": "cat_prog",
        "type": "python", "fonction": "executer",
        "prompt": "Écris une fonction Python `executer(programme)` qui exécute un petit assembleur "
                  "et retourne le dictionnaire des registres. `programme` est une liste de chaînes. "
                  "Registres : A, B, C, D, tous à 0 au départ. Instructions (X = registre, "
                  "Y = registre ou entier) :\n"
                  "MOV X Y (X = Y), ADD X Y (X += Y), SUB X Y (X -= Y), MUL X Y (X *= Y), "
                  "DEC X (X -= 1), JNZ X n (si X != 0, saute de n lignes, relatif à la ligne "
                  "courante, n peut être négatif), JMP n (saut relatif inconditionnel). "
                  "Le programme s'arrête quand on sort de la liste. Retourne {'A':..,'B':..,'C':..,'D':..}.",
        "prep": PREP_INTERP,
        "tests": [
            "assert executer([]) == {'A': 0, 'B': 0, 'C': 0, 'D': 0}",
            "assert executer(P1)['B'] == 120",
            "assert executer(P1)['A'] == 0",
            "r = executer(P2)\nassert r['A'] == 0 and r['C'] == 4",
            "assert executer(P3) == {'A': 7, 'B': 15, 'C': 0, 'D': 0}",
            "assert executer(['MOV D -3', 'ADD D 10', 'JMP 5', 'MOV D 0'])['D'] == 7",
        ],
    },
    {
        "nom": "8 Comprendre du x86 32 bits (pile)", "id": 8, "cat": "cat_decomp",
        "type": "python", "fonction": "mystere8",
        "prompt": "Voici une fonction x86 32 bits (syntaxe Intel, convention cdecl : les deux "
                  "arguments int signés sont sur la pile, [ebp+8] puis [ebp+12] ; résultat dans eax), "
                  "compilée sans optimisation comme un vieux programme PC. Explique-toi ce que fait "
                  "chaque instruction (cdq, idiv, neg, cmovns), puis écris une fonction Python "
                  "`mystere8(a, b)` qui fait exactement la même chose. Attention : en C la division "
                  "entière tronque vers zéro, pas comme // en Python.\n\n" + ASM8,
        "tests": [
            "assert mystere8(84, 36) == 12",
            "assert mystere8(17, 5) == 1",
            "assert mystere8(-48, 18) == 6",
            "assert mystere8(7, 0) == 7",
            "assert mystere8(0, 9) == 9",
            "assert mystere8(-9, -6) == 3",
        ],
    },
]

# Les capacités : chaque exercice appartient à une capacité (clé "cat")
CATEGORIES = ["cat_base", "cat_decomp", "cat_lecture", "cat_tete", "cat_prog"]
EX_PAR_NOM = {e["nom"]: e for e in EXERCICES}     # le nom français sert de clé dans le CSV


def points_max(ex):
    return len(ex["tests"]) if ex["type"] == "python" else len(ex["attendu"])


def nom_ex(ex):
    """Nom de l'exercice dans la langue choisie."""
    return T("ex%d" % ex["id"])


RUNNER = '''
_ok = 0
for _t in _TESTS:
    try:
        exec(_t, globals())
        _ok += 1
    except BaseException:
        pass
# Le score est écrit dans un fichier (fonctionne aussi depuis le .exe sans console)
with open("score.txt", "w") as _f:
    _f.write(str(_ok))
'''


# ---------------------------------------------------------------
# 4) OUTILS
# ---------------------------------------------------------------
def appel(chemin, donnees=None, delai=2400):
    requete = urllib.request.Request(
        URL + chemin,
        data=json.dumps(donnees).encode("utf-8") if donnees else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(requete, timeout=delai) as r:
        return json.loads(r.read().decode("utf-8"))


def pourcentage_gpu(modele):
    try:
        for m in appel("/api/ps", delai=10).get("models", []):
            if m["name"].lower() in (modele.lower(), modele.lower() + ":latest"):
                if m["size"] > 0:
                    return round(100 * m["size_vram"] / m["size"])
    except Exception:
        pass
    return -1


def decharger(modele):
    try:
        appel("/api/generate", {"model": modele, "keep_alive": 0}, delai=60)
    except Exception:
        pass


def nettoyer(texte):
    return re.sub(r"<think>.*?</think>", "", texte, flags=re.S).strip()


def extraire_code(texte, mot_cle=""):
    blocs = re.findall(r"```[a-zA-Z0-9]*\n(.*?)```", texte, flags=re.S)
    for b in blocs:
        if mot_cle and mot_cle in b:
            return b
    if blocs:
        return blocs[0]
    return texte


def tester_python(code, ex):
    complet = (code + "\n\n" + ex.get("prep", "") + "\n_TESTS = " + repr(ex["tests"]) + "\n" + RUNNER)
    with tempfile.TemporaryDirectory() as dossier:
        fichier = os.path.join(dossier, "essai.py")
        with open(fichier, "w", encoding="utf-8") as f:
            f.write(complet)
        if getattr(sys, "frozen", False):
            # Version .exe : le programme se relance lui-même en mode "exécuteur"
            commande = [sys.executable, "--executer", fichier]
        else:
            commande = [sys.executable, "-I", fichier]
        options = {}
        if os.name == "nt":
            options["creationflags"] = 0x08000000   # pas de fenêtre noire qui clignote
        try:
            subprocess.run(commande, cwd=dossier, capture_output=True, timeout=20,
                           stdin=subprocess.DEVNULL, **options)
            with open(os.path.join(dossier, "score.txt")) as f:
                return int(f.read().strip() or 0)
        except Exception:
            return 0


def tester_valeurs(texte, attendu):
    """Cherche la dernière ligne 'RESULTAT: x y' et compte les valeurs justes."""
    lignes = re.findall(r"RESULTAT\s*:?\s*\**\s*(-?\d+)\D+?(-?\d+)", texte, flags=re.I)
    if not lignes:
        return 0
    valeurs = [int(v) for v in lignes[-1]]
    return sum(1 for v, a in zip(valeurs, attendu) if v == a)


def generer(modele, prompt, reflexion=False):
    demande = {
        "model": modele, "prompt": prompt, "stream": False, "think": bool(reflexion),
        "options": {
            "num_ctx": contexte_utilise(reflexion),     # réglable dans « Réglages »
            "temperature": 0.2,
            "num_predict": MAX_TOKENS_REFLEXION if reflexion else MAX_TOKENS,
        },
    }
    try:
        return appel("/api/generate", demande)
    except urllib.error.HTTPError:
        del demande["think"]          # certains modèles refusent ce paramètre
        return appel("/api/generate", demande)


def modeles_installes():
    """Liste des modèles Ollama installés (liste vide si Ollama ne répond pas)."""
    try:
        return sorted(m["name"] for m in appel("/api/tags", delai=10).get("models", []))
    except Exception:
        return []


def version_ollama():
    """Version d'Ollama (ex. « 0.40.17 »), ou None s'il ne répond pas."""
    try:
        return appel("/api/version", delai=3).get("version", "?")
    except Exception:
        return None


def liste_modeles():
    """Liste détaillée des modèles installés (un dictionnaire par modèle).
    Retourne None si Ollama ne répond pas (et [] s'il n'y a aucun modèle)."""
    try:
        donnees = appel("/api/tags", delai=10)
    except Exception:
        return None
    resultat = []
    for m in donnees.get("models", []):
        d = m.get("details") or {}
        resultat.append({
            "nom": m.get("name", "?"),
            "taille": m.get("size", 0) or 0,                       # en octets
            "date": str(m.get("modified_at", ""))[:10],
            "famille": d.get("family", "") or "",
            "params": d.get("parameter_size", "") or "",           # ex. « 9.2B »
            "quantif": d.get("quantization_level", "") or "",     # ex. « Q4_K_M »
            "format": d.get("format", "") or "",
            "contexte": d.get("context_length", 0) or 0,           # absent sur les vieux Ollama
            "capacites": m.get("capabilities"),                    # None = inconnu (vieux Ollama)
            "digest": m.get("digest", "") or "",
            "parent": d.get("parent_model", "") or "",
        })
    return sorted(resultat, key=lambda x: x["nom"].lower())


def modeles_en_memoire():
    """Modèles chargés en mémoire (/api/ps) : {nom en minuscules: {"gpu": %, "taille": octets}}."""
    resultat = {}
    try:
        for m in appel("/api/ps", delai=5).get("models", []):
            taille = m.get("size", 0) or 0
            vram = m.get("size_vram", 0) or 0
            resultat[m.get("name", "").lower()] = {"gpu": round(100 * vram / taille) if taille else 0,
                                                   "taille": taille}
    except Exception:
        pass
    return resultat


def details_modele(nom):
    """Infos complètes d'un modèle (/api/show) : capacités, contexte maximal, Modelfile.
    Retourne {} si Ollama ne répond pas."""
    try:
        info = appel("/api/show", {"model": nom}, delai=30)
    except Exception:
        return {}
    contexte = 0
    for cle, valeur in (info.get("model_info") or {}).items():
        if cle.endswith(".context_length") and isinstance(valeur, int):
            contexte = valeur
    return {"capacites": info.get("capabilities") or [], "contexte": contexte,
            "modelfile": info.get("modelfile", "")}


def copier_modele(source, destination):
    """Copie un modèle sous un autre nom (équivalent de « ollama cp »). Les gros fichiers sont partagés :
    la copie ne prend presque pas de place sur le disque."""
    requete = urllib.request.Request(URL + "/api/copy",
                                     data=json.dumps({"source": source, "destination": destination}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(requete, timeout=60):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError(T("z_introuvable_ollama", n=source))
        raise


def espace_libre(dossier):
    """Place libre (en octets) sur le disque du dossier, ou None si on ne peut pas la lire."""
    import shutil
    try:
        return shutil.disk_usage(dossier).free
    except Exception:
        return None


# ---------------------------------------------------------------
# 5) LE TEST (lancé depuis la fenêtre)
# ---------------------------------------------------------------
def lancer_tests(modeles, reflexion, ecrire, arret, progres=None):
    """ecrire(texte) affiche dans la fenêtre ; arret() retourne True si on doit s'arrêter ;
    progres(fait, total) (facultatif) reçoit le nombre d'exercices faits, pour la barre d'avancement."""
    total_ex, fait_ex = len(modeles) * len(EXERCICES), 0

    def avancer():
        nonlocal fait_ex
        fait_ex += 1
        if progres:
            progres(fait_ex, total_ex)

    installes = [m.lower() for m in modeles_installes()]
    if not installes:
        ecrire(T("ollama_absent"))
        return

    suffixe = "_reflexion" if reflexion else ""
    f_csv = os.path.join(DOSSIER, f"resultats_hardcode{suffixe}.csv")
    f_rep = os.path.join(DOSSIER, f"reponses_hardcode{suffixe}.md")
    f_res = os.path.join(DOSSIER, f"resume_hardcode{suffixe}.md")

    lignes, reponses = [], []
    ecrire(T("mode_reflexion", etat=T("active") if reflexion else T("desactive")))
    ecrire(T("ctx_info", c=contexte_utilise(reflexion)))

    for modele in modeles:
        if arret():
            break
        if modele.lower() not in installes and modele.lower() + ":latest" not in installes:
            ecrire(T("ignore", m=modele))
            for _ in EXERCICES:          # la barre d'avancement saute ce modèle
                avancer()
            continue
        ecrire(f"\n=== {modele} ===")
        for ex in EXERCICES:
            if arret():
                ecrire(T("arret_demande"))
                break
            debut = time.time()
            prompt = ex["prompt"] + (CONSIGNE_CODE if ex["type"] == "python" else "")
            try:
                res = generer(modele, prompt, reflexion)
            except Exception as e:
                ecrire(T("erreur_ex", ex=nom_ex(ex), e=e))
                lignes.append([modele, ex["nom"], "ERREUR", points_max(ex), "", "", "", ""])
                avancer()
                continue

            texte = nettoyer(res.get("response", "") or "")
            sur = points_max(ex)
            try:
                if ex["type"] == "python":
                    code = extraire_code(texte, "def " + ex["fonction"])
                    points = tester_python(code, ex)
                else:
                    points = tester_valeurs(texte, ex["attendu"])
            except Exception:
                points = 0

            tokens = res.get("eval_count", 0) or 0
            duree_gen = (res.get("eval_duration", 0) or 0) / 1e9
            vitesse = round(tokens / duree_gen, 1) if duree_gen else 0
            duree = round(time.time() - debut, 1)
            gpu = pourcentage_gpu(modele)
            ecrire(f"  {points}/{sur} | {vitesse:>5} tok/s | {duree:>6}s | {nom_ex(ex)}")
            if ex["id"] == 0 and points == 0:
                ecrire(T("echec_base", m=modele))

            # Le CSV garde le nom français de l'exercice : c'est la clé qui permet de le relire
            lignes.append([modele, ex["nom"], points, sur, vitesse, tokens, duree, gpu])
            reflexion_txt = (res.get("thinking") or "").strip()
            bloc = f"## {modele} - {nom_ex(ex)}  ({points}/{sur})\n\n"
            if reflexion_txt:
                bloc += (f"<details><summary>{T('reflexion_md')}</summary>\n\n"
                         f"{reflexion_txt}\n\n</details>\n\n")
            reponses.append(bloc + f"{texte}\n\n---\n")
            avancer()
        decharger(modele)

        try:   # sauvegarde après chaque modèle
            with open(f_csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["modele", "exercice", "points", "sur", "tokens_par_s",
                            "tokens", "duree_s", "pourcent_GPU"])
                w.writerows(lignes)
            with open(f_rep, "w", encoding="utf-8") as f:
                f.write("\n".join(reponses))
        except Exception as e:
            ecrire(T("ecriture_impossible", e=e))

    # ----- Score global et classement par capacité -----
    global DERNIERS_RESULTATS
    DERNIERS_RESULTATS = {"lignes": lignes, "reflexion": reflexion,
                          "date": time.strftime("%d/%m/%Y %H:%M"),
                          "contexte": contexte_utilise(reflexion)}
    scores = calculer_scores(lignes)
    if not scores:
        ecrire(T("aucun_resultat"))
        return
    try:
        with open(f_res, "w", encoding="utf-8") as f:
            f.write(resume_markdown(scores, DERNIERS_RESULTATS))
    except Exception as e:
        ecrire(T("resume_impossible", e=e))
    ecrire("\n" + T("titre_global") + "\n" + tableau_markdown(scores))
    ecrire("\n" + T("titre_capacites") + "\n" + tableau_capacites(scores))
    ecrire("\n" + meilleurs_texte(scores))
    ecrire(T("fichiers_crees", d=DOSSIER) + f"\n  {os.path.basename(f_res)}, "
           f"{os.path.basename(f_csv)}, {os.path.basename(f_rep)}")


# ---------------------------------------------------------------
# 6) SCORES, RÉSUMÉ ET RAPPORT PDF
# ---------------------------------------------------------------
DERNIERS_RESULTATS = None   # rempli à la fin d'un test, utilisé par l'export PDF


def calculer_scores(lignes):
    """Transforme les lignes [modele, exercice, points, sur, vitesse, tokens, duree, gpu]
    en une liste de scores par modèle, du meilleur au moins bon.
    Les exercices comptés sont ceux présents dans les résultats : un ancien fichier sans
    l'exercice 0 reste donc noté sur ses 37 points."""
    presents = {EX_PAR_NOM[l[1]]["id"] for l in lignes if l[1] in EX_PAR_NOM}
    exercices = [e for e in EXERCICES if e["id"] in presents]
    total_max = sum(points_max(e) for e in exercices)
    resume = {}
    for l in lignes:
        ex = EX_PAR_NOM.get(l[1])
        if ex is None:
            continue           # exercice inconnu (fichier d'une autre version) : ignoré
        try:
            points = int(l[2])
        except (ValueError, TypeError):
            points = 0         # exercice en ERREUR : 0 point
        r = resume.setdefault(l[0], {"modele": l[0], "points": 0, "parfaits": 0, "par_ex": {},
                                     "tokens": 0, "temps_gen": 0.0, "duree": 0.0, "gpu": "", "erreurs": 0})
        r["points"] += points
        r["parfaits"] += int(points == points_max(ex))
        r["par_ex"][ex["id"]] = points
        if str(l[2]) == "ERREUR":
            r["erreurs"] += 1
        try:
            r["duree"] += float(l[6])
            vitesse, tokens = float(l[4]), int(float(l[5]))
            if vitesse > 0 and tokens > 0:
                r["tokens"] += tokens
                r["temps_gen"] += tokens / vitesse     # temps passé à écrire la réponse
        except (ValueError, TypeError):
            pass
        if str(l[7]).strip() not in ("", "-1"):
            r["gpu"] = l[7]
    scores = []
    for r in resume.values():
        r["sur"] = total_max
        r["exercices"] = exercices
        r["pourcent"] = round(100 * r["points"] / total_max, 1) if total_max else 0
        # Vitesse = total des tokens / total du temps d'écriture (une réponse d'un seul token
        # ne fausse plus la moyenne)
        r["vitesse"] = round(r["tokens"] / r["temps_gen"], 1) if r["temps_gen"] else 0
        r["par_minute"] = round(r["points"] / (r["duree"] / 60), 1) if r["duree"] else 0
        r["detail"] = [f"{r['par_ex'][e['id']]}/{points_max(e)}" if e["id"] in r["par_ex"] else "-"
                       for e in exercices]
        # Score par capacité : points obtenus / points possibles dans la capacité
        r["capacites"] = {}
        for cat in CATEGORIES:
            ex_cat = [e for e in exercices if e["cat"] == cat]
            if ex_cat:
                pts = sum(r["par_ex"].get(e["id"], 0) for e in ex_cat)
                sur = sum(points_max(e) for e in ex_cat)
                r["capacites"][cat] = {"points": pts, "sur": sur, "pourcent": round(100 * pts / sur)}
        r["echec_base"] = 0 in r["par_ex"] and r["par_ex"][0] == 0
        scores.append(r)
    scores.sort(key=lambda r: (-r["points"], r["duree"]))
    for i, r in enumerate(scores, 1):
        r["rang"] = i
    return scores


def categories_presentes(scores):
    return [c for c in CATEGORIES if scores and c in scores[0]["capacites"]]


def classement_capacite(scores, cat):
    """Modèles triés du meilleur au moins bon pour une capacité."""
    return sorted(scores, key=lambda r: (-r["capacites"][cat]["pourcent"], r["rang"]))


def duree_lisible(secondes):
    secondes = int(round(secondes))
    if secondes < 60:
        return f"{secondes} s"
    if secondes < 3600:
        return f"{secondes // 60} min {secondes % 60:02d}"
    return f"{secondes // 3600} h {secondes % 3600 // 60:02d}"


def tableau_markdown(scores):
    ex = scores[0]["exercices"]
    sortie = [f"| {T('col_rang')} | {T('col_modele')} | {T('col_score')} | {T('col_points')} /{scores[0]['sur']} "
              f"| {T('col_parfaits')} /{len(ex)} | {T('col_detail', a=ex[0]['id'], b=ex[-1]['id'])} "
              f"| {T('col_vitesse')} | {T('col_temps')} | {T('col_ppm')} | {T('col_gpu')} |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in scores:
        sortie.append(f"| {r['rang']} | {r['modele']} | **{r['pourcent']} %** | {r['points']} "
                      f"| {r['parfaits']} | {' '.join(r['detail'])} | {r['vitesse']} "
                      f"| {duree_lisible(r['duree'])} | {r['par_minute']} | {r['gpu']} |")
    return "\n".join(sortie)


def tableau_capacites(scores):
    cats = categories_presentes(scores)
    sortie = ["| " + T("col_modele") + " | " + " | ".join(T(c) for c in cats) + f" | {T('col_global')} |",
              "|---" * (len(cats) + 2) + "|"]
    for r in scores:
        cellules = [f"{r['capacites'][c]['pourcent']} % ({r['capacites'][c]['points']}/{r['capacites'][c]['sur']})"
                    for c in cats]
        sortie.append(f"| {r['modele']} | " + " | ".join(cellules) + f" | **{r['pourcent']} %** |")
    return "\n".join(sortie)


def meilleurs_texte(scores):
    lignes = [T("md_meilleurs") + " :"]
    for c in categories_presentes(scores):
        premier = classement_capacite(scores, c)[0]
        p = premier["capacites"][c]["pourcent"]
        lignes.append(f"- {T(c)} : " + (f"{premier['modele']} ({p} %)" if p > 0 else T("aucun")))
    return "\n".join(lignes)


def resume_markdown(scores, donnees):
    etat = T("active") if donnees.get("reflexion") else T("desactive")
    return (f"# {T('resume_titre', date=donnees.get('date', '?'), etat=etat, c=donnees.get('contexte', '?'))}\n\n"
            f"## {T('md_global')}\n\n{tableau_markdown(scores)}\n\n"
            f"## {T('md_capacites')}\n\n{tableau_capacites(scores)}\n\n{meilleurs_texte(scores)}\n")


def charger_dernier_csv():
    """Si aucun test n'a été fait depuis l'ouverture, relit le CSV le plus récent du dossier."""
    candidats = [os.path.join(DOSSIER, f) for f in os.listdir(DOSSIER)
                 if f.startswith("resultats_hardcode") and f.endswith(".csv")]
    if not candidats:
        return None
    fichier = max(candidats, key=os.path.getmtime)
    with open(fichier, encoding="utf-8-sig") as f:
        lignes = [l for l in csv.reader(f, delimiter=";")][1:]
    lignes = [l for l in lignes if len(l) >= 8]
    if not lignes:
        return None
    return {"lignes": lignes, "reflexion": "_reflexion" in fichier,
            "date": time.strftime("%d/%m/%Y %H:%M", time.localtime(os.path.getmtime(fichier))),
            "contexte": "?", "source": os.path.basename(fichier)}


# ----- Petit moteur PDF fait maison (aucune bibliothèque à installer) -----
# Largeur de chaque caractère (codes 32 à 126) pour 1000 points de taille, polices standard du PDF.
LARGEURS_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556,
                 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722,
                 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722,
                 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556,
                 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500,
                 500, 334, 260, 334, 584]
LARGEURS_HELV_GRAS = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556,
                      556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722,
                      722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722,
                      667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556,
                      611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333,
                      611, 556, 778, 556, 556, 500, 389, 280, 389, 584]

# Couleurs (rouge, vert, bleu entre 0 et 1)
BLEU_FONCE = (0.11, 0.24, 0.42)
BLEU = (0.20, 0.45, 0.75)
GRIS_TEXTE = (0.38, 0.40, 0.44)
GRIS_CLAIR = (0.95, 0.96, 0.97)
GRIS_TRAIT = (0.82, 0.84, 0.87)
NOIR = (0.12, 0.13, 0.15)
BLANC = (1, 1, 1)


def couleurs_pourcent(p):
    """(fond, texte) selon le pourcentage : vert, orange ou rouge."""
    if p >= 67:
        return (0.84, 0.94, 0.85), (0.08, 0.42, 0.18)
    if p >= 34:
        return (1.00, 0.93, 0.78), (0.62, 0.38, 0.00)
    return (0.99, 0.86, 0.86), (0.66, 0.13, 0.13)


def _pdf_texte(t):
    """Prépare un texte pour le PDF (accents en WinAnsi, caractères spéciaux échappés)."""
    b = str(t).encode("cp1252", errors="replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class PDF:
    """Page A4. Les coordonnées partent du HAUT de la page (plus simple pour empiler)."""
    L, H = 595, 842

    def __init__(self):
        self.pages = []
        self.flux = None

    def nouvelle_page(self):
        self.flux = []
        self.pages.append(self.flux)

    @staticmethod
    def largeur(texte, taille, gras=False, mono=False):
        if mono:
            return len(str(texte)) * 0.6 * taille
        table = LARGEURS_HELV_GRAS if gras else LARGEURS_HELV
        total = 0
        for c in str(texte):
            if c == "…":
                total += 1000
                continue
            base = unicodedata.normalize("NFD", c)[0]      # é -> e (même largeur)
            code = ord(base)
            total += table[code - 32] if 32 <= code <= 126 else 556
        return total * taille / 1000

    def raccourcir(self, texte, larg_max, taille, gras=False):
        """Coupe le milieu d'un texte trop long : 'ttempvnn/Hauh…K-M:latest'."""
        texte = str(texte)
        if self.largeur(texte, taille, gras) <= larg_max:
            return texte
        debut, fin = len(texte) // 2, len(texte) // 2
        while debut > 1:
            essai = texte[:debut] + "…" + texte[-fin:]
            if self.largeur(essai, taille, gras) <= larg_max:
                return essai
            debut -= 1
            fin = max(1, fin - 1)
        return texte[:1] + "…"

    def couper_lignes(self, texte, larg_max, taille, gras=False):
        """Découpe un paragraphe en lignes qui tiennent dans larg_max."""
        lignes, courante = [], ""
        for mot in str(texte).split():
            essai = (courante + " " + mot).strip()
            if self.largeur(essai, taille, gras) <= larg_max or not courante:
                courante = essai
            else:
                lignes.append(courante)
                courante = mot
        if courante:
            lignes.append(courante)
        return lignes

    @staticmethod
    def _c(couleur):
        return "%.3f %.3f %.3f" % couleur

    def rect(self, x, y, l, h, fond=None, bord=None, epaisseur=0.6):
        haut = self.H - y - h
        if fond:
            self.flux.append(f"{self._c(fond)} rg {x:.1f} {haut:.1f} {l:.1f} {h:.1f} re f")
        if bord:
            self.flux.append(f"{epaisseur} w {self._c(bord)} RG {x:.1f} {haut:.1f} {l:.1f} {h:.1f} re S")

    def ligne(self, x1, y1, x2, y2, couleur=GRIS_TRAIT, epaisseur=0.6):
        self.flux.append(f"{epaisseur} w {self._c(couleur)} RG {x1:.1f} {self.H - y1:.1f} m "
                         f"{x2:.1f} {self.H - y2:.1f} l S")

    def cercle(self, cx, cy, r, fond):
        k, y = 0.5523 * r, self.H - cy
        self.flux.append(
            f"{self._c(fond)} rg {cx + r:.1f} {y:.1f} m "
            f"{cx + r:.1f} {y + k:.1f} {cx + k:.1f} {y + r:.1f} {cx:.1f} {y + r:.1f} c "
            f"{cx - k:.1f} {y + r:.1f} {cx - r:.1f} {y + k:.1f} {cx - r:.1f} {y:.1f} c "
            f"{cx - r:.1f} {y - k:.1f} {cx - k:.1f} {y - r:.1f} {cx:.1f} {y - r:.1f} c "
            f"{cx + k:.1f} {y - r:.1f} {cx + r:.1f} {y - k:.1f} {cx + r:.1f} {y:.1f} c f")

    def texte(self, x, y, contenu, taille=10, gras=False, mono=False, couleur=NOIR, align="g"):
        """y = ligne de base du texte. align : g (gauche), c (centré), d (droite)."""
        police = "F3" if mono else ("F2" if gras else "F1")
        l = self.largeur(contenu, taille, gras, mono)
        if align == "c":
            x -= l / 2
        elif align == "d":
            x -= l
        self.flux.append(f"BT /{police} {taille} Tf {self._c(couleur)} rg {x:.1f} {self.H - y:.1f} Td ("
                         + _pdf_texte(contenu).decode("latin-1") + ") Tj ET")

    def enregistrer(self, chemin, pied_gauche):
        objets = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]      # 1 : catalogue, 2 : pages
        for p in (b"Helvetica", b"Helvetica-Bold", b"Courier"):    # 3, 4, 5 : polices
            objets.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /" + p + b" /Encoding /WinAnsiEncoding >>")
        ressources = b"<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >>"
        kids, n = [], len(self.pages)
        for i, flux in enumerate(self.pages, 1):
            self.flux = flux                      # pied de page : trait, signature, numéro
            self.ligne(40, self.H - 34, self.L - 40, self.H - 34)
            self.texte(40, self.H - 22, pied_gauche, 7.5, couleur=GRIS_TEXTE)
            self.texte(self.L - 40, self.H - 22, T("pdf_page", i=i, n=n), 7.5, couleur=GRIS_TEXTE, align="d")
            contenu = "\n".join(flux).encode("latin-1")
            objets.append(b"<< /Length " + str(len(contenu)).encode() + b" >>\nstream\n" + contenu + b"\nendstream")
            num_flux = len(objets)
            objets.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 " + f"{self.L} {self.H}".encode()
                          + b"] /Resources " + ressources + b" /Contents " + str(num_flux).encode() + b" 0 R >>")
            kids.append(str(len(objets)).encode() + b" 0 R")
        objets[1] = b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count " + str(n).encode() + b" >>"
        sortie = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        positions = []
        for i, o in enumerate(objets, 1):
            positions.append(len(sortie))
            sortie += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
        debut_xref = len(sortie)
        sortie += f"xref\n0 {len(objets) + 1}\n0000000000 65535 f \n".encode()
        for p in positions:
            sortie += f"{p:010d} 00000 n \n".encode()
        sortie += (f"trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\nstartxref\n{debut_xref}\n%%EOF\n").encode()
        with open(chemin, "wb") as f:
            f.write(sortie)


def exporter_pdf(donnees):
    """Crée le rapport PDF dans le dossier du programme et retourne son chemin."""
    scores = calculer_scores(donnees["lignes"])
    if not scores:
        raise ValueError(T("pdf_vide"))
    reflexion = donnees.get("reflexion")
    exercices = scores[0]["exercices"]
    cats = categories_presentes(scores)
    pdf = PDF()
    M = 40                              # marge gauche et droite
    LU = pdf.L - 2 * M                  # largeur utile
    BAS = pdf.H - 50                    # on ne descend pas plus bas (pied de page)
    etat = {"y": 0}

    def page_suite():
        pdf.nouvelle_page()
        pdf.rect(0, 0, pdf.L, 6, fond=BLEU_FONCE)          # fin bandeau en haut des pages suivantes
        etat["y"] = 40

    def besoin(h):
        if etat["y"] + h > BAS:
            page_suite()

    def section(titre, hauteur_suivante=60):
        besoin(34 + hauteur_suivante)
        etat["y"] += 22
        pdf.texte(M, etat["y"], titre, 13, gras=True, couleur=BLEU_FONCE)
        pdf.ligne(M, etat["y"] + 5, M + LU, etat["y"] + 5, BLEU, 1.2)
        etat["y"] += 16

    # ----- Page 1 : bandeau de titre -----
    pdf.nouvelle_page()
    pdf.rect(0, 0, pdf.L, 92, fond=BLEU_FONCE)
    pdf.rect(0, 92, pdf.L, 4, fond=BLEU)
    pdf.texte(M, 44, T("pdf_titre"), 22, gras=True, couleur=BLANC)
    pdf.texte(M, 68, T("pdf_sous_titre"), 11, couleur=(0.80, 0.86, 0.95))
    pdf.texte(pdf.L - M, 44, f"v{VERSION}", 11, gras=True, couleur=BLANC, align="d")
    pdf.texte(pdf.L - M, 68, SIGNATURE, 9, couleur=(0.80, 0.86, 0.95), align="d")

    # ----- Cartes d'information -----
    infos = [(T("pdf_date"), donnees.get("date", "?")),
             (T("pdf_mode"), T("active") if reflexion else T("desactive")),
             (T("pdf_ctx"), f"{donnees['contexte']} tokens" if str(donnees.get("contexte", "?")) != "?" else "?"),
             (T("pdf_nb_modeles"), str(len(scores)))]
    y, larg = 112, (LU - 3 * 10) / 4
    for i, (titre, valeur) in enumerate(infos):
        x = M + i * (larg + 10)
        pdf.rect(x, y, larg, 44, fond=GRIS_CLAIR)
        pdf.rect(x, y, 3, 44, fond=BLEU)
        pdf.texte(x + 12, y + 16, titre.upper(), 7, gras=True, couleur=GRIS_TEXTE)
        pdf.texte(x + 12, y + 34, pdf.raccourcir(valeur, larg - 18, 12, True), 12, gras=True, couleur=NOIR)
    pdf.texte(M, y + 62, T("pdf_machine", n=len(exercices), p=scores[0]["sur"]), 8.5, couleur=GRIS_TEXTE)
    if donnees.get("source"):
        pdf.texte(M + LU, y + 62, T("pdf_source", f=donnees["source"]), 8.5, couleur=GRIS_TEXTE, align="d")
    etat["y"] = y + 70

    # ----- Classement global -----
    section(T("pdf_classement"))
    medailles = {1: (0.85, 0.65, 0.13), 2: (0.60, 0.63, 0.67), 3: (0.72, 0.45, 0.20)}
    for r in scores:
        besoin(44)
        y = etat["y"]
        if r["rang"] % 2 == 1:
            pdf.rect(M, y, LU, 40, fond=GRIS_CLAIR)
        pdf.cercle(M + 18, y + 20, 11, medailles.get(r["rang"], (0.45, 0.50, 0.58)))
        pdf.texte(M + 18, y + 24, str(r["rang"]), 11, gras=True, couleur=BLANC, align="c")
        pdf.texte(M + 38, y + 17, pdf.raccourcir(r["modele"], 250, 10.5, True), 10.5, gras=True)
        sous = T("pdf_ligne_modele", p=r["points"], s=r["sur"], f=r["parfaits"], n=len(exercices),
                 v=r["vitesse"], t=duree_lisible(r["duree"]))
        pdf.texte(M + 38, y + 31, pdf.raccourcir(sous, 260, 7.5), 7.5, couleur=GRIS_TEXTE)
        if r["echec_base"]:
            pdf.texte(M + 38 + 255, y + 17, "(!) " + T("pdf_echec_base"), 7, gras=True,
                      couleur=(0.66, 0.13, 0.13), align="d")
        # barre de score
        xb, lb = M + 300, 135
        fond, texte = couleurs_pourcent(r["pourcent"])
        pdf.rect(xb, y + 14, lb, 12, fond=(0.88, 0.89, 0.91))
        if r["pourcent"] > 0:
            pdf.rect(xb, y + 14, lb * r["pourcent"] / 100, 12, fond=texte)
        pdf.texte(M + LU - 6, y + 25, f"{r['pourcent']} %", 13, gras=True, couleur=texte, align="d")
        etat["y"] += 42

    # ----- Classement par capacité (tableau coloré) -----
    # on garde le tableau, la légende et les meilleurs modèles sur la même page
    section(T("pdf_capacites"), 22 * (len(scores) + 1) + 14 * len(cats) + 60)
    col_nom = 165
    col = (LU - col_nom) / (len(cats) + 1)

    def entete_tableau(titres):
        y = etat["y"]
        pdf.rect(M, y, LU, 22, fond=BLEU_FONCE)
        pdf.texte(M + 8, y + 14.5, T("col_modele"), 8.5, gras=True, couleur=BLANC)
        for i, t in enumerate(titres):
            pdf.texte(M + col_nom + col * (i + 0.5), y + 14.5, t, 8.5, gras=True, couleur=BLANC, align="c")
        etat["y"] += 22

    entete_tableau([T("catc_" + c[4:]) for c in cats] + [T("col_global")])
    meilleurs = {c: max(r["capacites"][c]["pourcent"] for r in scores) for c in cats}
    for r in scores:
        besoin(22)
        y = etat["y"]
        pdf.texte(M + 8, y + 14, pdf.raccourcir(f"{r['rang']}. {r['modele']}", col_nom - 12, 8.5), 8.5)
        valeurs = [r["capacites"][c]["pourcent"] for c in cats] + [r["pourcent"]]
        for i, p in enumerate(valeurs):
            fond, texte = couleurs_pourcent(p)
            x = M + col_nom + col * i
            pdf.rect(x + 1.5, y + 2, col - 3, 18, fond=fond)
            meilleur = i < len(cats) and p == meilleurs[cats[i]] and p > 0
            if meilleur:
                pdf.rect(x + 1.5, y + 2, col - 3, 18, bord=texte, epaisseur=1.2)
            pdf.texte(x + col / 2, y + 14.5, f"{round(p)} %", 9, gras=meilleur or i == len(cats),
                      couleur=texte, align="c")
        pdf.ligne(M, y + 22, M + LU, y + 22)
        etat["y"] += 22
    etat["y"] += 8
    pdf.texte(M, etat["y"] + 10, T("pdf_legende"), 7.5, couleur=GRIS_TEXTE)
    etat["y"] += 26
    pdf.texte(M, etat["y"], T("pdf_meilleurs"), 10, gras=True, couleur=BLEU_FONCE)
    etat["y"] += 4
    for c in cats:
        etat["y"] += 14
        premier = classement_capacite(scores, c)[0]
        p = premier["capacites"][c]["pourcent"]
        pdf.texte(M + 10, etat["y"], T(c), 9, couleur=GRIS_TEXTE)
        nom = f"{premier['modele']}  ({p} %)" if p > 0 else T("aucun")
        pdf.texte(M + 210, etat["y"], pdf.raccourcir(nom, LU - 210, 9, True), 9, gras=True)

    # ----- Détail par exercice -----
    section(T("pdf_detail"), 30 + 22 * len(scores))
    col = (LU - col_nom) / (len(exercices) + 1)
    entete_tableau([f"Ex {e['id']}" for e in exercices] + [T("col_points")])
    for r in scores:
        besoin(22)
        y = etat["y"]
        pdf.texte(M + 8, y + 14, pdf.raccourcir(f"{r['rang']}. {r['modele']}", col_nom - 12, 8.5), 8.5)
        for i, e in enumerate(exercices):
            pts, sur = r["par_ex"].get(e["id"]), points_max(e)
            x = M + col_nom + col * i
            if pts is None:
                pdf.texte(x + col / 2, y + 14.5, "-", 9, couleur=GRIS_TEXTE, align="c")
                continue
            fond, texte = couleurs_pourcent(100 * pts / sur)
            pdf.rect(x + 1.5, y + 2, col - 3, 18, fond=fond)
            pdf.texte(x + col / 2, y + 14.5, f"{pts}/{sur}", 8.5, gras=(pts == sur), couleur=texte, align="c")
        x = M + col_nom + col * len(exercices)
        pdf.texte(x + col / 2, y + 14.5, f"{r['points']}/{r['sur']}", 9, gras=True, align="c")
        pdf.ligne(M, y + 22, M + LU, y + 22)
        etat["y"] += 22

    # ----- Vitesse et temps -----
    section(T("pdf_perf"), 30 + 22 * len(scores))
    titres = [T("col_vitesse"), T("col_temps"), T("col_ppm"), T("col_gpu")]
    col = (LU - col_nom) / len(titres)
    y = etat["y"]
    pdf.rect(M, y, LU, 22, fond=BLEU_FONCE)
    pdf.texte(M + 8, y + 14.5, T("col_modele"), 8.5, gras=True, couleur=BLANC)
    for i, t in enumerate(titres):
        pdf.texte(M + col_nom + col * (i + 0.5), y + 14.5, t, 8.5, gras=True, couleur=BLANC, align="c")
    etat["y"] += 22
    plus_rapide = max(r["vitesse"] for r in scores)
    for r in scores:
        besoin(22)
        y = etat["y"]
        if r["rang"] % 2 == 0:
            pdf.rect(M, y, LU, 22, fond=GRIS_CLAIR)
        pdf.texte(M + 8, y + 14, pdf.raccourcir(f"{r['rang']}. {r['modele']}", col_nom - 12, 8.5), 8.5)
        valeurs = [str(r["vitesse"]), duree_lisible(r["duree"]), str(r["par_minute"]),
                   f"{r['gpu']} %" if r["gpu"] != "" else "-"]
        for i, v in enumerate(valeurs):
            gras = i == 0 and r["vitesse"] == plus_rapide
            pdf.texte(M + col_nom + col * (i + 0.5), y + 14.5, v, 9, gras=gras, align="c")
        etat["y"] += 22

    # ----- Liste des exercices -----
    section(T("pdf_liste_ex"), 40)
    for e in exercices:
        besoin(30)
        y = etat["y"] + 12
        pdf.rect(M, y - 9, 26, 13, fond=BLEU)
        pdf.texte(M + 13, y + 0.5, f"Ex {e['id']}", 7.5, gras=True, couleur=BLANC, align="c")
        pdf.texte(M + 34, y, nom_ex(e)[2:].strip(), 9.5, gras=True)
        pdf.texte(M + 34, y + 12, T("pdf_ex_ligne", p=points_max(e), c=T(e["cat"])), 8, couleur=GRIS_TEXTE)
        etat["y"] += 28
    etat["y"] += 6
    for l in pdf.couper_lignes(T("pdf_rappel"), LU, 8):
        besoin(12)
        etat["y"] += 11
        pdf.texte(M, etat["y"], l, 8, couleur=GRIS_TEXTE)

    nom = f"rapport_hardcode{'_reflexion' if reflexion else ''}_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
    chemin = os.path.join(DOSSIER, nom)
    pdf.enregistrer(chemin, f"Comparateur hardcode v{VERSION}  -  {SIGNATURE}")
    return chemin


def ouvrir(chemin):
    """Ouvre un fichier ou un dossier avec l'application Windows par défaut."""
    try:
        if hasattr(os, "startfile"):
            os.startfile(chemin)
        else:
            subprocess.Popen(["xdg-open", chemin])
    except Exception:
        pass


def normaliser_nom_modele(texte):
    """Transforme ce que l'utilisateur colle en nom accepté par « ollama pull ».
    - « ollama pull gemma4:26b »                       -> gemma4:26b
    - https://huggingface.co/auteur/depot              -> hf.co/auteur/depot
    - .../auteur/depot/blob/main/modele-Q4_K_M.gguf    -> hf.co/auteur/depot:Q4_K_M
    Lève ValueError pour un lien vers un « Space » (application, pas un modèle)."""
    texte = (texte or "").strip().splitlines()[0].strip() if (texte or "").strip() else ""
    texte = texte.strip("\"' ")
    morceaux = texte.split()
    if len(morceaux) >= 3 and morceaux[0].lower() == "ollama" and morceaux[1].lower() in ("pull", "run"):
        texte = morceaux[2]
    m = re.search(r"(?:https?://)?(?:www\.)?(?:huggingface\.co|hf\.co)/(.+)", texte, flags=re.I)
    if m:
        chemin = m.group(1).split("?")[0].split("#")[0].strip("/")
        parties = chemin.split("/")
        if parties[0].lower() in ("spaces", "datasets"):
            raise ValueError(T("gm_space"))
        if len(parties) >= 2:
            depot = parties[1].split(":")[0]
            tag = parties[1].split(":", 1)[1] if ":" in parties[1] else ""
            fichier = parties[-1] if len(parties) > 2 else ""
            q = re.search(r"[-_.]((?:I?Q\d[A-Za-z0-9_]*)|F16|BF16|F32)\.gguf$", fichier, flags=re.I)
            if q:
                tag = q.group(1)
            return f"hf.co/{parties[0]}/{depot}" + (f":{tag}" if tag else "")
    return texte


# ---------------------------------------------------------------
# 7) EXPORT / IMPORT D'UN MODÈLE OLLAMA EN ZIP
# ---------------------------------------------------------------
# Ollama range chaque modèle en deux parties dans son dossier "models" :
#   manifests/<hôte>/<auteur>/<nom>/<tag>   : petit fichier JSON qui liste les morceaux
#   blobs/sha256-xxxx                        : les gros fichiers (poids, modèle de dialogue...)
# Le ZIP contient exactement ces fichiers, avec les mêmes chemins.

DOSSIER_MODELES_CHOISI = None   # dossier indiqué à la main par l'utilisateur (prioritaire)


def dossier_depuis_ollama(nom):
    """Demande à Ollama où est vraiment rangé un modèle.
    Retourne (dossier des modèles, digest du fichier principal) ou (None, None)."""
    try:
        info = appel("/api/show", {"model": nom}, delai=30)
    except Exception:
        return None, None
    texte = info.get("modelfile", "") or ""
    m = re.search(r"FROM\s+(.+?)[\\/]blobs[\\/](sha256-[0-9a-fA-F]{64})", texte)
    if not m:
        return None, None
    return m.group(1).strip().strip('"'), m.group(2).replace("-", ":")


def dossiers_candidats(nom=None):
    """Dossiers possibles des modèles, du plus sûr au moins sûr, sans doublon."""
    liste = []
    if DOSSIER_MODELES_CHOISI:
        liste.append(DOSSIER_MODELES_CHOISI)
    if nom is None:                                  # pas de nom : on interroge Ollama avec le 1er modèle
        installes = modeles_installes()
        nom = installes[0] if installes else None
    if nom:
        d, _ = dossier_depuis_ollama(nom)
        if d:
            liste.append(d)
    if os.environ.get("OLLAMA_MODELS"):
        liste.append(os.environ["OLLAMA_MODELS"])
    liste.append(os.path.join(os.path.expanduser("~"), ".ollama", "models"))
    resultat = []
    for d in liste:
        d = os.path.normpath(d)
        if d not in resultat:
            resultat.append(d)
    return resultat


def dossier_modeles():
    """Dossier où Ollama range ses modèles (le premier candidat qui contient 'manifests')."""
    candidats = dossiers_candidats()
    for d in candidats:
        if os.path.isdir(os.path.join(d, "manifests")):
            return d
    return candidats[0]


def chemin_relatif_manifeste(nom):
    """'gemma4:26b' -> 'manifests/registry.ollama.ai/library/gemma4/26b'."""
    nom = nom.strip()
    dernier = nom.split("/")[-1]
    if ":" in dernier:
        base, tag = nom.rsplit(":", 1)
    else:
        base, tag = nom, "latest"
    morceaux = base.split("/")
    if len(morceaux) == 1:
        morceaux = ["registry.ollama.ai", "library"] + morceaux
    elif len(morceaux) == 2:
        morceaux = ["registry.ollama.ai"] + morceaux
    return "/".join(["manifests"] + morceaux + [tag])


def trouver_manifeste(nom, dossier, digest=None):
    """Retourne le chemin relatif réel du manifeste ou None.
    1) chemin exact  2) même chemin sans tenir compte de la casse
    3) même nom de modèle et même tag  4) manifeste qui contient le fichier principal (digest)"""
    rel = chemin_relatif_manifeste(nom)
    if os.path.isfile(os.path.join(dossier, *rel.split("/"))):
        return rel
    racine = os.path.join(dossier, "manifests")
    tous = []
    for chemin, _, fichiers in os.walk(racine):
        for f in fichiers:
            tous.append(os.path.relpath(os.path.join(chemin, f), dossier).replace(os.sep, "/"))
    for r in tous:
        if r.lower() == rel.lower():
            return r
    fin = "/".join(rel.lower().split("/")[-2:])          # "nom/tag"
    proches = [r for r in tous if r.lower().endswith("/" + fin)]
    if len(proches) == 1:
        return proches[0]
    if digest:
        for r in tous:
            try:
                with open(os.path.join(dossier, *r.split("/")), encoding="utf-8") as f:
                    if digest in f.read() and r.lower().split("/")[-1] == rel.lower().split("/")[-1]:
                        return r
            except Exception:
                pass
    return None


def compter_manifestes(dossier):
    n = 0
    for _, _, fichiers in os.walk(os.path.join(dossier, "manifests")):
        n += len(fichiers)
    return n


def localiser_modele(nom, dossier=None):
    """Retourne (dossier des modèles, chemin relatif du manifeste) ou lève une erreur explicite."""
    if dossier:
        candidats = [dossier]
        digest = None
    else:
        _, digest = dossier_depuis_ollama(nom)
        candidats = dossiers_candidats(nom)
    for d in candidats:
        rel = trouver_manifeste(nom, d, digest)
        if rel:
            return d, rel
    details = "\n".join(f"  - {d} ({T('z_n_manifestes', n=compter_manifestes(d))})" for d in candidats)
    raise FileNotFoundError(T("z_introuvable", n=nom, d=details))


def blobs_du_manifeste(chemin_manifeste):
    """Liste des fichiers blobs ('blobs/sha256-...') utilisés par un manifeste."""
    with open(chemin_manifeste, encoding="utf-8") as f:
        m = json.load(f)
    digests = []
    if m.get("config", {}).get("digest"):
        digests.append(m["config"]["digest"])
    for couche in m.get("layers", []):
        if couche.get("digest"):
            digests.append(couche["digest"])
    return ["blobs/" + d.replace(":", "-") for d in digests]


def _taille_lisible(octets):
    return f"{octets / 1e9:.2f} Go" if octets >= 1e8 else f"{octets / 1e6:.1f} Mo"


def _copier_flux(source, destination, avancement, ecrire, etiquette):
    """Copie par morceaux de 16 Mo ; affiche l'avancement global tous les 10 %.
    avancement = {"total": octets à copier, "deja": octets copiés, "palier": prochain % à afficher,
                  "progres": fonction facultative qui reçoit le % (barre d'avancement de la fenêtre)}"""
    morceau = 16 * 1024 * 1024
    while True:
        bloc = source.read(morceau)
        if not bloc:
            break
        destination.write(bloc)
        avancement["deja"] += len(bloc)
        if avancement["total"]:
            pct = avancement["deja"] * 100 // avancement["total"]
            if avancement.get("progres"):
                avancement["progres"](pct)
            if pct >= avancement["palier"]:
                ecrire(f"  {etiquette} : {pct} %")
                avancement["palier"] = (pct // 10 + 1) * 10


def exporter_modeles_zip(noms, chemin_zip, ecrire, dossier=None, progres=None):
    """Exporte un ou plusieurs modèles dans un ZIP (les morceaux communs ne sont copiés qu'une fois)."""
    import shutil
    import zipfile
    fichiers, infos, sources = [], [], {}      # sources : fichier du ZIP -> chemin sur le disque
    for nom in noms:
        dossier_m, rel = localiser_modele(nom, dossier)
        ecrire(T("z_trouve", n=nom, d=dossier_m))
        sources[rel] = os.path.join(dossier_m, *rel.split("/"))
        fichiers.append(rel)
        for b in blobs_du_manifeste(sources[rel]):
            chemin_b = os.path.join(dossier_m, *b.split("/"))
            if not os.path.isfile(chemin_b):
                raise FileNotFoundError(T("z_manquant", c=chemin_b))
            if b not in fichiers:
                fichiers.append(b)
                sources[b] = chemin_b
        infos.append({"nom": nom, "manifeste": rel})

    total = sum(os.path.getsize(sources[f]) for f in fichiers)
    libre = shutil.disk_usage(os.path.dirname(os.path.abspath(chemin_zip))).free
    if libre < total + 200 * 1024 * 1024:
        raise OSError(T("z_place", a=_taille_lisible(total), b=_taille_lisible(libre)))
    ecrire(T("z_export_de", m=len(noms), f=len(fichiers), t=_taille_lisible(total)))

    temporaire = chemin_zip + ".partiel"
    avancement = {"total": total, "deja": 0, "palier": 10, "progres": progres}
    try:
        # ZIP_STORED : pas de compression (les poids ne se compressent pas, et c'est bien plus rapide)
        with zipfile.ZipFile(temporaire, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            z.writestr("ollama_export.json", json.dumps(
                {"programme": "comparer_hardcode", "date": time.strftime("%Y-%m-%d %H:%M"),
                 "modeles": infos, "taille": total}, ensure_ascii=False, indent=2))
            for f in fichiers:
                with open(sources[f], "rb") as src, z.open(f, "w", force_zip64=True) as dst:
                    _copier_flux(src, dst, avancement, ecrire, T("z_lbl_export"))
        os.replace(temporaire, chemin_zip)
    except BaseException:
        if os.path.exists(temporaire):
            os.remove(temporaire)
        raise
    ecrire(T("z_export_fini", c=chemin_zip))
    return chemin_zip


def lire_infos_zip(chemin_zip):
    """Retourne les infos d'un ZIP exporté (liste des modèles) ou lève une erreur s'il n'est pas valable."""
    import zipfile
    with zipfile.ZipFile(chemin_zip) as z:
        noms = z.namelist()
        for n in noms:   # sécurité : rien en dehors de manifests/ et blobs/
            if n != "ollama_export.json" and not (n.startswith("manifests/") or n.startswith("blobs/")):
                raise ValueError(T("z_inattendu", n=n))
            if ".." in n.split("/") or n.startswith("/") or ":" in n.split("/")[0]:
                raise ValueError(T("z_dangereux", n=n))
        if "ollama_export.json" in noms:
            return json.loads(z.read("ollama_export.json").decode("utf-8"))
        manifestes = [n for n in noms if n.startswith("manifests/")]
        if not manifestes:
            raise ValueError(T("z_aucun"))
        return {"modeles": [{"nom": m, "manifeste": m} for m in manifestes]}


def importer_zip(chemin_zip, ecrire, dossier=None, verifier=True, progres=None):
    """Importe un ZIP créé par exporter_modeles_zip dans le dossier des modèles d'Ollama."""
    import hashlib
    import shutil
    import zipfile
    dossier = dossier or dossier_modeles()
    infos = lire_infos_zip(chemin_zip)
    os.makedirs(os.path.join(dossier, "blobs"), exist_ok=True)
    with zipfile.ZipFile(chemin_zip) as z:
        elements = [i for i in z.infolist() if i.filename != "ollama_export.json" and not i.is_dir()]
        a_copier = []
        for i in elements:
            cible = os.path.join(dossier, *i.filename.split("/"))
            if i.filename.startswith("blobs/") and os.path.isfile(cible) and os.path.getsize(cible) == i.file_size:
                continue   # déjà présent (morceau partagé avec un autre modèle) : on ne recopie pas
            a_copier.append(i)
        total = sum(i.file_size for i in a_copier)
        libre = shutil.disk_usage(dossier).free
        if libre < total + 200 * 1024 * 1024:
            raise OSError(T("z_place", a=_taille_lisible(total), b=_taille_lisible(libre)))
        ecrire(T("z_import", f=len(a_copier), t=_taille_lisible(total)))
        avancement = {"total": total, "deja": 0, "palier": 10, "progres": progres}
        # Les gros fichiers d'abord, les manifestes à la fin : le modèle n'apparaît que s'il est complet
        a_copier.sort(key=lambda i: i.filename.startswith("manifests/"))
        for i in a_copier:
            cible = os.path.join(dossier, *i.filename.split("/"))
            os.makedirs(os.path.dirname(cible), exist_ok=True)
            temporaire = cible + ".partiel"
            try:
                with z.open(i) as src, open(temporaire, "wb") as dst:
                    _copier_flux(src, dst, avancement, ecrire, T("z_lbl_import"))
                if verifier and i.filename.startswith("blobs/sha256-"):
                    ecrire(T("z_verif", n=i.filename[:25]))
                    h = hashlib.sha256()
                    with open(temporaire, "rb") as f:
                        for bloc in iter(lambda: f.read(16 * 1024 * 1024), b""):
                            h.update(bloc)
                    if h.hexdigest() != i.filename.split("sha256-", 1)[1]:
                        raise ValueError(T("z_abime", n=i.filename))
                os.replace(temporaire, cible)
            except BaseException:
                if os.path.exists(temporaire):
                    os.remove(temporaire)
                raise
    noms = [m["nom"] for m in infos.get("modeles", [])]
    ecrire(T("z_import_fini", n=", ".join(noms)))
    return noms


def supprimer_modele(nom):
    """Supprime un modèle d'Ollama (équivalent de « ollama rm »)."""
    for cle in ("model", "name"):      # "model" pour les Ollama récents, "name" pour les anciens
        requete = urllib.request.Request(URL + "/api/delete", data=json.dumps({cle: nom}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="DELETE")
        try:
            with urllib.request.urlopen(requete, timeout=60):
                return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise FileNotFoundError(T("z_introuvable_ollama", n=nom))
            if cle == "name":
                raise
    return False


def telecharger_modele(nom, ecrire, progres=None):
    """Télécharge un modèle (équivalent de « ollama pull ») en affichant l'avancement tous les 5 %.
    progres(pct) (facultatif) reçoit le % du gros fichier en cours, pour la barre d'avancement."""
    requete = urllib.request.Request(URL + "/api/pull",
                                     data=json.dumps({"model": nom, "name": nom, "stream": True}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    dernier_statut, palier = "", {}
    with urllib.request.urlopen(requete, timeout=3600) as r:
        for ligne in r:
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                info = json.loads(ligne.decode("utf-8"))
            except ValueError:
                continue
            if info.get("error"):
                raise RuntimeError(info["error"])
            statut = info.get("status", "")
            total, fait = info.get("total"), info.get("completed")
            if total and fait is not None:
                if total < 50e6:               # petits fichiers (modèle de dialogue...) : pas d'avancement
                    continue
                pct = int(fait * 100 / total)
                cle = info.get("digest", statut)
                if progres and pct != palier.get(cle + "_barre"):      # seulement quand le % change
                    palier[cle + "_barre"] = pct
                    progres(pct)
                if pct >= palier.get(cle, 0):
                    ecrire(f"  {statut[:40]} : " + T("z_de", p=pct, t=_taille_lisible(total)))
                    palier[cle] = (pct // 5 + 1) * 5
            elif statut and statut != dernier_statut:
                ecrire(f"  {statut}")
                dernier_statut = statut
            if statut == "success":
                ecrire(T("z_telech_ok", n=nom))
                return True
    raise RuntimeError(T("z_telech_coupe"))


# ---------------------------------------------------------------
# 8) L'ICÔNE DU LOGICIEL (dessinée par le programme, sans fichier image)
# ---------------------------------------------------------------
# Un carré arrondi bleu avec un cube blanc (le cube représente un « modèle »).
# Le programme calcule lui-même les pixels puis fabrique une image PNG :
# pas besoin de fichier image ni de bibliothèque. Le même dessin sert pour
# la fenêtre et pour le fichier icone.ico du .exe (voir compiler.bat).
_CACHE_ICONE = {}


def _dans_polygone(x, y, sommets):
    """True si le point (x, y) est à l'intérieur du polygone convexe donné (sommets dans l'ordre)."""
    signe = 0
    for i in range(len(sommets)):
        x1, y1 = sommets[i]
        x2, y2 = sommets[(i + 1) % len(sommets)]
        c = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        if c:
            s = 1 if c > 0 else -1
            if signe == 0:
                signe = s
            elif s != signe:
                return False
    return True


def _dans_carre_arrondi(x, y, marge, rayon):
    """True si le point (x, y) (entre 0 et 1) est dans le carré aux coins arrondis."""
    if not (marge <= x <= 1 - marge and marge <= y <= 1 - marge):
        return False
    cx = min(max(x, marge + rayon), 1 - marge - rayon)
    cy = min(max(y, marge + rayon), 1 - marge - rayon)
    return (x - cx) ** 2 + (y - cy) ** 2 <= rayon ** 2


def png_icone(taille):
    """Retourne l'icône du logiciel en image PNG (octets), de taille x taille pixels."""
    import math
    import struct
    import zlib
    if taille in _CACHE_ICONE:
        return _CACHE_ICONE[taille]

    # Le cube vu en perspective : un hexagone découpé en 3 faces (dessus, gauche, droite)
    cx, cy, r = 0.5, 0.52, 0.31
    k = r * math.cos(math.pi / 6)
    haut, bas, centre = (cx, cy - r), (cx, cy + r), (cx, cy)
    haut_d, bas_d = (cx + k, cy - r / 2), (cx + k, cy + r / 2)
    haut_g, bas_g = (cx - k, cy - r / 2), (cx - k, cy + r / 2)

    def reduire(sommets, f=0.88):
        """Rapproche la face de son centre : laisse un petit espace bleu entre les faces."""
        mx = sum(p[0] for p in sommets) / len(sommets)
        my = sum(p[1] for p in sommets) / len(sommets)
        return [(mx + (px - mx) * f, my + (py - my) * f) for px, py in sommets]

    faces = [(reduire([haut, haut_d, centre, haut_g]), (255, 255, 255)),
             (reduire([haut_g, centre, bas, bas_g]), (208, 226, 248)),
             (reduire([centre, haut_d, bas_d, bas]), (146, 187, 236))]
    haut_bleu, bas_bleu = (58, 128, 210), (20, 52, 104)     # dégradé du fond

    n = 4 if taille <= 64 else 2       # n x n échantillons par pixel : bords lissés
    lignes = []
    for j in range(taille):
        ligne = bytearray()
        for i in range(taille):
            somme, dedans = [0, 0, 0], 0
            for sj in range(n):
                y = (j + (sj + 0.5) / n) / taille
                for si in range(n):
                    x = (i + (si + 0.5) / n) / taille
                    if not _dans_carre_arrondi(x, y, 0.03, 0.21):
                        continue
                    dedans += 1
                    couleur = None
                    if abs(x - cx) <= r and abs(y - cy) <= r:      # près du cube seulement
                        for sommets, c in faces:
                            if _dans_polygone(x, y, sommets):
                                couleur = c
                                break
                    if couleur is None:
                        couleur = [a + (b - a) * y for a, b in zip(haut_bleu, bas_bleu)]
                    for c in range(3):
                        somme[c] += couleur[c]
            if dedans:
                ligne += bytes([round(s / dedans) for s in somme] + [round(255 * dedans / (n * n))])
            else:
                ligne += b"\0\0\0\0"                                # transparent
        lignes.append(bytes(ligne))

    # Fabrication du fichier PNG (format simple : en-tête + pixels compressés)
    def bloc(nom, donnees):
        return (struct.pack(">I", len(donnees)) + nom + donnees
                + struct.pack(">I", zlib.crc32(nom + donnees) & 0xFFFFFFFF))
    brut = b"".join(b"\0" + l for l in lignes)
    png = (b"\x89PNG\r\n\x1a\n"
           + bloc(b"IHDR", struct.pack(">IIBBBBB", taille, taille, 8, 6, 0, 0, 0))
           + bloc(b"IDAT", zlib.compress(brut, 9)) + bloc(b"IEND", b""))
    _CACHE_ICONE[taille] = png
    return png


def ecrire_ico(chemin, tailles=(16, 24, 32, 48, 64, 128, 256)):
    """Écrit le fichier .ico du programme (utilisé par compiler.bat pour l'icône du .exe)."""
    import struct
    images = [png_icone(t) for t in tailles]
    entete = struct.pack("<HHH", 0, 1, len(images))
    decalage = 6 + 16 * len(images)
    entrees = b""
    for t, png in zip(tailles, images):
        entrees += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(png), decalage)
        decalage += len(png)
    with open(chemin, "wb") as f:
        f.write(entete + entrees + b"".join(images))
    return chemin


# ---------------------------------------------------------------
# 9) LA FENÊTRE
# ---------------------------------------------------------------
# Couleurs de l'interface
C_FOND = "#f3f5f9"
C_CARTE = "#ffffff"
C_TRAIT = "#d5dbe4"
C_TEXTE = "#1f2633"
C_GRIS = "#687385"
C_ACCENT = "#2f6fc0"
C_ACCENT_FONCE = "#1d4f91"
C_BANDEAU = "#173a6b"
C_BARRE = "#e6eaf0"
C_JOURNAL = "#1c2230"
C_JOURNAL_TEXTE = "#d5dde9"


class InfoBulle:
    """Petite bulle d'aide qui apparaît quand la souris passe sur un élément."""

    def __init__(self, widget, texte):
        self.widget, self.texte, self.bulle = widget, texte, None
        widget.bind("<Enter>", self.montrer, add="+")
        widget.bind("<Leave>", self.cacher, add="+")
        widget.bind("<ButtonPress>", self.cacher, add="+")

    def montrer(self, _evenement=None):
        import tkinter as tk
        if self.bulle:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.bulle = tk.Toplevel(self.widget)
        self.bulle.wm_overrideredirect(True)          # sans barre de titre
        self.bulle.wm_geometry(f"+{x}+{y}")
        tk.Label(self.bulle, text=self.texte, justify="left", background="#ffffe8", relief="solid",
                 borderwidth=1, wraplength=420, padx=8, pady=6).pack()

    def cacher(self, _evenement=None):
        if self.bulle:
            self.bulle.destroy()
            self.bulle = None


def dessiner_roue(canvas, couleur, fond):
    """Dessine une roue dentée (icône des réglages) dans un petit Canvas de 26 x 26."""
    import math
    canvas.delete("all")
    cx = cy = 13
    points = []
    dents = 8
    for i in range(dents * 4):
        angle = 2 * math.pi * (i - 0.5) / (dents * 4)
        rayon = 11.5 if i % 4 in (0, 1) else 8.3        # 2 points en haut de la dent, 2 au creux
        points += [cx + rayon * math.cos(angle), cy + rayon * math.sin(angle)]
    canvas.create_polygon(points, fill=couleur, outline=couleur)
    canvas.create_oval(cx - 3.6, cy - 3.6, cx + 3.6, cy + 3.6, fill=fond, outline=fond)


def taille_texte(octets):
    """1234567890 -> « 1,2 Go » (virgule en français, espagnol et allemand)."""
    if octets >= 1e9:
        texte = f"{octets / 1e9:.1f} {T('unite_go')}"
    else:
        texte = f"{octets / 1e6:.0f} {T('unite_mo')}"
    return texte if LANGUE == "en" else texte.replace(".", ",")


def contexte_texte(n):
    """131072 -> « 128 K » ; 0 -> « - »."""
    if not n:
        return "-"
    return f"{n // 1024} K" if n % 1024 == 0 else str(n)


def valeur_parametres(texte):
    """« 9.2B » -> 9.2 ; « 270M » -> 0.27 (pour trier la colonne Paramètres)."""
    m = re.match(r"\s*([\d.]+)\s*([BMK]?)", texte or "", flags=re.I)
    if not m:
        return 0
    try:
        v = float(m.group(1))
    except ValueError:
        return 0
    return v / 1000 if m.group(2).upper() == "M" else v


def raccourcir_milieu(texte, maxi=70):
    """Raccourcit un long chemin au milieu : « C:\\Users\\...\\models »."""
    return texte if len(texte) <= maxi else texte[:maxi // 2 - 2] + "..." + texte[-(maxi // 2 - 1):]


def fenetre(garde=None):
    """Ouvre la fenêtre principale. Retourne (relancer, garde) :
    relancer = True quand la langue a changé (la fenêtre est alors reconstruite) ;
    garde = ce qu'on garde d'une fenêtre à l'autre (journal, champs du benchmark, onglet ouvert)."""
    import base64
    import queue
    import threading
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import ttk, scrolledtext, messagebox, filedialog

    garde = garde or {}
    if os.name == "nt":
        import ctypes
        try:      # texte net sur les écrans réglés à 125 % ou 150 %
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:      # la barre des tâches montre l'icône du programme (et pas celle de Python)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PixtrekCoder.GestModOllama")
        except Exception:
            pass

    racine = tk.Tk()
    racine.title(f"{T('titre_fenetre')} - v{VERSION}")
    echelle = max(1.0, racine.winfo_fpixels("1i") / 96.0)

    def px(n):
        """Taille en pixels adaptée à l'écran (plus grande si Windows est réglé à 125 % ou 150 %)."""
        return int(round(n * echelle))

    racine.geometry(f"{px(1140)}x{px(800)}")
    racine.minsize(px(880), px(620))
    racine.configure(background=C_FOND)

    etat = {"arret": False, "en_cours": False, "transfert": False, "relancer": False, "ferme": False,
            "modeles": [], "memoire": {}, "connecte": None, "liste_ok": None, "dossier": None,
            "libre": None, "tri": ("nom", False), "rafraichit": False, "premier_chargement": True}
    file_msg = queue.Queue()      # textes à écrire dans le journal (envoyés par les threads)
    file_ui = queue.Queue()       # actions à faire dans la fenêtre (envoyées par les threads)

    # ----- Icône de la fenêtre -----
    try:
        etat["icones"] = [tk.PhotoImage(data=base64.b64encode(png_icone(t)).decode("ascii"))
                          for t in (16, 32, 48, 64)]
        racine.iconphoto(True, *etat["icones"])
    except Exception:
        pass

    # ----- Polices et style -----
    familles = set(tkfont.families(racine))
    POLICE = "Segoe UI" if "Segoe UI" in familles else tkfont.nametofont("TkDefaultFont").actual("family")
    MONO = "Consolas" if "Consolas" in familles else "Courier"
    for nom in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(nom).configure(family=POLICE, size=10)
        except tk.TclError:
            pass
    racine.option_add("*TCombobox*Listbox.font", (POLICE, 10))

    style = ttk.Style(racine)
    try:
        style.theme_use("clam")          # thème qui accepte les couleurs personnalisées
    except tk.TclError:
        pass
    style.configure(".", background=C_FOND, foreground=C_TEXTE, font=(POLICE, 10))
    style.configure("TFrame", background=C_FOND)
    style.configure("TLabel", background=C_FOND, foreground=C_TEXTE)
    style.configure("Gris.TLabel", foreground=C_GRIS)
    style.configure("Gras.TLabel", font=(POLICE, 10, "bold"))
    style.configure("Carte.TLabel", background=C_CARTE)
    style.configure("CarteGris.TLabel", background=C_CARTE, foreground=C_GRIS, font=(POLICE, 9))
    style.configure("CarteTitre.TLabel", background=C_CARTE, foreground=C_ACCENT_FONCE, font=(POLICE, 12, "bold"))
    style.configure("Barre.TFrame", background=C_BARRE)
    style.configure("Barre.TLabel", background=C_BARRE, foreground="#4a5568", font=(POLICE, 9))
    # Boutons plats, bord bleu au survol
    style.configure("TButton", padding=(px(12), px(5)), background="#ffffff", bordercolor="#c3cbd8",
                    lightcolor="#ffffff", darkcolor="#ffffff", focuscolor="#ffffff")
    style.map("TButton",
              background=[("disabled", "#f1f3f6"), ("pressed", "#dbe7f7"), ("active", "#eaf2fc")],
              lightcolor=[("disabled", "#f1f3f6"), ("pressed", "#dbe7f7"), ("active", "#eaf2fc")],
              darkcolor=[("disabled", "#f1f3f6"), ("pressed", "#dbe7f7"), ("active", "#eaf2fc")],
              bordercolor=[("disabled", "#dde2ea"), ("active", C_ACCENT)],
              focuscolor=[("active", "#eaf2fc")],
              foreground=[("disabled", "#a3abb8")])
    style.configure("Accent.TButton", background=C_ACCENT, foreground="#ffffff", bordercolor=C_ACCENT,
                    lightcolor=C_ACCENT, darkcolor=C_ACCENT, focuscolor=C_ACCENT, font=(POLICE, 10, "bold"))
    style.map("Accent.TButton",
              background=[("disabled", "#a9c1e3"), ("pressed", C_ACCENT_FONCE), ("active", "#3a7dd1")],
              lightcolor=[("disabled", "#a9c1e3"), ("pressed", C_ACCENT_FONCE), ("active", "#3a7dd1")],
              darkcolor=[("disabled", "#a9c1e3"), ("pressed", C_ACCENT_FONCE), ("active", "#3a7dd1")],
              bordercolor=[("disabled", "#a9c1e3"), ("active", C_ACCENT_FONCE)],
              focuscolor=[("active", "#3a7dd1"), ("pressed", C_ACCENT_FONCE)],
              foreground=[("disabled", "#eef3fa")])
    style.configure("Danger.TButton", foreground="#b42318")
    style.map("Danger.TButton", foreground=[("disabled", "#a3abb8")],
              bordercolor=[("disabled", "#dde2ea"), ("active", "#b42318")])
    style.configure("Petit.TButton", padding=(px(8), px(1)), font=(POLICE, 9))
    # Onglets
    style.configure("TNotebook", background=C_FOND, borderwidth=0, bordercolor=C_TRAIT,
                    lightcolor=C_FOND, darkcolor=C_FOND, tabmargins=(px(2), px(6), px(2), 0))
    style.configure("TNotebook.Tab", padding=(px(22), px(7)), background="#dde3ec", foreground=C_GRIS,
                    bordercolor=C_TRAIT, lightcolor="#dde3ec", font=(POLICE, 10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", C_FOND), ("active", "#e8edf4")],
              lightcolor=[("selected", C_FOND)], foreground=[("selected", C_ACCENT_FONCE)],
              expand=[("selected", (1, 1, 1, 0))])
    # Liste des modèles
    style.configure("Treeview", rowheight=px(27), background=C_CARTE, fieldbackground=C_CARTE,
                    foreground=C_TEXTE, bordercolor=C_TRAIT, lightcolor=C_CARTE, darkcolor=C_CARTE,
                    font=(POLICE, 10))
    style.map("Treeview", background=[("selected", "#d4e4f8")], foreground=[("selected", C_TEXTE)])
    style.configure("Treeview.Heading", font=(POLICE, 9, "bold"), background="#eef2f7", foreground="#4a5568",
                    bordercolor=C_TRAIT, lightcolor="#eef2f7", darkcolor=C_TRAIT, padding=(px(6), px(5)))
    style.map("Treeview.Heading", background=[("active", "#e2e9f3")])
    # Champs, cases, barres
    style.configure("TLabelframe", background=C_FOND, bordercolor=C_TRAIT, lightcolor=C_FOND, darkcolor=C_FOND)
    style.configure("TLabelframe.Label", background=C_FOND, foreground=C_ACCENT_FONCE, font=(POLICE, 10, "bold"))
    style.configure("TCheckbutton", background=C_FOND)
    style.map("TCheckbutton", background=[("active", C_FOND)])
    style.configure("TEntry", fieldbackground="#ffffff", bordercolor="#c3cbd8", lightcolor="#ffffff",
                    padding=px(4))
    style.map("TEntry", bordercolor=[("focus", C_ACCENT)], lightcolor=[("focus", C_ACCENT)])
    style.configure("TCombobox", fieldbackground="#ffffff", bordercolor="#c3cbd8", lightcolor="#ffffff",
                    padding=px(3), arrowsize=px(14))
    style.map("TCombobox", bordercolor=[("focus", C_ACCENT)], lightcolor=[("focus", C_ACCENT)],
              fieldbackground=[("readonly", "#ffffff")])
    style.configure("Horizontal.TProgressbar", background=C_ACCENT, troughcolor="#d6dce6",
                    bordercolor="#d6dce6", lightcolor=C_ACCENT, darkcolor=C_ACCENT, thickness=px(10))
    style.configure("TPanedwindow", background=C_FOND)
    style.configure("Sash", sashthickness=px(7), background=C_FOND, gripcount=0)
    style.configure("TScrollbar", background="#dfe4ec", troughcolor=C_FOND, bordercolor=C_FOND,
                    arrowcolor=C_GRIS, lightcolor="#dfe4ec", darkcolor="#dfe4ec")

    # ===============================================================
    # Petits outils de la fenêtre
    # ===============================================================
    def ecrire(texte):
        """Ajoute une ligne au journal (utilisable depuis un thread)."""
        file_msg.put(str(texte))

    def dans_ui(fonction):
        """Demande à la fenêtre d'exécuter une action (utilisable depuis un thread)."""
        file_ui.put(fonction)

    def vider_file():
        try:
            while True:
                journal.insert("end", file_msg.get_nowait() + "\n")
                journal.see("end")
        except queue.Empty:
            pass

    def actualiser():
        """Toutes les 150 ms : journal + actions demandées par les threads."""
        if etat["ferme"]:
            return
        etat["minuterie"] = racine.after(150, actualiser)
        vider_file()
        while not etat["ferme"]:
            try:
                action = file_ui.get_nowait()
            except queue.Empty:
                break
            try:
                action()
            except Exception as e:                 # une erreur ne doit jamais fermer la fenêtre
                if not etat["ferme"]:
                    ecrire(T("erreur_inattendue", e=e))

    def statut(texte):
        texte_etat.config(text=texte)

    def montrer_progression(pct):
        if not progression.winfo_ismapped():
            progression.pack(side="left", padx=px(8), before=texte_etat)
        progression["value"] = pct

    def cacher_progression():
        progression.pack_forget()
        progression["value"] = 0

    def progres(pct):
        """Avancement d'un transfert (appelé depuis le thread du transfert)."""
        dans_ui(lambda: montrer_progression(pct))

    def centrer(fen):
        """Place une petite fenêtre au milieu de la fenêtre principale."""
        fen.update_idletasks()
        x = racine.winfo_rootx() + (racine.winfo_width() - fen.winfo_width()) // 2
        y = racine.winfo_rooty() + (racine.winfo_height() - fen.winfo_height()) // 3
        fen.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def selection():
        """Noms des modèles sélectionnés dans la liste."""
        return list(arbre.selection())

    def modele_par_nom(nom):
        return next((m for m in etat["modeles"] if m["nom"] == nom), None)

    def memoire_de(nom):
        """Infos de /api/ps si le modèle est chargé en mémoire, sinon None."""
        return etat["memoire"].get(nom.lower()) or etat["memoire"].get(nom.lower() + ":latest")

    def texte_memoire(mem):
        return T("mem_gpu", p=mem["gpu"]) if mem else ""

    def dossier_connu():
        return DOSSIER_MODELES_CHOISI or etat["dossier"]

    def boite_saisie(titre, question, aide="", bouton="OK", valeur="", coller=False, normaliser=None):
        """Petite fenêtre avec un champ de texte. Retourne le texte saisi, ou None si annulé."""
        resultat = {"texte": None}
        d = tk.Toplevel(racine)
        d.title(titre)
        d.transient(racine)
        d.resizable(False, False)
        d.configure(background=C_FOND)
        corps_d = ttk.Frame(d, padding=px(16))
        corps_d.pack(fill="both", expand=True)
        ttk.Label(corps_d, text=question, style="Gras.TLabel").pack(anchor="w", pady=(0, px(6)))
        ligne = ttk.Frame(corps_d)
        ligne.pack(fill="x")
        var = tk.StringVar(value=valeur)
        champ = ttk.Entry(ligne, textvariable=var, width=66)
        champ.pack(side="left", fill="x", expand=True)

        def f_coller():
            try:
                texte = d.clipboard_get()
            except tk.TclError:              # presse-papier vide ou image
                texte = ""
            texte = texte.strip()
            if not texte:
                messagebox.showinfo(titre, T("gm_presse_vide"), parent=d)
                return
            texte = texte.splitlines()[0].strip()
            if normaliser:
                try:
                    texte = normaliser(texte)    # un lien Hugging Face devient hf.co/...
                except ValueError as e:          # lien vers un « Space » : pas un modèle
                    messagebox.showwarning(titre, str(e), parent=d)
            var.set(texte)
            champ.icursor("end")
            champ.focus_set()

        if coller:
            ttk.Button(ligne, text=T("gm_coller"), command=f_coller).pack(side="left", padx=(px(6), 0))
        if aide:
            ttk.Label(corps_d, text=aide, style="Gris.TLabel", justify="left").pack(anchor="w", pady=(px(8), 0))

        def valider(_evenement=None):
            texte = var.get().strip()
            if normaliser:
                try:
                    texte = normaliser(texte)
                except ValueError as e:
                    messagebox.showwarning(titre, str(e), parent=d)
                    return
            if not texte:
                return
            resultat["texte"] = texte
            d.destroy()

        boutons_d = ttk.Frame(corps_d)
        boutons_d.pack(fill="x", pady=(px(14), 0))
        ttk.Button(boutons_d, text=T("annuler"), command=d.destroy).pack(side="right")
        ttk.Button(boutons_d, text=bouton, style="Accent.TButton", command=valider).pack(side="right", padx=px(6))
        champ.bind("<Return>", valider)
        d.bind("<Escape>", lambda _e: d.destroy())
        centrer(d)
        d.grab_set()
        champ.focus_set()
        champ.select_range(0, "end")
        racine.wait_window(d)
        return resultat["texte"]

    def en_tache(fonction, fin, texte_statut):
        """Lance un téléchargement / export / import dans un thread pour ne pas bloquer la fenêtre."""
        if etat["transfert"]:
            messagebox.showinfo(T("gm_patientez_t"), T("gm_patientez"), parent=racine)
            return
        etat["transfert"] = True
        statut(texte_statut)
        montrer_progression(0)

        def tache():
            try:
                resultat, erreur = fonction(), None
            except Exception as e:
                resultat, erreur = None, e
                ecrire(T("erreur", e=e))

            def finir():
                etat["transfert"] = False
                cacher_progression()
                statut(T("sb_pret"))
                fin(resultat, erreur)
            dans_ui(finir)
        threading.Thread(target=tache, daemon=True).start()

    # ===============================================================
    # Liste des modèles : chargement, tri, filtre, détails
    # ===============================================================
    def rafraichir():
        """Relit la liste des modèles dans un thread (Ollama peut être lent à répondre)."""
        if etat["rafraichit"]:
            return
        etat["rafraichit"] = True
        statut(T("sb_chargement"))

        def tache():
            modeles = liste_modeles()
            memoire = modeles_en_memoire() if modeles is not None else {}
            dossier = dossier_modeles() if modeles is not None else None
            libre = espace_libre(dossier) if dossier else None

            def appliquer():
                etat["rafraichit"] = False
                etat["liste_ok"] = modeles is not None
                etat["modeles"] = modeles or []
                etat["memoire"] = memoire
                if dossier:
                    etat["dossier"], etat["libre"] = dossier, libre
                if not etat["transfert"] and not etat["en_cours"]:
                    statut(T("sb_pret"))
                remplir_liste()
                noms = [m["nom"] for m in etat["modeles"]]
                for c in champs:
                    c["values"] = noms
                if etat["premier_chargement"] and modeles is not None:
                    etat["premier_chargement"] = False
                    if not garde.get("journal"):
                        ecrire(T("msg_n_installes", n=len(noms)))
            dans_ui(appliquer)
        threading.Thread(target=tache, daemon=True).start()

    def cle_tri(m, colonne):
        if colonne == "taille":
            return m["taille"]
        if colonne == "contexte":
            return m["contexte"] or 0
        if colonne == "params":
            return valeur_parametres(m["params"])
        if colonne == "memoire":
            mem = memoire_de(m["nom"])
            return mem["gpu"] + 1 if mem else 0
        return str(m.get(colonne, "")).lower()

    def trier(colonne):
        actuelle, inverse = etat["tri"]
        if colonne == actuelle:
            etat["tri"] = (colonne, not inverse)
        else:   # les nombres sont d'abord triés du plus grand au plus petit
            etat["tri"] = (colonne, colonne in ("taille", "contexte", "params", "memoire", "date"))
        remplir_liste()

    def remplir_liste():
        """Remplit la liste avec les modèles connus, filtrés par la recherche et triés."""
        choisis = set(arbre.selection())
        arbre.delete(*arbre.get_children())
        filtre = var_recherche.get().strip().lower()
        visibles = [m for m in etat["modeles"]
                    if not filtre or filtre in m["nom"].lower() or filtre in m["famille"].lower()]
        colonne, inverse = etat["tri"]
        visibles.sort(key=lambda m: cle_tri(m, colonne), reverse=inverse)
        for i, m in enumerate(visibles):
            mem = memoire_de(m["nom"])
            tags = (["impair"] if i % 2 else []) + (["memoire"] if mem else [])
            arbre.insert("", "end", iid=m["nom"], tags=tags,
                         values=(m["nom"], m["params"] or "-", m["quantif"] or "-", taille_texte(m["taille"]),
                                 contexte_texte(m["contexte"]), m["date"], texte_memoire(mem)))
        garder = [n for n in choisis if arbre.exists(n)]
        if garder:
            arbre.selection_set(garder)
        for c in COLONNES:     # petite flèche sur la colonne triée
            fleche = (" ▼" if inverse else " ▲") if c == colonne else ""
            arbre.heading(c, text=TITRES[c] + fleche)
        # Message au milieu de la liste quand elle est vide
        if visibles:
            message_vide.place_forget()
        else:
            if etat["liste_ok"] is False:
                message_vide.config(text=T("liste_vide_ollama"))
            elif etat["liste_ok"] is None:
                message_vide.config(text=T("sb_chargement"))
            elif filtre:
                message_vide.config(text=T("liste_vide_filtre"))
            else:
                message_vide.config(text=T("liste_vide"))
            message_vide.place(relx=0.5, rely=0.42, anchor="center")
        maj_resume()
        afficher_details()

    def maj_resume():
        total = sum(m["taille"] for m in etat["modeles"])
        texte = T("resume_liste", n=len(etat["modeles"]), t=taille_texte(total))
        if etat["libre"] is not None:
            texte += "   ·   " + T("resume_libre", l=taille_texte(etat["libre"]))
        if var_recherche.get().strip():
            texte += "   ·   " + T("resume_filtre", a=len(arbre.get_children()))
        texte_resume.config(text=texte)
        dossier = dossier_connu()
        etiquette_dossier.config(text=T("gm_lbl_dossier", d=raccourcir_milieu(dossier)) if dossier else "")

    def maj_colonne_memoire():
        """Met à jour la colonne « En mémoire » sans reconstruire la liste."""
        for nom in arbre.get_children():
            mem = memoire_de(nom)
            arbre.set(nom, "memoire", texte_memoire(mem))
            tags = [t for t in arbre.item(nom, "tags") if t != "memoire"] + (["memoire"] if mem else [])
            arbre.item(nom, tags=tags)
        afficher_details()

    def maj_boutons():
        """Grise les boutons qui ont besoin d'une sélection quand rien n'est sélectionné."""
        n = len(arbre.selection())
        for b in boutons_selection:
            b.state(["!disabled"] if n else ["disabled"])
        for b in boutons_un_seul:
            b.state(["!disabled"] if n == 1 else ["disabled"])

    def afficher_details(_evenement=None):
        """Remplit la carte « Détails du modèle » à droite."""
        maj_boutons()
        noms = selection()
        if len(noms) != 1:
            for v in valeurs_det.values():
                v.config(text="")
            for e in etiquettes_det.values():
                e.grid_remove()
            if noms:
                total = sum((modele_par_nom(n) or {"taille": 0})["taille"] for n in noms)
                det_titre.config(text=T("det_plusieurs", n=len(noms)))
                det_sous.config(text=T("det_total", t=taille_texte(total)))
            else:
                det_titre.config(text=T("det_titre"))
                det_sous.config(text=T("det_aucun"))
            return
        m = modele_par_nom(noms[0])
        if not m:
            return
        for e in etiquettes_det.values():
            e.grid()
        det_titre.config(text=m["nom"])
        det_sous.config(text=T("det_base", p=m["parent"]) if m["parent"] else "")
        mem = memoire_de(m["nom"])
        if m["capacites"] is None:
            capacites = T("det_chargement")
            charger_details(m["nom"])
        else:
            capacites = ", ".join(T("cap_" + c) if "cap_" + c in TEXTES else c for c in m["capacites"]) or "-"
        valeurs = {
            "famille": m["famille"] or "-",
            "params": m["params"] or "-",
            "quantif": (m["quantif"] or "-") + (f"  ({m['format']})" if m["format"] else ""),
            "taille": taille_texte(m["taille"]),
            "contexte": (f"{m['contexte']:,}".replace(",", " ") + " tokens") if m["contexte"] else "-",
            "capacites": capacites,
            "date": m["date"] or "-",
            "empreinte": m["digest"][:12] or "-",
            "memoire": T("det_oui_mem", p=mem["gpu"], t=taille_texte(mem["taille"])) if mem else T("det_non"),
        }
        for cle, v in valeurs.items():
            valeurs_det[cle].config(text=v)

    def charger_details(nom):
        """Vieux Ollama : capacités et contexte absents de la liste -> demandés à /api/show."""
        m = modele_par_nom(nom)
        if not m or m.get("demande"):
            return
        m["demande"] = True

        def tache():
            d = details_modele(nom)

            def appliquer():
                x = modele_par_nom(nom)
                if x:
                    x["capacites"] = d.get("capacites") or []
                    x["contexte"] = x["contexte"] or d.get("contexte", 0)
                    if arbre.exists(nom):
                        arbre.set(nom, "contexte", contexte_texte(x["contexte"]))
                    afficher_details()
            dans_ui(appliquer)
        threading.Thread(target=tache, daemon=True).start()

    # ===============================================================
    # Actions sur les modèles
    # ===============================================================
    def verifier_selection(un_seul=False):
        noms = selection()
        if not noms:
            messagebox.showinfo(T("m_modeles"), T("gm_selection"), parent=racine)
            return None
        if un_seul and len(noms) > 1:
            messagebox.showinfo(T("m_modeles"), T("cp_un_seul"), parent=racine)
            return None
        return noms

    def copier_nom(_evenement=None):
        """Copie le nom du ou des modèles sélectionnés dans le presse-papier (un par ligne)."""
        noms = selection()
        if not noms:
            return
        racine.clipboard_clear()
        racine.clipboard_append("\n".join(noms))
        racine.update()                 # le texte reste dans le presse-papier
        statut(T("gm_copie", n=", ".join(noms)))

    def ajouter_au_bench(_evenement=None):
        """Met les modèles sélectionnés dans les champs libres de l'onglet Benchmark."""
        noms = verifier_selection()
        if not noms:
            return
        deja = [c.get().strip() for c in champs]
        ajoutes = []
        for nom in noms:
            if nom in deja:
                continue
            libre = next((c for c in champs if not c.get().strip()), None)
            if libre is None:
                messagebox.showinfo(T("onglet_bench"), T("gm_champs_pleins", n=NB_CHAMPS), parent=racine)
                break
            libre.set(nom)
            deja.append(nom)
            ajoutes.append(nom)
        if ajoutes:
            statut(T("bench_ajoute", n=", ".join(ajoutes)))

    def telecharger(nom_initial=""):
        """Fenêtre « Télécharger un modèle » (comme « ollama pull »)."""
        nom = boite_saisie(T("gm_ajouter_t"), T("gm_ajouter_q"), T("gm_exemples"), T("gm_telecharger"),
                           valeur=nom_initial, coller=True, normaliser=normaliser_nom_modele)
        if not nom:
            return
        ecrire(T("gm_telechargement", n=nom))

        def fin(_resultat, erreur):
            if erreur:
                messagebox.showerror(T("gm_ajouter_t"), T("gm_telech_echec", e=erreur), parent=racine)
            else:
                rafraichir()
                messagebox.showinfo(T("gm_ajouter_t"), T("gm_ajoute", n=nom), parent=racine)
        en_tache(lambda: telecharger_modele(nom, ecrire, progres), fin, T("sb_telech", n=nom))

    def mettre_a_jour():
        """Retélécharge les modèles choisis : seuls les morceaux qui ont changé sont récupérés."""
        noms = verifier_selection()
        if not noms or not messagebox.askyesno(T("m_maj"), T("maj_q", n="\n- ".join(noms)), parent=racine):
            return

        def travail_maj():
            for nom in noms:
                ecrire(T("gm_telechargement", n=nom))
                telecharger_modele(nom, ecrire, progres)

        def fin(_resultat, erreur):
            rafraichir()
            if erreur:
                messagebox.showerror(T("m_maj"), T("gm_telech_echec", e=erreur), parent=racine)
            else:
                messagebox.showinfo(T("m_maj"), T("maj_ok"), parent=racine)
        en_tache(travail_maj, fin, T("sb_telech", n=", ".join(noms)))

    def copier_sous():
        """Crée une copie d'un modèle sous un autre nom (comme « ollama cp »)."""
        noms = verifier_selection(un_seul=True)
        if not noms:
            return
        source = noms[0]
        nouveau = boite_saisie(T("cp_titre"), T("cp_question", n=source), T("cp_aide"), T("cp_bouton"),
                               valeur=source)
        if not nouveau or nouveau == source:
            return
        if modele_par_nom(nouveau) or modele_par_nom(nouveau + ":latest"):
            messagebox.showwarning(T("cp_titre"), T("cp_existe"), parent=racine)
            return
        try:
            copier_modele(source, nouveau)
            ecrire(T("cp_ok", n=nouveau))
            rafraichir()
        except Exception as e:
            ecrire(T("erreur", e=e))
            messagebox.showerror(T("cp_titre"), T("cp_echec", e=e), parent=racine)

    def supprimer(_evenement=None):
        noms = verifier_selection()
        if not noms:
            return
        if not messagebox.askyesno(T("gm_supprimer_t"), T("gm_supprimer_q", n="\n- ".join(noms)),
                                   icon="warning", parent=racine):
            return
        erreurs = []
        for nom in noms:
            try:
                supprimer_modele(nom)
                ecrire(T("gm_supprime", n=nom))
            except Exception as e:
                erreurs.append(f"{nom} : {e}")
                ecrire(T("gm_supp_erreur", n=nom, e=e))
        rafraichir()
        if erreurs:
            messagebox.showerror(T("gm_supprimer_t"), T("gm_supp_echec", e="\n".join(erreurs)), parent=racine)

    def decharger_selection():
        """Libère la mémoire (VRAM / RAM) occupée par les modèles choisis."""
        noms = verifier_selection()
        if not noms:
            return

        def tache():
            for nom in noms:
                try:
                    appel("/api/generate", {"model": nom, "keep_alive": 0}, delai=60)
                    ecrire(T("decharge_ok", n=nom))
                except Exception as e:
                    ecrire(T("erreur", e=e))
            memoire = modeles_en_memoire()

            def appliquer():
                etat["memoire"] = memoire
                maj_colonne_memoire()
            dans_ui(appliquer)
        threading.Thread(target=tache, daemon=True).start()

    def voir_modelfile():
        """Affiche le Modelfile du modèle (sa « recette » : fichier de base, modèle de dialogue, paramètres)."""
        noms = verifier_selection(un_seul=True)
        if not noms:
            return
        nom = noms[0]
        f = tk.Toplevel(racine)
        f.title(T("modelfile_titre", n=nom))
        f.geometry(f"{px(820)}x{px(560)}")
        f.configure(background=C_FOND)
        zone = scrolledtext.ScrolledText(f, font=(MONO, 9), wrap="none", relief="flat", borderwidth=0,
                                         background=C_CARTE, padx=px(8), pady=px(6))
        zone.pack(fill="both", expand=True, padx=px(10), pady=(px(10), 0))
        zone.insert("end", T("det_chargement"))
        bas = ttk.Frame(f, padding=px(10))
        bas.pack(fill="x")

        def copier_tout():
            f.clipboard_clear()
            f.clipboard_append(zone.get("1.0", "end-1c"))
            f.update()
        ttk.Button(bas, text=T("fermer"), command=f.destroy).pack(side="right")
        ttk.Button(bas, text=T("copier_tout"), command=copier_tout).pack(side="right", padx=px(6))
        f.bind("<Escape>", lambda _e: f.destroy())
        centrer(f)

        def tache():
            texte = details_modele(nom).get("modelfile") or T("z_introuvable_ollama", n=nom)

            def appliquer():
                if f.winfo_exists():
                    zone.delete("1.0", "end")
                    zone.insert("end", texte)
            dans_ui(appliquer)
        threading.Thread(target=tache, daemon=True).start()

    def exporter_zip():
        noms = verifier_selection()
        if not noms:
            return
        nom_defaut = re.sub(r'[\\/:*?"<>|]+', "_", noms[0] if len(noms) == 1 else "modeles") + ".zip"
        chemin = filedialog.asksaveasfilename(parent=racine, title=T("gm_exporter_dialog"),
                                              initialdir=DOSSIER, initialfile=nom_defaut,
                                              defaultextension=".zip",
                                              filetypes=[(T("gm_type_fichier"), "*.zip")])
        if not chemin:
            return
        ecrire(T("gm_export_de", n=", ".join(noms)))

        def fin(resultat, erreur):
            if erreur:
                messagebox.showerror(T("gm_exporter_t"), T("gm_export_echec", e=erreur), parent=racine)
            else:
                messagebox.showinfo(T("gm_exporter_t"), T("gm_export_ok", r=resultat), parent=racine)
        en_tache(lambda: exporter_modeles_zip(noms, chemin, ecrire, progres=progres), fin, T("sb_export"))

    def importer():
        chemin = filedialog.askopenfilename(parent=racine, title=T("gm_importer_dialog"), initialdir=DOSSIER,
                                            filetypes=[(T("gm_type_fichier"), "*.zip")])
        if not chemin:
            return
        try:
            infos_zip = lire_infos_zip(chemin)
        except Exception as e:
            messagebox.showerror(T("gm_importer_t"), T("gm_import_invalide", e=e), parent=racine)
            return
        noms = [m["nom"] for m in infos_zip.get("modeles", [])]
        installes_noms = [m["nom"].lower() for m in etat["modeles"]]
        deja = [n for n in noms if n.lower() in installes_noms or n.lower() + ":latest" in installes_noms]
        message = T("gm_contenu") + "\n- " + "\n- ".join(noms)
        if deja:
            message += "\n\n" + T("gm_remplace", n=", ".join(deja))
        message += ("\n\n" + T("gm_dossier_ollama", d=dossier_connu() or dossier_modeles())
                    + "\n\n" + T("gm_lancer_import"))
        if not messagebox.askyesno(T("gm_importer_t"), message, parent=racine):
            return
        ecrire(T("gm_import_de", c=chemin))

        def fin(resultat, erreur):
            if erreur:
                messagebox.showerror(T("gm_importer_t"), T("gm_import_echec", e=erreur), parent=racine)
                return
            visibles = [m["nom"].lower() for m in (liste_modeles() or [])]
            rafraichir()
            absents = [n for n in resultat if n.lower() not in visibles and n.lower() + ":latest" not in visibles]
            if absents:
                messagebox.showwarning(T("gm_importer_t"), T("gm_import_absents", n=", ".join(absents)),
                                       parent=racine)
            else:
                messagebox.showinfo(T("gm_importer_t"), T("gm_import_ok"), parent=racine)
        en_tache(lambda: importer_zip(chemin, ecrire, progres=progres), fin, T("sb_import"))

    def choisir_dossier():
        global DOSSIER_MODELES_CHOISI
        dossier = filedialog.askdirectory(parent=racine, title=T("gm_dossier_dialog"),
                                          initialdir=dossier_connu() or os.path.expanduser("~"))
        if not dossier:
            return
        if not os.path.isdir(os.path.join(dossier, "manifests")):
            messagebox.showwarning(T("gm_dossier_t"), T("gm_pas_manifests"), parent=racine)
            return
        DOSSIER_MODELES_CHOISI = os.path.normpath(dossier)
        etat["libre"] = espace_libre(dossier)
        maj_resume()
        ecrire(T("gm_dossier_choisi", d=dossier, n=compter_manifestes(dossier)))

    def ouvrir_dossier_modeles():
        dossier = dossier_connu()
        if dossier and os.path.isdir(dossier):
            ouvrir(dossier)
        else:
            messagebox.showinfo(T("gm_dossier_t"), T("liste_vide_ollama"), parent=racine)

    # ===============================================================
    # Fenêtres « Réglages » et « À propos »
    # ===============================================================
    def ouvrir_reglages():
        fen = tk.Toplevel(racine)
        fen.title(T("reglages"))
        fen.transient(racine)
        fen.resizable(False, False)
        fen.configure(background=C_FOND)
        corps_r = ttk.Frame(fen, padding=px(18))
        corps_r.pack(fill="both", expand=True)

        # 1) La version du logiciel, en premier
        ttk.Label(corps_r, text=T("version", v=VERSION), font=(POLICE, 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Separator(corps_r).grid(row=1, column=0, columnspan=3, sticky="we", pady=px(10))

        # 2) La langue
        ttk.Label(corps_r, text=T("langue")).grid(row=2, column=0, sticky="w", pady=px(4))
        choix_langue = ttk.Combobox(corps_r, values=[nom for _, nom in LANGUES], state="readonly", width=22)
        choix_langue.set(dict(LANGUES)[LANGUE])
        choix_langue.grid(row=2, column=1, sticky="w", padx=px(8), pady=px(4))

        # 3) La taille du contexte (utilisée par le benchmark), avec sa bulle d'aide
        ttk.Label(corps_r, text=T("contexte")).grid(row=3, column=0, sticky="w", pady=px(4))
        choix_ctx = ttk.Combobox(corps_r, values=[T("auto"), "4096", "8192", "16384", "32768", "65536"], width=22)
        choix_ctx.set(str(CONTEXTE_CHOISI) if CONTEXTE_CHOISI else T("auto"))
        choix_ctx.grid(row=3, column=1, sticky="w", padx=px(8), pady=px(4))
        aide = tk.Label(corps_r, text=" ? ", font=(POLICE, 9, "bold"), fg="white", bg=C_ACCENT,
                        cursor="question_arrow")
        aide.grid(row=3, column=2, sticky="w")
        InfoBulle(aide, T("contexte_bulle"))
        InfoBulle(choix_ctx, T("contexte_bulle"))

        def enregistrer():
            global CONTEXTE_CHOISI, LANGUE
            texte_ctx = choix_ctx.get().strip()
            if texte_ctx == "" or texte_ctx.lower() == T("auto").lower():
                nouveau_ctx = 0
            else:
                try:
                    nouveau_ctx = int(texte_ctx.replace(" ", ""))
                    if not 2048 <= nouveau_ctx <= 262144:
                        raise ValueError
                except ValueError:
                    messagebox.showwarning(T("reglages"), T("contexte_invalide"), parent=fen)
                    return
            nouvelle_langue = next(code for code, nom in LANGUES if nom == choix_langue.get())
            change_langue = nouvelle_langue != LANGUE
            CONTEXTE_CHOISI, LANGUE = nouveau_ctx, nouvelle_langue
            if not sauver_reglages():
                ecrire(T("reglages_non_sauves", f=FICHIER_REGLAGES))
            ecrire(T("reglages_ok", l=dict(LANGUES)[LANGUE], c=nouveau_ctx or T("auto")))
            fen.destroy()
            if change_langue:
                if etat["en_cours"] or etat["transfert"]:
                    messagebox.showinfo(T("reglages"), T("langue_plus_tard"), parent=racine)
                else:
                    etat["relancer"] = True      # la fenêtre est reconstruite dans la nouvelle langue
                    terminer()

        boutons_r = ttk.Frame(corps_r)
        boutons_r.grid(row=4, column=0, columnspan=3, sticky="e", pady=(px(16), 0))
        ttk.Button(boutons_r, text=T("enregistrer"), style="Accent.TButton", command=enregistrer).pack(side="left")
        ttk.Button(boutons_r, text=T("annuler"), command=fen.destroy).pack(side="left", padx=(px(6), 0))

        # 4) La signature, à la fin
        ttk.Separator(corps_r).grid(row=5, column=0, columnspan=3, sticky="we", pady=(px(14), px(6)))
        ttk.Label(corps_r, text=T("credit", a=AUTEUR, l=LICENCE, y=ANNEE), foreground="#7a7f87",
                  font=(POLICE, 8)).grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Label(corps_r, text=SIGNATURE, foreground="#7a7f87", font=(POLICE, 9, "italic")).grid(
            row=6, column=2, sticky="e")
        fen.bind("<Escape>", lambda _e: fen.destroy())
        fen.bind("<Return>", lambda _e: enregistrer())
        centrer(fen)
        fen.grab_set()                       # fenêtre « modale » : on la ferme avant de continuer

    def a_propos():
        f = tk.Toplevel(racine)
        f.title(T("m_apropos").rstrip(". "))
        f.transient(racine)
        f.resizable(False, False)
        f.configure(background=C_FOND)
        corps_a = ttk.Frame(f, padding=px(20))
        corps_a.pack(fill="both", expand=True)
        try:
            etat["img_apropos"] = tk.PhotoImage(data=base64.b64encode(png_icone(px(64))).decode("ascii"))
            ttk.Label(corps_a, image=etat["img_apropos"]).pack()
        except Exception:
            pass
        ttk.Label(corps_a, text=T("titre_fenetre"), font=(POLICE, 13, "bold"),
                  foreground=C_ACCENT_FONCE).pack(pady=(px(8), 0))
        ttk.Label(corps_a, text=T("version", v=VERSION), style="Gris.TLabel").pack()
        ttk.Label(corps_a, text=T("apropos_texte"), justify="center", wraplength=px(420)).pack(pady=px(12))
        ttk.Separator(corps_a).pack(fill="x", pady=(0, px(8)))
        ttk.Label(corps_a, text=T("credit", a=AUTEUR, l=LICENCE, y=ANNEE), style="Gris.TLabel",
                  font=(POLICE, 9)).pack()
        if DEPOT_GITHUB:
            import webbrowser
            lien = ttk.Label(corps_a, text=T("lien_github"), foreground=C_ACCENT, cursor="hand2",
                             font=(POLICE, 9, "underline"))
            lien.pack(pady=(px(2), 0))
            lien.bind("<Button-1>", lambda _e: webbrowser.open(DEPOT_GITHUB))
        ttk.Label(corps_a, text=SIGNATURE, foreground="#7a7f87", font=(POLICE, 9, "italic")).pack(pady=(px(4), 0))
        ttk.Button(corps_a, text="OK", style="Accent.TButton", command=f.destroy).pack(pady=(px(12), 0))
        f.bind("<Escape>", lambda _e: f.destroy())
        f.bind("<Return>", lambda _e: f.destroy())
        centrer(f)
        f.grab_set()

    # ===============================================================
    # Benchmark : lancement des tests et rapport PDF
    # ===============================================================
    def export_pdf():
        try:
            donnees = DERNIERS_RESULTATS or charger_dernier_csv()
            if not donnees:
                messagebox.showinfo(T("pdf_box"), T("pdf_aucun_test"), parent=racine)
                return
            chemin = exporter_pdf(donnees)
            ecrire(T("pdf_cree", c=chemin))
            if messagebox.askyesno(T("pdf_box"), T("pdf_ouvrir", n=os.path.basename(chemin)), parent=racine):
                ouvrir(chemin)
        except Exception as e:
            messagebox.showerror(T("pdf_box"), T("pdf_impossible", e=e), parent=racine)

    def progres_test(fait, total):
        def appliquer():
            barre_test.configure(maximum=max(total, 1), value=fait)
            texte_test.config(text=T("bench_avance", a=fait, b=total))
        dans_ui(appliquer)

    def fin_test():
        b_lancer.state(["!disabled"])
        b_arret.state(["disabled"])
        statut(T("sb_pret"))
        rafraichir()

    def travail(modeles, reflexion):
        try:
            lancer_tests(modeles, reflexion, ecrire, lambda: etat["arret"], progres_test)
        except Exception as e:
            ecrire(T("erreur_inattendue", e=e))
        finally:
            etat["en_cours"] = False
            ecrire(T("termine"))
            dans_ui(fin_test)

    def lancer():
        if etat["en_cours"]:
            return
        modeles = []
        for c in champs:
            nom = c.get().strip()
            if nom and nom not in modeles:      # vide ou doublon : ignoré
                modeles.append(nom)
        if not modeles:
            ecrire(T("saisir_un"))
            messagebox.showinfo(T("onglet_bench"), T("saisir_un"), parent=racine)
            return
        etat["arret"] = False
        etat["en_cours"] = True
        b_lancer.state(["disabled"])
        b_arret.state(["!disabled"])
        barre_test.configure(value=0, maximum=len(modeles) * len(EXERCICES))
        texte_test.config(text=T("bench_avance", a=0, b=len(modeles) * len(EXERCICES)))
        statut(T("sb_test", n=len(modeles)))
        onglets.select(page_b)
        ecrire(T("lancement", n=len(modeles)))
        threading.Thread(target=travail, args=(modeles, var_reflexion.get()), daemon=True).start()

    def arreter():
        if etat["en_cours"]:
            etat["arret"] = True
            ecrire(T("arret_demande"))

    # ===============================================================
    # Surveillance d'Ollama (toutes les 4 secondes, dans un thread)
    # ===============================================================
    def maj_etat_ollama(version, memoire):
        avant = etat["connecte"]
        etat["connecte"] = bool(version)
        dessiner_pastille(etat["connecte"])
        texte_ollama.config(text=T("ollama_ok", v=version) if version else T("ollama_ko"))
        if version and not avant:                       # Ollama vient de répondre : on lit la liste
            etat["memoire"] = memoire
            rafraichir()
        elif not version and avant is not False:        # Ollama ne répond pas (ou plus)
            if avant is None and not garde.get("journal"):
                ecrire(T("msg_ollama_debut"))
            etat["liste_ok"] = False
            etat["modeles"], etat["memoire"] = [], {}
            remplir_liste()
        elif version and memoire != etat["memoire"]:   # un modèle a été chargé ou déchargé
            etat["memoire"] = memoire
            maj_colonne_memoire()

    def surveiller():
        while not etat["ferme"]:
            version = version_ollama()
            memoire = modeles_en_memoire() if version else {}
            dans_ui(lambda v=version, m=memoire: maj_etat_ollama(v, m))
            for _ in range(40):
                if etat["ferme"]:
                    return
                time.sleep(0.1)

    # ===============================================================
    # Fermeture
    # ===============================================================
    def terminer():
        """Ferme la fenêtre en gardant le journal et les champs (utile au changement de langue)."""
        vider_file()
        etat["garde"] = {"journal": journal.get("1.0", "end-1c"), "champs": [c.get() for c in champs],
                         "reflexion": var_reflexion.get(), "onglet": onglets.index("current")}
        etat["ferme"] = True
        try:
            racine.after_cancel(etat["minuterie"])
        except Exception:
            pass
        racine.destroy()

    def fermer():
        if etat["en_cours"] or etat["transfert"]:
            if not messagebox.askyesno(T("quitter_t"), T("quitter_q"), icon="warning", parent=racine):
                return
        terminer()

    # ===============================================================
    # Construction de la fenêtre
    # ===============================================================
    # ----- Bandeau du haut : icône, titre, état d'Ollama -----
    bandeau = tk.Frame(racine, background=C_BANDEAU)
    bandeau.pack(fill="x")
    try:
        etat["img_bandeau"] = tk.PhotoImage(data=base64.b64encode(png_icone(px(44))).decode("ascii"))
        tk.Label(bandeau, image=etat["img_bandeau"], background=C_BANDEAU).pack(
            side="left", padx=(px(16), px(12)), pady=px(10))
    except Exception:
        pass
    textes_bandeau = tk.Frame(bandeau, background=C_BANDEAU)
    textes_bandeau.pack(side="left", pady=px(8))
    tk.Label(textes_bandeau, text=T("titre_fenetre"), font=(POLICE, 16, "bold"), fg="white",
             bg=C_BANDEAU).pack(anchor="w")
    tk.Label(textes_bandeau, text=T("sous_titre"), font=(POLICE, 10), fg="#b7cbe6",
             bg=C_BANDEAU).pack(anchor="w")
    pastille = tk.Frame(bandeau, background="#24497f", padx=px(12), pady=px(6))
    pastille.pack(side="right", padx=px(16))
    point = tk.Canvas(pastille, width=px(12), height=px(12), background="#24497f", highlightthickness=0)
    point.pack(side="left", padx=(0, px(8)))
    texte_ollama = tk.Label(pastille, text=T("ollama_attente"), fg="white", bg="#24497f",
                            font=(POLICE, 10, "bold"))
    texte_ollama.pack(side="left")

    def dessiner_pastille(ok):
        point.delete("all")
        couleur = "#9aa7b8" if ok is None else ("#3ddc84" if ok else "#ff6b6b")
        point.create_oval(1, 1, px(11), px(11), fill=couleur, outline=couleur)
    dessiner_pastille(None)

    # ----- Barre d'état du bas : roue dentée, message, avancement, version -----
    barre = ttk.Frame(racine, style="Barre.TFrame", padding=(px(8), px(3)))
    barre.pack(side="bottom", fill="x")
    roue = tk.Canvas(barre, width=26, height=26, highlightthickness=0, background=C_BARRE, cursor="hand2")
    roue.pack(side="left", padx=(0, px(6)))
    dessiner_roue(roue, "#4b5563", C_BARRE)
    roue.bind("<Enter>", lambda _e: dessiner_roue(roue, C_ACCENT, C_BARRE), add="+")
    roue.bind("<Leave>", lambda _e: dessiner_roue(roue, "#4b5563", C_BARRE), add="+")
    roue.bind("<Button-1>", lambda _e: ouvrir_reglages())
    InfoBulle(roue, T("reglages"))
    progression = ttk.Progressbar(barre, length=px(220), mode="determinate", maximum=100)
    texte_etat = ttk.Label(barre, text=T("sb_pret"), style="Barre.TLabel")
    texte_etat.pack(side="left", padx=px(4))
    # Mention discrète en bas à droite : version, auteur, licence, année
    credit = ttk.Label(barre, text=f"v{VERSION}  ·  " + T("credit", a=AUTEUR, l=LICENCE, y=ANNEE),
                       style="Barre.TLabel", foreground="#7a8496", font=(POLICE, 8), cursor="hand2")
    credit.pack(side="right")
    credit.bind("<Button-1>", lambda _e: a_propos())

    # ----- Milieu : onglets en haut, journal en bas (la séparation se déplace à la souris) -----
    panneaux = ttk.PanedWindow(racine, orient="vertical")
    panneaux.pack(fill="both", expand=True, padx=px(10), pady=(px(2), px(4)))
    onglets = ttk.Notebook(panneaux)
    panneaux.add(onglets, weight=5)
    cadre_journal = ttk.Frame(panneaux)
    panneaux.add(cadre_journal, weight=1)

    # ===== Onglet 1 : Modèles (fonction principale) =====
    page_m = ttk.Frame(onglets, padding=(px(4), px(10), px(4), px(4)))
    onglets.add(page_m, text="   " + T("onglet_modeles") + "   ")

    outils = ttk.Frame(page_m)
    outils.pack(fill="x", pady=(0, px(8)))
    ttk.Button(outils, text=T("tb_telecharger"), style="Accent.TButton",
               command=lambda: telecharger()).pack(side="left")
    ttk.Button(outils, text=T("gm_btn_importer"), command=lambda: importer()).pack(side="left", padx=(px(6), 0))
    b_exporter = ttk.Button(outils, text=T("tb_exporter"), command=lambda: exporter_zip())
    b_exporter.pack(side="left", padx=(px(6), 0))
    ttk.Separator(outils, orient="vertical").pack(side="left", fill="y", padx=px(10), pady=px(3))
    b_maj = ttk.Button(outils, text=T("tb_maj"), command=lambda: mettre_a_jour())
    b_maj.pack(side="left")
    b_decharger = ttk.Button(outils, text=T("tb_decharger"), command=lambda: decharger_selection())
    b_decharger.pack(side="left", padx=(px(6), 0))
    b_supprimer = ttk.Button(outils, text=T("gm_supprimer_t"), style="Danger.TButton", command=lambda: supprimer())
    b_supprimer.pack(side="left", padx=(px(6), 0))
    b_actualiser = ttk.Button(outils, text=T("tb_actualiser"), command=lambda: rafraichir())
    b_actualiser.pack(side="right")
    var_recherche = tk.StringVar()
    recherche = ttk.Entry(outils, textvariable=var_recherche, width=26)
    recherche.pack(side="right", padx=(px(6), px(10)))
    ttk.Label(outils, text=T("rechercher"), style="Gris.TLabel").pack(side="right")
    var_recherche.trace_add("write", lambda *_a: remplir_liste())
    recherche.bind("<Escape>", lambda _e: var_recherche.set(""))

    corps = ttk.PanedWindow(page_m, orient="horizontal")
    corps.pack(fill="both", expand=True)

    # Liste des modèles
    cadre_arbre = tk.Frame(corps, background=C_CARTE, highlightthickness=1, highlightbackground=C_TRAIT)
    corps.add(cadre_arbre, weight=3)
    COLONNES = ("nom", "params", "quantif", "taille", "contexte", "date", "memoire")
    TITRES = {"nom": T("gm_col_nom"), "params": T("col_params"), "quantif": T("col_quantif"),
              "taille": T("gm_col_taille"), "contexte": T("col_contexte"), "date": T("gm_col_date"),
              "memoire": T("col_memoire")}
    # Largeurs de départ : toutes les colonnes s'agrandissent ou rétrécissent avec la fenêtre
    largeurs = {"nom": 250, "params": 76, "quantif": 76, "taille": 72, "contexte": 84, "date": 84, "memoire": 92}
    arbre = ttk.Treeview(cadre_arbre, columns=COLONNES, show="headings", selectmode="extended")
    for c in COLONNES:
        arbre.heading(c, text=TITRES[c], command=lambda c=c: trier(c),
                      anchor="w" if c == "nom" else "center")
        arbre.column(c, width=px(largeurs[c]), minwidth=px(50), stretch=True,
                     anchor="w" if c == "nom" else ("e" if c == "taille" else "center"))
    defil = ttk.Scrollbar(cadre_arbre, orient="vertical", command=arbre.yview)
    arbre.configure(yscrollcommand=defil.set)
    defil.pack(side="right", fill="y")
    arbre.pack(side="left", fill="both", expand=True)
    arbre.tag_configure("impair", background="#f6f8fb")
    arbre.tag_configure("memoire", foreground="#13703a")
    message_vide = tk.Label(arbre, text="", background=C_CARTE, foreground=C_GRIS, font=(POLICE, 11),
                            justify="center")

    # Carte « Détails du modèle » à droite
    carte = tk.Frame(corps, background=C_CARTE, highlightthickness=1, highlightbackground=C_TRAIT,
                     padx=px(14), pady=px(12))
    corps.add(carte, weight=1)
    det_titre = ttk.Label(carte, text=T("det_titre"), style="CarteTitre.TLabel", wraplength=px(290))
    det_titre.pack(anchor="w", fill="x")
    det_sous = ttk.Label(carte, text="", style="CarteGris.TLabel", wraplength=px(290))
    det_sous.pack(anchor="w", pady=(px(2), px(6)))
    grille = tk.Frame(carte, background=C_CARTE)
    grille.pack(fill="x")
    valeurs_det, etiquettes_det = {}, {}
    for i, cle in enumerate(["famille", "params", "quantif", "taille", "contexte", "capacites",
                             "date", "empreinte", "memoire"]):
        e = ttk.Label(grille, text=T("det_" + cle), style="CarteGris.TLabel")
        e.grid(row=i, column=0, sticky="nw", pady=px(2), padx=(0, px(12)))
        v = ttk.Label(grille, text="", style="Carte.TLabel", wraplength=px(160), justify="left")
        v.grid(row=i, column=1, sticky="nw", pady=px(2))
        etiquettes_det[cle], valeurs_det[cle] = e, v
    grille.columnconfigure(1, weight=1)
    boutons_det = tk.Frame(carte, background=C_CARTE)
    boutons_det.pack(side="bottom", fill="x", pady=(px(8), 0))
    b_det_bench = ttk.Button(boutons_det, text=T("btn_bench"), style="Petit.TButton",
                             command=lambda: ajouter_au_bench())
    b_det_copier = ttk.Button(boutons_det, text=T("gm_menu_copier"), style="Petit.TButton",
                              command=lambda: copier_nom())
    b_det_modelfile = ttk.Button(boutons_det, text=T("m_modelfile"), style="Petit.TButton",
                                 command=lambda: voir_modelfile())
    b_det_copie = ttk.Button(boutons_det, text=T("m_copier_sous"), style="Petit.TButton",
                             command=lambda: copier_sous())
    for b in (b_det_bench, b_det_copier, b_det_modelfile, b_det_copie):
        b.pack(fill="x", pady=px(2), ipady=px(2))
    boutons_selection = [b_exporter, b_maj, b_decharger, b_supprimer, b_det_bench, b_det_copier]
    boutons_un_seul = [b_det_modelfile, b_det_copie]

    # Résumé sous la liste
    pied = ttk.Frame(page_m)
    pied.pack(fill="x", pady=(px(8), 0))
    texte_resume = ttk.Label(pied, text="", style="Gris.TLabel")
    texte_resume.pack(side="left")
    ttk.Button(pied, text=T("gm_btn_dossier"), style="Petit.TButton",
               command=lambda: choisir_dossier()).pack(side="right")
    etiquette_dossier = ttk.Label(pied, text="", style="Gris.TLabel")
    etiquette_dossier.pack(side="right", padx=px(8))

    # Clavier et souris sur la liste
    menu_liste = tk.Menu(racine, tearoff=0)
    menu_liste.add_command(label=T("gm_menu_copier"), command=copier_nom, accelerator="Ctrl+C")
    menu_liste.add_command(label=T("btn_bench"), command=ajouter_au_bench)
    menu_liste.add_separator()
    menu_liste.add_command(label=T("m_maj"), command=mettre_a_jour)
    menu_liste.add_command(label=T("m_copier_sous"), command=copier_sous)
    menu_liste.add_command(label=T("m_decharger"), command=decharger_selection)
    menu_liste.add_command(label=T("m_modelfile"), command=voir_modelfile)
    menu_liste.add_command(label=T("gm_btn_exporter"), command=exporter_zip)
    menu_liste.add_separator()
    menu_liste.add_command(label=T("gm_supprimer_t") + "...", command=supprimer, accelerator=T("touche_suppr"))

    def clic_droit(evenement):
        ligne_survolee = arbre.identify_row(evenement.y)
        if ligne_survolee and ligne_survolee not in arbre.selection():
            arbre.selection_set(ligne_survolee)       # sélectionne la ligne sous la souris
        if arbre.selection():
            try:
                menu_liste.tk_popup(evenement.x_root, evenement.y_root)
            finally:
                menu_liste.grab_release()

    arbre.bind("<Button-3>", clic_droit)
    arbre.bind("<<TreeviewSelect>>", afficher_details)
    arbre.bind("<Double-1>", lambda e: ajouter_au_bench() if arbre.identify_row(e.y) else None)
    arbre.bind("<Control-c>", copier_nom)
    arbre.bind("<Delete>", supprimer)

    # ===== Onglet 2 : Benchmark (évaluation des capacités de codage) =====
    page_b = ttk.Frame(onglets, padding=(px(4), px(10), px(4), px(4)))
    onglets.add(page_b, text="   " + T("onglet_bench") + "   ")

    intro = tk.Frame(page_b, background=C_CARTE, highlightthickness=1, highlightbackground=C_TRAIT,
                     padx=px(16), pady=px(12))
    intro.pack(fill="x")
    ttk.Label(intro, text=T("bench_titre"), style="CarteTitre.TLabel").pack(anchor="w")
    textes_intro = [
        ttk.Label(intro, text=T("bench_texte", n=len(EXERCICES), p=sum(points_max(e) for e in EXERCICES)),
                  style="Carte.TLabel", justify="left"),
        ttk.Label(intro, text=T("bench_attention"), style="CarteGris.TLabel", justify="left")]
    textes_intro[0].pack(anchor="w", pady=(px(4), 0))
    textes_intro[1].pack(anchor="w", pady=(px(6), 0))
    intro.bind("<Configure>", lambda e: [t.configure(wraplength=max(e.width - px(40), 200)) for t in textes_intro])

    cadre = ttk.LabelFrame(page_b, text=T("cadre_modeles"), padding=px(10))
    cadre.pack(fill="x", pady=(px(10), 0))
    champs = []
    for i in range(NB_CHAMPS):
        ligne, colonne = i % 4, (i // 4) * 2
        ttk.Label(cadre, text=T("champ_modele", n=i + 1)).grid(
            row=ligne, column=colonne, sticky="w", padx=(px(4) if colonne == 0 else px(18), px(6)), pady=px(3))
        c = ttk.Combobox(cadre, values=[])
        c.grid(row=ligne, column=colonne + 1, sticky="we", pady=px(3))
        champs.append(c)
    cadre.columnconfigure(1, weight=1)
    cadre.columnconfigure(3, weight=1)
    for c, valeur in zip(champs, garde.get("champs", [])):
        c.set(valeur)

    options = ttk.Frame(page_b)
    options.pack(fill="x", pady=px(8))
    var_reflexion = tk.BooleanVar(value=garde.get("reflexion", True))
    ttk.Checkbutton(options, text=T("reflexion"), variable=var_reflexion).pack(side="left")
    ttk.Button(options, text=T("vider"), command=lambda: [c.set("") for c in champs]).pack(side="right")
    ttk.Button(options, text=T("bench_selection"), command=lambda: ajouter_au_bench()).pack(side="right", padx=px(6))

    actions = ttk.Frame(page_b)
    actions.pack(fill="x", pady=(px(4), 0))
    b_lancer = ttk.Button(actions, text=T("lancer"), style="Accent.TButton", command=lambda: lancer())
    b_lancer.pack(side="left")
    b_arret = ttk.Button(actions, text=T("arreter"), style="Danger.TButton", command=lambda: arreter())
    b_arret.pack(side="left", padx=px(6))
    b_arret.state(["disabled"])
    barre_test = ttk.Progressbar(actions, length=px(200), mode="determinate", maximum=1)
    barre_test.pack(side="left", padx=(px(10), px(6)))
    texte_test = ttk.Label(actions, text="", style="Gris.TLabel")
    texte_test.pack(side="left")
    ttk.Button(actions, text=T("pdf"), command=lambda: export_pdf()).pack(side="right")
    ttk.Button(actions, text=T("ouvrir_dossier"), command=lambda: ouvrir(DOSSIER)).pack(side="right", padx=px(6))

    # ----- Journal (commun aux deux onglets) -----
    tete_journal = ttk.Frame(cadre_journal)
    tete_journal.pack(fill="x", pady=(px(4), px(3)))
    ttk.Label(tete_journal, text=T("journal_titre"), style="Gras.TLabel").pack(side="left")
    ttk.Button(tete_journal, text=T("journal_effacer"), style="Petit.TButton",
               command=lambda: journal.delete("1.0", "end")).pack(side="right")
    journal = scrolledtext.ScrolledText(cadre_journal, font=(MONO, 9), height=8, background=C_JOURNAL,
                                        foreground=C_JOURNAL_TEXTE, insertbackground=C_JOURNAL_TEXTE,
                                        relief="flat", borderwidth=0, padx=px(8), pady=px(6))
    journal.pack(fill="both", expand=True)
    if garde.get("journal"):
        journal.insert("end", garde["journal"] + "\n")
        journal.see("end")

    # ----- Barre de menus -----
    menus = tk.Menu(racine)
    m_fichier = tk.Menu(menus, tearoff=0)
    m_fichier.add_command(label=T("m_importer"), command=importer)
    m_fichier.add_command(label=T("gm_btn_exporter"), command=exporter_zip)
    m_fichier.add_separator()
    m_fichier.add_command(label=T("m_ouvrir_modeles"), command=ouvrir_dossier_modeles)
    m_fichier.add_command(label=T("ouvrir_dossier"), command=lambda: ouvrir(DOSSIER))
    m_fichier.add_separator()
    m_fichier.add_command(label=T("quitter_t"), command=fermer, accelerator="Alt+F4")
    menus.add_cascade(label=T("m_fichier"), menu=m_fichier)

    m_modeles = tk.Menu(menus, tearoff=0)
    m_modeles.add_command(label=T("m_telecharger"), command=telecharger, accelerator="Ctrl+N")
    m_modeles.add_command(label=T("m_maj"), command=mettre_a_jour)
    m_modeles.add_command(label=T("m_copier_sous"), command=copier_sous)
    m_modeles.add_command(label=T("m_supprimer"), command=supprimer)
    m_modeles.add_separator()
    m_modeles.add_command(label=T("m_decharger"), command=decharger_selection)
    m_modeles.add_command(label=T("m_modelfile"), command=voir_modelfile)
    m_modeles.add_command(label=T("gm_menu_copier"), command=copier_nom)
    m_modeles.add_separator()
    m_modeles.add_command(label=T("m_actualiser"), command=rafraichir, accelerator="F5")
    m_modeles.add_command(label=T("m_rechercher"), command=lambda: (onglets.select(page_m), recherche.focus_set()),
                          accelerator="Ctrl+F")
    m_modeles.add_command(label=T("gm_btn_dossier"), command=choisir_dossier)
    menus.add_cascade(label=T("m_modeles"), menu=m_modeles)

    m_bench = tk.Menu(menus, tearoff=0)
    m_bench.add_command(label=T("m_voir_bench"), command=lambda: onglets.select(page_b))
    m_bench.add_command(label=T("btn_bench"), command=ajouter_au_bench)
    m_bench.add_separator()
    m_bench.add_command(label=T("lancer"), command=lancer)
    m_bench.add_command(label=T("arreter"), command=arreter)
    m_bench.add_separator()
    m_bench.add_command(label=T("pdf"), command=export_pdf)
    menus.add_cascade(label=T("onglet_bench"), menu=m_bench)

    m_outils = tk.Menu(menus, tearoff=0)
    m_outils.add_command(label=T("reglages") + "...", command=ouvrir_reglages)
    menus.add_cascade(label=T("m_outils"), menu=m_outils)

    m_aide = tk.Menu(menus, tearoff=0)
    m_aide.add_command(label=T("m_apropos"), command=a_propos)
    menus.add_cascade(label=T("m_aide"), menu=m_aide)
    racine.config(menu=menus)

    racine.bind("<F5>", lambda _e: rafraichir())
    racine.bind("<Control-f>", lambda _e: (onglets.select(page_m), recherche.focus_set()))
    racine.bind("<Control-n>", lambda _e: telecharger())
    racine.protocol("WM_DELETE_WINDOW", fermer)

    # ----- Démarrage -----
    onglets.select(garde.get("onglet", 0))      # l'onglet « Modèles » s'ouvre en premier
    remplir_liste()
    if not garde.get("journal"):
        ecrire(T("msg_dossier", d=DOSSIER))

    def placer_separations():
        """Largeur de départ de la carte « Détails » et hauteur du journal."""
        try:
            corps.sashpos(0, corps.winfo_width() - px(300))
            panneaux.sashpos(0, panneaux.winfo_height() - px(135))
        except tk.TclError:
            pass
    racine.after(80, placer_separations)
    threading.Thread(target=surveiller, daemon=True).start()
    actualiser()
    racine.mainloop()

    # La fenêtre est fermée : on garde le journal si elle doit être reconstruite (changement de langue)
    return etat["relancer"], etat.get("garde", {})


def mode_executeur(fichier):
    """Utilisé par la version .exe : exécute le fichier de test d'un modèle puis s'arrête."""
    import runpy
    try:
        os.chdir(os.path.dirname(fichier))
        runpy.run_path(fichier, run_name="__main__")
    except BaseException:
        pass


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--executer":
        mode_executeur(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "--icone":
        # Fabrique le fichier icone.ico (utilisé par compiler.bat pour l'icône du .exe)
        print("Icone creee :", ecrire_ico(sys.argv[2] if len(sys.argv) >= 3 else os.path.join(DOSSIER, "icone.ico")))
    else:
        charger_reglages()
        relancer, garde = True, {}
        while relancer:                       # reconstruit la fenêtre si la langue change
            relancer, garde = fenetre(garde)
