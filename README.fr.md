# 🐧 kidcode-fedora

**Un tableau de bord parental + une aventure de code hors-ligne pour enfants, pour Linux (Fedora d'abord).**

*[🇬🇧 Read in English](README.md)*

`kidcode-fedora` transforme un vieux PC Linux en un ordinateur **console-first** sûr que tes
enfants *possèdent* — où ils apprennent les vraies commandes et codent leurs propres jeux —
pendant que tu gardes une main légère sur le temps d'écran depuis un tableau de bord web local.

Trois parties :

| Partie | Pour | Rôle |
|--------|------|------|
| 🖥️ **Tableau de bord** | Parents | Une petite page web locale (127.0.0.1) pour régler les **quotas de temps**, **verrouiller un PC** (« privé d'ordi jusqu'à nouvel ordre »), voir les **logs d'activité** et gérer les machines — le tout en SSH. Tourne sous **Linux & Windows**. |
| 📘 **Guides** | Enfants | Un guide de code **imprimable et hors-ligne** (FR & EN) — les bases Linux, puis coder Snake, une démo plasma, de la musique, un casse-brique, Lode Runner… en Python, pas à pas. |
| 🛡️ **Agent** | Chaque PC enfant | De petits scripts qui appliquent le quota (avec un écran de verrouillage clair) et, en option, verrouillent la machine en mode console + liste blanche. |

> ⚠️ **Conçu pour un usage familial/parental autorisé, sur tes propres machines.** Il utilise SSH
> avec le mot de passe root que tu définis. Garde `machines.conf` privé (il est git-ignoré).

---

## ✨ Fonctions

- ⏱️ **Quotas de temps** — plage horaire + minutes/jour, appliqués chaque minute ; la session se
  ferme quand le temps est écoulé et **ne peut pas être rouverte** avant le lendemain (verrou PAM au login).
- 🔒 **Verrou en un clic** — « privé d'ordi jusqu'à nouvel ordre » : l'écran de connexion affiche
  un message clair **VERROUILLÉ** au lieu d'une erreur de mot de passe énigmatique.
- 🖥️ **Écran de verrouillage kid-friendly** — heure actuelle, heures autorisées, **compte à rebours**
  jusqu'à la prochaine session et **jauge de temps restant**, directement sur l'écran GDM.
- 📊 **Logs d'activité** — sessions de connexion, commandes lancées (accounting de process) et temps par appli.
- ⚙️ **Page Réglages** — ajouter/modifier/supprimer des machines (IP, compte, mot de passe root)
  depuis le navigateur ; les mots de passe sont stockés en local (chmod 600) et **jamais envoyés au
  navigateur ni committés**.
- 🔐 **Config chiffrée** — au **premier démarrage**, le tableau de bord demande un **mot de passe
  maître** et chiffre tes machines aussitôt (AES + PBKDF2 via `cryptography`) ; il le redemande une
  fois par session pour déverrouiller. **Export / import** du fichier chiffré pour migrer vers un
  autre PC, et **rotation ou retrait** du mot de passe maître depuis la page Réglages.
- 🌐 **Suit les changements d'IP (DHCP)** — donne à chaque PC un **nom mDNS/DNS** (ex. `salon.local`) :
  le tableau de bord le joint par son nom même si l'IP change ; un bouton **🔄 Résoudre** met à jour
  l'IP stockée. L'agent publie le nom via avahi.
- 📘 **Guide de code bilingue hors-ligne** — aucune connexion requise ; imprime et c'est parti.
- 🪟 **Tableau de bord multiplateforme** — Python pur + paramiko, tourne sous Linux et Windows.

---

## 🚀 Démarrage rapide — le tableau de bord (parents)

> 📘 Installation & lancement pas à pas (Linux **et** Windows) : **[docs/install.md](docs/install.md)**.

### Linux (Fedora et dérivés)

```bash
git clone https://github.com/delminator/kidcode-fedora.git
cd kidcode-fedora
./install/install.sh        # installe paramiko + la commande 'kidcode' + une entrée de menu
kidcode                     # démarre le tableau de bord et ouvre le navigateur
```

Pas de git ? Récupère-le avec `wget` :

```bash
wget -qO- https://github.com/delminator/kidcode-fedora/archive/refs/heads/main.tar.gz | tar xz
cd kidcode-fedora-main && ./install/install.sh
```

### Windows

```powershell
# téléchargement (PowerShell a curl/Invoke-WebRequest intégrés)
Invoke-WebRequest https://github.com/delminator/kidcode-fedora/archive/refs/heads/main.zip -OutFile kidcode.zip
Expand-Archive kidcode.zip -DestinationPath .
cd kidcode-fedora-main
powershell -ExecutionPolicy Bypass -File install\install.ps1   # installe paramiko + un raccourci Bureau
```

Puis double-clique **KidCode** sur le Bureau (ou lance `install\kidcode.bat`).
Le tableau de bord s'ouvre sur **http://127.0.0.1:8765**.

### Premier lancement

Ouvre le tableau de bord → **⚙️ Réglages** → ajoute chaque PC enfant (nom, IP, compte SSH admin,
mot de passe root). Voilà — tu peux régler les quotas, verrouiller et lire les logs.

---

## 🧒 Préparer un PC enfant (l'agent)

Sur chaque PC Linux de l'enfant (en root), une fois :

```bash
sudo ./agent/kid-timetrack.sh <login_enfant>     # quota + verrou au login + logs d'activité
# (option, plus strict) verrouillage console-first + liste blanche de paquets :
sudo ./agent/kid-lockdown.sh  <login_enfant>
```

`kid-timetrack.sh` installe un gardien chaque minute, un écran de verrouillage GDM clair, et
l'accounting de process — **sans rien verrouiller d'autre**. Voir [`docs/agent.md`](docs/agent.md).

Pour qu'un PC soit joignable depuis le tableau de bord, il lui faut SSH (root + mot de passe).
Sur un Fedora Workstation tout neuf :

```bash
sudo dnf install -y openssh-server && sudo systemctl enable --now sshd
sudo firewall-cmd --permanent --add-service=ssh && sudo firewall-cmd --reload
echo 'root:TON_MOT_DE_PASSE_ROOT' | sudo chpasswd
printf 'PermitRootLogin yes\nPasswordAuthentication yes\n' | sudo tee /etc/ssh/sshd_config.d/00-kidcode.conf
sudo systemctl restart sshd
```

---

## 📘 Le guide de code des enfants

Ouvre ou imprime ces fichiers (un par langue, **sans internet**) :

- [`guides/guide-fr.html`](guides/guide-fr.html) — 🇫🇷 français
- [`guides/guide-en.html`](guides/guide-en.html) — 🇬🇧 English

Ils couvrent : se connecter, la touche TAB, naviguer, installer des applis, écouter de la musique
et jouer en console, puis **coder** Snake, une démo plasma, de la musique avec des maths, un
casse-brique, Lode Runner et un générateur de grottes. Régénère-les (les deux langues) avec :

```bash
python3 guides/gen-tuto.py
```

---

## 🗂️ Structure du projet

```
kidcode-fedora/
├── dashboard/        # le tableau de bord parental (Python + paramiko)
│   ├── kid-admin.py
│   ├── machines.conf.example   # copier en machines.conf (git-ignoré) ou utiliser ⚙️ Réglages
│   └── requirements.txt
├── agent/            # scripts à lancer SUR chaque PC enfant
│   ├── kid-timetrack.sh        # quota + verrou au login + logs
│   └── kid-lockdown.sh         # verrouillage console-first (option)
├── guides/           # le guide de code imprimable
│   ├── guide-fr.html  guide-en.html
│   └── gen-tuto.py             # régénère les deux guides
├── install/          # installeurs + lanceurs (Linux & Windows)
└── docs/             # documentation (FR & EN)
```

## 🔐 Modèle de sécurité

- Le tableau de bord écoute **uniquement sur 127.0.0.1** — jamais exposé au réseau.
- Les **mots de passe** des machines vivent **uniquement dans `machines.conf`** (chmod 600),
  qui est **git-ignoré**. Ils ne sont jamais envoyés au navigateur. Tu peux en plus **chiffrer**
  le fichier avec un mot de passe maître depuis la page Réglages (→ `machines.conf.enc`,
  AES + PBKDF2-SHA256, 600k itérations).
- SSH utilise paramiko avec le mot de passe root que tu définis ; prévu pour **tes PC familiaux**.

## 🤝 Contribuer

PRs bienvenues ! Une bonne **première contribution** : les commentaires `#` dans les exemples de
code (`guides/gen-tuto.py`, `CODES`) sont en français — les traduire en anglais (ou une autre
langue) améliorerait encore le guide anglais.

## 🙏 Crédits

Conçu et développé avec l'aide de **Claude** (Anthropic).

## 📄 Licence

[GPLv3](LICENSE) © contributeurs. Fait avec ❤️ pour les enfants curieux et la communauté Fedora.
