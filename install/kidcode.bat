@echo off
REM ───────────────────────────────────────────────────────────────────────
REM  kidcode-fedora — lanceur Windows
REM  Démarre le tableau de bord et ouvre le navigateur.
REM ───────────────────────────────────────────────────────────────────────
REM On préfère le lanceur 'py' (évite l'alias factice du Microsoft Store).
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0..\dashboard\kid-admin.py" --open %*
  goto :eof
)
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0..\dashboard\kid-admin.py" --open %*
  goto :eof
)
echo Python 3 introuvable. Installe-le : https://www.python.org/downloads/  ^(coche "Add python.exe to PATH"^)
echo ou lance d'abord : install\install.ps1
pause
