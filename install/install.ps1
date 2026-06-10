# ─────────────────────────────────────────────────────────────────────────
#  kidcode-fedora — installeur Windows (PowerShell)
#  Installe paramiko + cryptography et crée un raccourci « KidCode » sur le Bureau.
#  Lancement :  powershell -ExecutionPolicy Bypass -File install\install.ps1
# ─────────────────────────────────────────────────────────────────────────
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $PSScriptRoot     # racine du dépôt
Write-Host "kidcode-fedora - installation (Windows)"
Write-Host "  depot : $here"

# 1. Trouver un VRAI Python 3 — en évitant l'alias factice du Microsoft Store
function Find-Python {
  # a) lanceur officiel 'py' (fourni par les installeurs python.org) — le plus fiable
  if (Get-Command py -ErrorAction SilentlyContinue) {
    try { & py -3 --version *> $null; if ($LASTEXITCODE -eq 0) { return @("py", "-3") } } catch {}
  }
  # b) 'python' s'il s'exécute vraiment ET n'est pas le stub WindowsApps du Store
  $p = Get-Command python -ErrorAction SilentlyContinue
  if ($p -and ($p.Source -notlike "*\WindowsApps\*")) {
    try { & python --version *> $null; if ($LASTEXITCODE -eq 0) { return @("python") } } catch {}
  }
  return $null
}

$PY = Find-Python
if (-not $PY) {
  Write-Host ""
  Write-Host "[X] Python 3 introuvable (ou seul l'alias Microsoft Store est present)." -ForegroundColor Red
  Write-Host "    Installe Python PUIS relance ce script :"
  Write-Host "      * https://www.python.org/downloads/   (COCHE 'Add python.exe to PATH')"
  Write-Host "      * ou en ligne de commande :   winget install -e --id Python.Python.3.12"
  Write-Host "    Astuce : si taper 'python' ouvre le Microsoft Store, desactive l'alias dans"
  Write-Host "      Parametres > Applications > Alias d'execution d'application > python.exe (OFF)."
  exit 1
}
$pyExe  = $PY[0]
$pyArgs = if ($PY.Count -gt 1) { $PY[1..($PY.Count - 1)] } else { @() }
Write-Host ("  python : " + ($PY -join " "))

# 2. dépendances Python (paramiko = SSH, cryptography = config chiffrée)
Write-Host "-> installation des dependances (paramiko, cryptography)..."
& $pyExe @pyArgs -m pip install --user --upgrade paramiko cryptography
if ($LASTEXITCODE -ne 0) {
  Write-Host "[!] Echec d'installation des dependances (pip). Verifie ta connexion." -ForegroundColor Yellow
  exit 1
}
Write-Host "OK dependances pretes"

# 3. dossier de config (mots de passe / config chiffrée)
$cfg = Join-Path $env:USERPROFILE ".config\kid-admin"
New-Item -ItemType Directory -Force -Path $cfg | Out-Null

# 4. raccourci Bureau -> kidcode.bat
$bat = Join-Path $here "install\kidcode.bat"
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop "KidCode.lnk"
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $bat
$s.WorkingDirectory = $here
$s.IconLocation = "shell32.dll,21"
$s.Description = "KidCode - tableau de bord parental"
$s.Save()

Write-Host ""
Write-Host "OK Installe."
Write-Host "   Double-clique 'KidCode' sur le Bureau (ou lance install\kidcode.bat)."
Write-Host "   Le navigateur s'ouvre sur http://127.0.0.1:8765"
