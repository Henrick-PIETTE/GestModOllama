@echo off
rem ============================================================
rem  Compile comparer_hardcode.py en comparer_hardcode.exe
rem  A lancer par double-clic, dans le dossier du programme.
rem ============================================================
cd /d "%~dp0"

echo Installation / mise a jour de PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo.
    echo ERREUR : Python ou pip introuvable. Installez Python depuis python.org
    pause
    exit /b 1
)

echo.
echo Creation de l'icone du programme (icone.ico)...
python comparer_hardcode.py --icone icone.ico
if errorlevel 1 (
    echo.
    echo ERREUR pendant la creation de l'icone.
    pause
    exit /b 1
)

echo.
echo Compilation en cours (1 a 2 minutes)...
python -m PyInstaller --onefile --noconsole --clean --icon icone.ico --name comparer_hardcode comparer_hardcode.py
if errorlevel 1 (
    echo.
    echo ERREUR pendant la compilation.
    pause
    exit /b 1
)

copy /y "dist\comparer_hardcode.exe" "comparer_hardcode.exe" >nul
echo.
echo Termine : comparer_hardcode.exe est dans ce dossier.
echo Vous pouvez supprimer les dossiers build et dist ainsi que le fichier .spec
echo (gardez icone.ico : il sert a la prochaine compilation, il est recree a chaque fois).
pause
