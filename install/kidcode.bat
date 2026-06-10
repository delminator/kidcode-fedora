@echo off
REM ───────────────────────────────────────────────────────────────────────
REM  kidcode-fedora — lanceur Windows
REM  Démarre le tableau de bord et ouvre le navigateur.
REM ───────────────────────────────────────────────────────────────────────
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 requis : https://www.python.org/downloads/  ^(coche "Add to PATH"^)
  pause
  exit /b 1
)
python "%~dp0..\dashboard\kid-admin.py" --open %*
