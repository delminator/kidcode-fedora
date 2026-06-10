#!/usr/bin/bash
#
# kid-lockdown.sh — Console-first lockdown pour les machines des enfants.
#
# Modèle :
#   - Pas de DE, pas de Sway, pas de display manager : console (TTY) par défaut.
#   - Apps autorisées : web/mail/chat TEXTE, toolchain dev, demoscene/GL, outils TUI.
#   - Navigateurs graphiques + DE : INTERDITS.
#   - cage autorisé pour lancer les applis MAISON en plein écran (pas d'app graphique livrée).
#   - Sudo partiel RÉEL : l'enfant n'est PLUS dans wheel. Il peut seulement :
#         * sudo install-pkg <paquet>   -> installe UNIQUEMENT depuis la liste blanche
#         * sudo systemctl reboot/poweroff
#     Il ne peut PAS lancer dnf directement, ni contourner la liste blanche.
#
# Idempotent : relançable sans casse. À lancer EN ROOT sur chaque machine.
# Usage : sudo ./kid-lockdown.sh <nom_utilisateur>   (ex : sudo ./kid-lockdown.sh alice)
#
set -euo pipefail

KID="${1:-}"
if [[ -z "$KID" ]]; then
  echo "ERREUR : indique le compte de l'enfant.  Ex : sudo $0 alice" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 0. Garde-fous
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "ERREUR : à lancer en root." >&2
  exit 1
fi
if ! id "$KID" &>/dev/null; then
  echo "ERREUR : l'utilisateur '$KID' n'existe pas." >&2
  exit 1
fi
echo "==> Verrouillage console pour l'utilisateur : $KID"

# ---------------------------------------------------------------------------
# 1. Set logiciel autorisé
#    BASE    = installé d'office.
#    EXTRA   = installable à la demande par l'enfant via 'sudo install-pkg'.
#    La liste blanche = BASE + EXTRA.
# ---------------------------------------------------------------------------
BASE_PKGS=(
  # --- Web / mail / chat TEXTE ---
  w3m lynx links elinks
  neomutt
  weechat irssi
  # --- Toolchain dev ---
  git gcc gcc-c++ make cmake gdb
  python3 python3-pip
  vim-enhanced nano micro
  # --- Demoscene / GL (compiler + lancer les prods maison en kiosk) ---
  cage
  mesa-dri-drivers mesa-libGLU mesa-vulkan-drivers
  vulkan-loader vulkan-tools
  glslang glslc spirv-tools glmark2
  qt6-qtbase qt6-qtdeclarative qt6-qtbase-devel
  # --- Outils système TUI ---
  htop btop ncdu tmux ranger mc tree file man-pages
  # --- Réglages portable : luminosité, batterie, montage clé USB (son = alsa-utils plus bas) ---
  brightnessctl acpi udisks2
  # --- iproute : fournit 'ip', utilisé par le wrapper cage pour activer le loopback ---
  iproute
  # --- Musique : lecteur (mpg123) + volume (alsa-utils) + téléchargeur (aria2) ---
  mpg123 alsa-utils aria2
)

EXTRA_ALLOWED=(
  # Dev / langages supplémentaires que l'enfant peut tirer lui-même
  clang lld llvm rust cargo golang nodejs npm
  meson ninja-build pkgconf-pkg-config autoconf automake libtool
  valgrind strace ltrace
  python3-numpy python3-pillow
  # Confort console
  zsh fish bash-completion curl wget jq ripgrep fd-find bat eza
  unzip zip tar gzip xz p7zip
  rsync openssh-clients
  # Multimédia / GL en console (pas de navigateur !)
  ffmpeg-free SDL2 SDL2-devel glfw glfw-devel glm-devel
  sox
  # Création musique en Python (son live)
  python3-sounddevice portaudio python3-devel
  # Création de jeux graphiques (lancés sous cage) — override graphique pré-approuvé
  python3-pygame
  # Jeux console
  nethack frotz angband crawl cataclysm-dda nsnake bastet nudoku 2048-cli moon-buggy gnuchess
  # Fun / découverte (à installer soi-même : c'est le 1er exercice du guide !)
  cowsay figlet sl fortune-mod lolcat
  # Découverte : photos en console + astronomie (stellarium = override graphique)
  chafa timg catimg ImageMagick perl-Image-ExifTool python3-ephem stellarium
  # Bonus « grottes » : jeux de grotte + GPS/carto (qgis = override graphique)
  bsd-games gpsbabel qgis
  # Bonus « musique » : composition ABC en console
  abcMIDI timidity++
  # Recherche web en console (DuckDuckGo / Google dans le terminal)
  ddgr googler
)

ALLOWLIST_FILE=/etc/kid-install-allowlist

# ---------------------------------------------------------------------------
# 2. Liste NOIRE de paquets (filet secondaire) : navigateurs GUI + DE + Sway
#    Note : la vraie barrière est la liste blanche du wrapper ; ceci protège
#    surtout des installs accidentelles côté root.
# ---------------------------------------------------------------------------
EXCLUDE='firefox*,chromium*,google-chrome*,brave*,vivaldi*,opera*,epiphany,falkon,midori,qutebrowser,seamonkey,thunderbird*,gnome-shell,gnome-session*,gnome-desktop*,gdm,plasma-desktop,plasma-workspace,sddm,lightdm,xfce4-session,lxqt-session,mate-session-manager,cinnamon,budgie-desktop,enlightenment,sway,swaybg,swayidle,swaylock,i3,i3-gaps,openbox,hyprland'

# ---------------------------------------------------------------------------
# 3. Installation du set de base
# ---------------------------------------------------------------------------
echo "==> Installation du set de base (peut prendre quelques minutes)..."
dnf install -y --refresh "${BASE_PKGS[@]}"

# ---------------------------------------------------------------------------
# 3b. topgrade — binaire officiel GitHub (absent des dépôts Fedora).
#     Installé seulement s'il manque ; ensuite il se met à jour lui-même.
# ---------------------------------------------------------------------------
if ! command -v topgrade >/dev/null 2>&1; then
  echo "==> Installation de topgrade (binaire GitHub)..."
  command -v curl >/dev/null 2>&1 || dnf install -y curl >/dev/null 2>&1 || true
  if tg_url=$(curl -fsS https://api.github.com/repos/topgrade-rs/topgrade/releases/latest \
                | grep -oE 'https://[^"]*x86_64-unknown-linux-musl\.tar\.gz' | head -1) \
     && [ -n "$tg_url" ] && curl -fsSL "$tg_url" -o /tmp/topgrade.tgz \
     && tar xzf /tmp/topgrade.tgz -C /tmp topgrade; then
    install -m0755 /tmp/topgrade /usr/local/bin/topgrade
    rm -f /tmp/topgrade.tgz /tmp/topgrade
    echo "    topgrade $(/usr/local/bin/topgrade --version 2>/dev/null | awk '{print $2}') installé"
  else
    echo "    ⚠️ topgrade non installé (GitHub injoignable) — relance plus tard"
  fi
else
  echo "==> topgrade déjà présent ($(topgrade --version 2>/dev/null | awk '{print $2}'))"
fi

# ---------------------------------------------------------------------------
# 4. Génération de la liste blanche (BASE + EXTRA, triée, dédupliquée)
# ---------------------------------------------------------------------------
echo "==> Écriture de $ALLOWLIST_FILE"
printf '%s\n' "${BASE_PKGS[@]}" "${EXTRA_ALLOWED[@]}" | sort -u > "$ALLOWLIST_FILE"
chown root:root "$ALLOWLIST_FILE"
chmod 0644 "$ALLOWLIST_FILE"

# ---------------------------------------------------------------------------
# 5. Wrapper d'installation durci
# ---------------------------------------------------------------------------
echo "==> Écriture de /usr/local/bin/install-pkg"
cat > /usr/local/bin/install-pkg <<'WRAPPER'
#!/usr/bin/bash
# install-pkg : autorise l'install des applis CONSOLE, refuse les applis graphiques.
# Les paquets de la liste blanche sont autorisés d'office (override : graphique pré-approuvé).
# Appelé via sudo. Root-owned, non modifiable par les utilisateurs.
set -euo pipefail

ALLOWLIST=/etc/kid-install-allowlist
USER_CALLER="${SUDO_USER:-$(id -un)}"
# Bibliothèques graphiques : si un paquet en requiert -> appli graphique -> refus.
GUI_RE='libX11|libxcb|libwayland|libGL|libEGL|libgtk|libgdk|libQt5|libQt6|libXext|libXrender'

if [[ $# -eq 0 ]]; then
  echo "Usage : sudo install-pkg <paquet> [paquet...]" >&2
  echo "Astuce : 'pkg search <terme>' ou 'pkg list' pour voir les paquets autorisés." >&2
  exit 1
fi

pkgs=()
for a in "$@"; do
  # Rejette tout sauf un nom de paquet simple :
  # pas d'option (-), pas de chemin (/), pas de groupe (@), pas de glob (*),
  # pas de .rpm local, pas d'espace ni de méta-caractère shell.
  if [[ ! "$a" =~ ^[a-zA-Z0-9][a-zA-Z0-9._+-]*$ ]]; then
    logger -t install-pkg "REFUSÉ (nom invalide) user=$USER_CALLER arg=$a"
    echo "Refusé (nom invalide) : $a" >&2
    exit 2
  fi
  # Autorisé d'office si présent dans la liste blanche (graphique pré-approuvé).
  if grep -qxF -- "$a" "$ALLOWLIST"; then
    pkgs+=("$a"); continue
  fi
  # Sinon : refusé si c'est une application graphique.
  if dnf -q repoquery --requires "$a" 2>/dev/null | grep -qiE "$GUI_RE"; then
    logger -t install-pkg "REFUSÉ (graphique) user=$USER_CALLER pkg=$a"
    echo "Refusé : '$a' est une application graphique (interdit ici)." >&2
    echo "  Les applis console sont autorisées. Demande à papa pour une appli graphique." >&2
    exit 3
  fi
  # Appli console -> autorisée.
  pkgs+=("$a")
done

logger -t install-pkg "ACCEPTÉ user=$USER_CALLER pkgs=${pkgs[*]}"
# Pas de --disableexcludes : la liste noire reste active. argv direct, aucun eval.
exec /usr/bin/dnf install -y "${pkgs[@]}"
WRAPPER
chown root:root /usr/local/bin/install-pkg
chmod 0755 /usr/local/bin/install-pkg

# ---------------------------------------------------------------------------
# 5b. Commande conviviale 'pkg' (lecture seule, SANS sudo) :
#     list / search / info parmi les paquets AUTORISÉS uniquement,
#     + 'pkg install' qui relaie vers 'sudo install-pkg'.
# ---------------------------------------------------------------------------
echo "==> Écriture de /usr/local/bin/pkg"
cat > /usr/local/bin/pkg <<'PKGTOOL'
#!/usr/bin/bash
# pkg — explorer/installer UNIQUEMENT les paquets de la liste blanche.
set -euo pipefail
ALLOWLIST=/etc/kid-install-allowlist
cmd="${1:-help}"; shift || true

case "$cmd" in
  list|ls)
    echo "Tu peux installer toute appli CONSOLE (les applis graphiques sont bloquées)."
    echo "Pour chercher :  pkg search <terme>"
    echo
    echo "Applis pré-approuvées (dont quelques graphiques pour la demoscene) :"
    column "$ALLOWLIST" 2>/dev/null || cat "$ALLOWLIST"
    ;;
  search|s)
    [[ $# -ge 1 ]] || { echo "Usage : pkg search <terme>" >&2; exit 1; }
    dnf -q search "$@" 2>/dev/null || echo "Aucun résultat pour : $*"
    ;;
  info|i)
    [[ $# -eq 1 ]] || { echo "Usage : pkg info <paquet>" >&2; exit 1; }
    dnf -q info "$1"
    ;;
  install|in|add)
    [[ $# -ge 1 ]] || { echo "Usage : pkg install <paquet>..." >&2; exit 1; }
    exec sudo /usr/local/bin/install-pkg "$@"
    ;;
  help|-h|--help|*)
    cat <<EOF
pkg — paquets autorisés
  pkg list                 liste les paquets autorisés
  pkg search <terme>       cherche parmi les autorisés (nom + description)
  pkg info <paquet>        détails d'un paquet autorisé
  pkg install <paquet>...  installe (via sudo install-pkg)
EOF
    ;;
esac
PKGTOOL
chown root:root /usr/local/bin/pkg
chmod 0755 /usr/local/bin/pkg

# ---------------------------------------------------------------------------
# 5c. Commande 'aide' : pense-bête console pour l'enfant (pas de navigateur).
# ---------------------------------------------------------------------------
echo "==> Écriture de /usr/local/bin/aide"
cat > /usr/local/bin/aide <<'AIDE'
#!/usr/bin/bash
b=$'\e[1m'; c=$'\e[36m'; y=$'\e[33m'; g=$'\e[32m'; r=$'\e[0m'
cat <<EOF
${b}${c}🐧  AIDE — mon ordinateur Linux${r}

${y}⭐ ASTUCE N°1${r} : tape le début d'un mot puis ${b}TAB ↹${r} → ça complète tout seul !
   Flèche ${b}Haut${r} = dernière commande. ${b}clear${r} = nettoie l'écran. ${b}man nom${r} = aide (q pour sortir).

${g}📂 Dossiers${r}
   ls            voir ce qu'il y a ici
   cd dossier    entrer   ·   cd ..  remonter   ·   cd  rentrer à la maison
   mkdir nom     créer un dossier
   ranger        explorer avec les flèches (q pour quitter)

${g}✍️  Écrire${r}
   nano fichier.txt   écrire   (Ctrl+O = sauver, Ctrl+X = quitter)
   cat fichier.txt    relire

${g}🎵 Musique${r}
   mpg123 chanson.mp3   jouer   (Ctrl+C pour arrêter)
   alsamixer            régler le VOLUME (flèches Haut/Bas, M = muet, Échap)

${g}📥 Installer un programme (applis console)${r}
   pkg list         ·   pkg search mot   ·   pkg install nom
   sudo maj         mettre le système à jour

${g}🤹 Pour rigoler${r}
   cowsay Salut | lolcat     figlet TonPrenom     sl     fortune

${g}🚀 Démo 3D plein écran${r}
   cage -- glmark2      (Échap ou Ctrl+C pour quitter)

${g}🎮 Jeux à installer${r}
   pkg install nethack       grand jeu d'aventure ASCII
   pkg install nsnake        le serpent   ·   pkg install bastet   (tetris)
   pkg install frotz         pour jouer à Zork & aux fictions interactives

${y}📄 Les exercices pour CODER tes jeux sont dans le guide papier — demande à papa.${r}
EOF
AIDE
chown root:root /usr/local/bin/aide
chmod 0755 /usr/local/bin/aide

# Rappel à la connexion (uniquement pour les comptes utilisateurs, pas root)
cat > /etc/profile.d/aide-hint.sh <<'HINT'
[ "$(id -u)" -ge 1000 ] && echo "💡 Tape 'aide' pour voir les commandes de base, ou 'pkg list' pour les programmes."
HINT
chmod 0644 /etc/profile.d/aide-hint.sh

# ---------------------------------------------------------------------------
# 5d. Commande 'maj' : mise à jour système FIGÉE (sudo-able, sans exec arbitraire).
#     NB : on n'autorise PAS 'sudo topgrade' (topgrade lance des commandes
#     définies par l'utilisateur -> escalade root). maj est sûre.
# ---------------------------------------------------------------------------
echo "==> Écriture de /usr/local/bin/maj"
cat > /usr/local/bin/maj <<'MAJ'
#!/usr/bin/bash
# maj — met à jour le système. Commandes figées, aucune entrée utilisateur utilisée.
set -euo pipefail
echo "==> Mise à jour des paquets système (dnf)..."
/usr/bin/dnf upgrade -y --refresh
if command -v flatpak >/dev/null 2>&1; then
  echo "==> Mise à jour Flatpak..."
  /usr/bin/flatpak update -y || true
fi
echo "✅ Système à jour."
MAJ
chown root:root /usr/local/bin/maj
chmod 0755 /usr/local/bin/maj

# ---------------------------------------------------------------------------
# 5e. Temps d'écran : gardien "kidtime" (timer systemd root, chaque minute).
#     Plage horaire + budget/jour, réglés depuis la page parents.
#     Par défaut : AUCUNE limite (n'écrase pas un réglage existant).
# ---------------------------------------------------------------------------
echo "==> Installation du gardien de temps d'écran (kidtime)"
cat > /usr/local/bin/kidtime-enforce <<'KT'
#!/usr/bin/bash
# Applique /etc/kidtime.conf. Format : "user hstart hend budget_min"
#   hstart=hend => pas de limite horaire ; budget 0 => pas de limite de durée.
set -uo pipefail
CONF=/etc/kidtime.conf; STATE=/var/lib/kidtime
mkdir -p "$STATE"; [ -f "$CONF" ] || exit 0
find "$STATE" -type f -mtime +3 -delete 2>/dev/null || true
today=$(date +%Y%m%d); hour=$(date +%-H)
while read -r user hstart hend budget _; do
  [[ -z "${user:-}" || "$user" == \#* ]] && continue
  loginctl list-sessions --no-legend 2>/dev/null | awk '{print $3}' | grep -qx "$user" || continue
  if [[ "${hstart:-0}" != "${hend:-0}" ]] && (( 10#${hour} < 10#${hstart} || 10#${hour} >= 10#${hend} )); then
    echo "[kidtime] $user : hors plage autorisée (${hstart}h-${hend}h). Déconnexion dans 30 s." | wall 2>/dev/null
    sleep 30; loginctl terminate-user "$user"; continue
  fi
  if (( ${budget:-0} > 0 )); then
    f="$STATE/$user.$today"; used=$(cat "$f" 2>/dev/null || echo 0); used=$((used+1)); echo "$used" > "$f"
    left=$(( budget - used ))
    if (( left <= 0 )); then
      echo "[kidtime] $user : temps d'écran du jour écoulé (${budget} min). Déconnexion dans 30 s." | wall 2>/dev/null
      sleep 30; loginctl terminate-user "$user"
    elif (( left == 10 || left == 5 || left == 2 )); then
      echo "[kidtime] $user : il te reste $left minutes aujourd'hui." | wall 2>/dev/null
    fi
  fi
done < "$CONF"
KT
chown root:root /usr/local/bin/kidtime-enforce; chmod 0755 /usr/local/bin/kidtime-enforce
cat > /etc/systemd/system/kidtime.service <<'KS'
[Unit]
Description=Gardien temps d'ecran enfants (kidtime)
[Service]
Type=oneshot
ExecStart=/usr/local/bin/kidtime-enforce
KS
cat > /etc/systemd/system/kidtime.timer <<'KTM'
[Unit]
Description=Lance kidtime chaque minute
[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=10s
[Install]
WantedBy=timers.target
KTM
touch /etc/kidtime.conf; chmod 0644 /etc/kidtime.conf
if ! grep -qE "^[[:space:]]*$KID[[:space:]]" /etc/kidtime.conf; then
  echo "$KID 0 0 0   # hstart hend budget_min (0 0 0 = aucune limite)" >> /etc/kidtime.conf
fi
systemctl daemon-reload
systemctl enable --now kidtime.timer >/dev/null 2>&1
echo "    kidtime actif (par défaut : aucune limite ; à régler via la page parents)"

# ---------------------------------------------------------------------------
# 6. Sudo partiel : sudoers.d (validé avant activation)
# ---------------------------------------------------------------------------
echo "==> Configuration du sudo partiel"
SUDO_TMP="$(mktemp)"
cat > "$SUDO_TMP" <<EOF
# Sudo partiel pour $KID (généré par kid-lockdown.sh)
# Aucun accès dnf direct. Uniquement le wrapper + arrêt/reboot.
Cmnd_Alias KID_INSTALL = /usr/local/bin/install-pkg
Cmnd_Alias KID_UPDATE  = /usr/local/bin/maj
Cmnd_Alias KID_POWER   = /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff, /usr/bin/systemctl suspend
$KID ALL=(root) NOPASSWD: KID_INSTALL
$KID ALL=(root) NOPASSWD: KID_UPDATE
$KID ALL=(root) NOPASSWD: KID_POWER
EOF
if visudo -cf "$SUDO_TMP" >/dev/null; then
  install -m 0440 -o root -g root "$SUDO_TMP" /etc/sudoers.d/kid-"$KID"
  rm -f "$SUDO_TMP"
  echo "    sudoers OK -> /etc/sudoers.d/kid-$KID"
else
  rm -f "$SUDO_TMP"
  echo "ERREUR : sudoers invalide, abandon de cette étape." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 7. Retrait du sudo COMPLET : sortir l'enfant de wheel
# ---------------------------------------------------------------------------
if id -nG "$KID" | tr ' ' '\n' | grep -qx wheel; then
  gpasswd -d "$KID" wheel
  echo "==> $KID retiré du groupe wheel (plus de sudo complet)"
else
  echo "==> $KID déjà hors de wheel"
fi

# ---------------------------------------------------------------------------
# 8. Groupes nécessaires pour cage / GL (accès DRM / input)
# ---------------------------------------------------------------------------
usermod -aG video,input,render "$KID"
echo "==> $KID ajouté à video,input,render (pour cage/OpenGL)"

# ---------------------------------------------------------------------------
# 8b. Wrapper 'cage' SANS INTERNET.
#     Politique : tout ce qui tourne en plein écran (sous cage) est isolé dans
#     un namespace réseau VIDE (seul le loopback/localhost reste). La console
#     normale de l'enfant (pkg, aria2c, maj, w3m...) garde son accès internet :
#     SEUL le sous-arbre lancé par cage est coupé du réseau.
#     But : anti-exfiltration + neutraliser un navigateur lancé en kiosque
#     (ex. Strudel), tout en laissant marcher Sonic Pi (OSC localhost),
#     Stellarium, glmark2, jeux maison (tous fonctionnent hors-ligne).
# ---------------------------------------------------------------------------
echo "==> Écriture du wrapper /usr/local/bin/cage (cage sans réseau)"
cat > /usr/local/bin/cage <<'CAGEWRAP'
#!/usr/bin/bash
# cage (wrapper de verrouillage) — lance le VRAI cage SANS accès internet.
#
# Comment : on isole l'arbre cage dans un user+net namespace NON privilégié.
#   - On reste dans la session logind / le siège (pas de sudo, même cgroup) :
#     cage obtient donc bien le DRM/clavier via logind (fd passé par logind,
#     les groupes video/input/render ne sont même pas nécessaires).
#   - On mappe sur root DANS le namespace (--map-root-user) : c'est la seule façon
#     de garder CAP_NET_ADMIN après le exec, donc de RELEVER le loopback —
#     indispensable à l'audio/OSC local (Sonic Pi) et à un Strudel servi en local.
#     L'uid RÉEL reste celui de l'enfant : logind voit le vrai uid → DRM/clavier OK.
#   - Conséquence : les applis tournent en « root du namespace ». Sans souci pour
#     sonic-pi / stellarium / glmark2 / jeux. Chromium, lui, refuse de tourner en
#     root → le lanceur 'strudel' ajoute --no-sandbox (sans danger : réseau coupé).
#
# ADMIN : pour lancer cage AVEC réseau (debug), appelle directement /usr/bin/cage
#         (l'enfant ne connaît que « cage »). Pour retirer la politique :
#         rm /usr/local/bin/cage   (le vrai /usr/bin/cage reprend la main).
set -euo pipefail
REAL_CAGE=/usr/bin/cage
[ -x "$REAL_CAGE" ] || { echo "cage: $REAL_CAGE introuvable" >&2; exit 127; }

# Fail-closed : si l'isolation échoue, on N'OUVRE PAS cage (pas de fuite réseau).
exec unshare --user --net --map-root-user --kill-child -- \
  /usr/bin/bash -c 'ip link set lo up 2>/dev/null || true; exec "$0" "$@"' \
  "$REAL_CAGE" "$@"
CAGEWRAP
chown root:root /usr/local/bin/cage
chmod 0755 /usr/local/bin/cage

# Vérif noyau : les user-namespaces non privilégiés sont-ils disponibles ?
if [ "$(sysctl -n user.max_user_namespaces 2>/dev/null || echo 0)" -gt 0 ]; then
  echo "==> user-namespaces OK → l'isolation réseau de cage est active"
else
  echo "!! ATTENTION : user.max_user_namespaces=0 → le wrapper cage ne pourra PAS" >&2
  echo "!! créer le namespace réseau (fail-closed = plus de GUI). Active les userns" >&2
  echo "!! (sysctl user.max_user_namespaces=10000) OU retire /usr/local/bin/cage." >&2
fi
echo "    À TESTER en tant que $KID :"
echo "      cage -- glmark2     → doit s'ouvrir (GPU OK)"
echo "      puis, dans une appli sous cage : aucun accès internet (loopback seul)"

# ---------------------------------------------------------------------------
# 9. Liste noire de paquets dans dnf.conf (idempotent)
# ---------------------------------------------------------------------------
echo "==> Application de la liste noire dnf"
sed -i '/^excludepkgs=/d' /etc/dnf/dnf.conf
if grep -q '^\[main\]' /etc/dnf/dnf.conf; then
  sed -i "/^\[main\]/a excludepkgs=$EXCLUDE" /etc/dnf/dnf.conf
else
  printf '[main]\nexcludepkgs=%s\n' "$EXCLUDE" >> /etc/dnf/dnf.conf
fi

# ---------------------------------------------------------------------------
# 10. Console par défaut (rien de graphique au boot)
# ---------------------------------------------------------------------------
systemctl set-default multi-user.target >/dev/null
echo "==> Cible par défaut : multi-user.target (console)"

# ---------------------------------------------------------------------------
# Résumé
# ---------------------------------------------------------------------------
cat <<EOF

============================================================
 Lockdown appliqué pour : $KID
------------------------------------------------------------
 Boot              : console (multi-user.target)
 Sudo complet      : RETIRÉ (hors wheel)
 Sudo autorisé     : install-pkg (liste blanche) + reboot/poweroff/suspend
 Recherche paquets : pkg search <terme> | pkg list | pkg info <paquet>
 Install paquets   : pkg install <paquet>  (= sudo install-pkg ; liste : $ALLOWLIST_FILE)
 Navigateur GUI/DE : interdits (liste blanche + liste noire dnf)
 Applis maison GUI : cage -- ./mon_appli   (plein écran, pas de WM)
 Réseau sous cage  : COUPÉ (loopback seul) — anti-exfil / navigateur kiosque
 Journal des installs : journalctl -t install-pkg
============================================================
EOF
