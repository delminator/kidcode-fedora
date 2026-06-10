#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
#  zork-graphique.sh — débloque & installe les Zork GRAPHIQUES
#  (Zork Nemesis + Zork: Grand Inquisitor) via ScummVM, en plein écran (cage).
#
#  🎮 VERROU-JEU « gentil » : pour les débloquer, il faut d'abord avoir
#     TERMINÉ un Zork TEXTE (I, II ou III). Un adulte donne alors le mot de
#     passe du « Maître du Donjon ».
#
#  Côté ADULTE, une seule fois :
#    • définir le mot de passe :  echo "MONMOT" | sudo tee /etc/kidcode/zork-unlock
#      (défaut : XYZZY — le mot magique des vieux jeux d'aventure 😉)
#    • autoriser ScummVM (jeu graphique) dans la liste blanche du lockdown :
#      l'ajouter à /etc/kid-install-allowlist  (comme stellarium).
#  Côté ENFANT : lance « zork-graphique » après avoir fini un Zork texte.
# ─────────────────────────────────────────────────────────────────────────
set -uo pipefail
PASS=$(cat /etc/kidcode/zork-unlock 2>/dev/null || echo "XYZZY")

cat <<'EOF'
+----------------------------------------------------------+
|     PORTE DU GRAND EMPIRE SOUTERRAIN                      |
+----------------------------------------------------------+
 Pour installer les Zork GRAPHIQUES (Nemesis & Grand
 Inquisitor), tu dois d'abord avoir TERMINE un Zork TEXTE
 (Zork I, II ou III) dans frotz.

 Quand c'est fait, demande a un adulte le
 MOT DE PASSE DU MAITRE DU DONJON.
EOF
read -rp " Mot de passe : " try
if [ "$try" != "$PASS" ]; then
  echo
  echo " La porte reste close. Termine d'abord un Zork texte ! (ex : frotz zork1)"
  echo " Astuce : tape SCORE dans le jeu pour voir ta progression."
  exit 1
fi

echo
echo " *** La porte s'ouvre ! Installation de ScummVM... ***"
if ! command -v scummvm >/dev/null 2>&1; then
  if command -v pkg >/dev/null 2>&1; then pkg install scummvm
  elif command -v install-pkg >/dev/null 2>&1; then sudo install-pkg scummvm
  else sudo dnf install -y scummvm; fi
fi

if ! command -v scummvm >/dev/null 2>&1; then
  echo " !! ScummVM n'a pas pu etre installe (demande a un adulte de l'ajouter"
  echo "    a la liste blanche : il est graphique, comme stellarium)."
  exit 1
fi

mkdir -p "$HOME/Jeux/zork-nemesis" "$HOME/Jeux/zork-grand-inquisitor"
cat <<EOF

 ScummVM est installe. Pour jouer en plein ecran :

     cage -- scummvm

 Dans ScummVM : "Add Game" -> choisis le dossier du jeu.

 Il te faut les DONNEES des jeux (que la famille possede : CD / GOG) a copier
 dans :
   ~/Jeux/zork-nemesis            (Zork Nemesis : The Forbidden Lands)
   ~/Jeux/zork-grand-inquisitor   (Zork: Grand Inquisitor)
 ScummVM les reconnait tout seul (moteur "ZVision").

 Bravo, Maitre du Donjon ! 🏰
EOF
