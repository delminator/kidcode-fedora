# ─────────────────────────────────────────────────────────────────────────
#  kidcode-fedora — installeur Windows (PowerShell)
#  Installe paramiko et crée un raccourci « KidCode » sur le Bureau.
#  Lancement :  powershell -ExecutionPolicy Bypass -File install\install.ps1
# ─────────────────────────────────────────────────────────────────────────
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $PSScriptRoot     # racine du dépôt
Write-Host "kidcode-fedora - installation (Windows)"
Write-Host "  depot : $here"

# 1. Python 3
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
  Write-Error "Python 3 requis : https://www.python.org/downloads/ (coche 'Add python.exe to PATH')."
  exit 1
}

# 2. paramiko
python -c "import paramiko" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "-> installation de paramiko..."
  python -m pip install --user paramiko
}
Write-Host "OK paramiko pret"

# 3. dossier de config (mots de passe)
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
