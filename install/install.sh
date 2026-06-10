#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
#  kidcode-fedora — installeur Linux (Fedora et dérivés)
#  Installe paramiko, crée la commande « kidcode » et une entrée de menu.
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"     # racine du dépôt
echo "kidcode-fedora — installation (Linux)"
echo "  dépôt : $HERE"

# 1. Python 3
command -v python3 >/dev/null 2>&1 || {
  echo "❌ Python 3 requis.  sudo dnf install python3" >&2; exit 1; }

# 2. paramiko (SSH multiplateforme)
if ! python3 -c 'import paramiko' 2>/dev/null; then
  echo "→ installation de paramiko…"
  python3 -m pip install --user paramiko 2>/dev/null \
    || sudo dnf install -y python3-paramiko \
    || { echo "❌ impossible d'installer paramiko (pip/dnf)." >&2; exit 1; }
fi
echo "✓ paramiko prêt"

# 3. dossier de config (mots de passe) — privé
mkdir -p "$HOME/.config/kid-admin"; chmod 700 "$HOME/.config/kid-admin"

# 4. commande « kidcode »
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/kidcode" <<EOF
#!/usr/bin/env bash
exec python3 "$HERE/dashboard/kid-admin.py" --open "\$@"
EOF
chmod +x "$HOME/.local/bin/kidcode"
echo "✓ commande 'kidcode' installée dans ~/.local/bin"

# 5. entrée de menu (lanceur graphique)
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/kidcode.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=KidCode — tableau de bord parental
Comment=Temps d'écran, verrouillage et activité des PC enfants
Exec=$HOME/.local/bin/kidcode
Icon=applications-education
Terminal=false
Categories=Education;Settings;
EOF

echo
echo "✅ Installé."
echo "   Lance :  kidcode        (ou depuis le menu : « KidCode »)"
echo "   Le navigateur s'ouvre sur http://127.0.0.1:8765"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "   ⚠️  Ajoute ~/.local/bin à ton PATH (ex. dans ~/.bashrc) :"
     echo "       export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac
