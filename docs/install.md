# 📥 Install & run / Installation & lancement

*(English first, [français plus bas](#-français))*

## Requirements

- **Python 3** (3.8+). The installers add the two Python libs automatically:
  `paramiko` (SSH) and `cryptography` (encrypted config).

---

## 🐧 Linux (Fedora & co.)

### Install

```bash
git clone https://github.com/delminator/kidcode-fedora.git
cd kidcode-fedora
./install/install.sh
```

No git? Use `wget`:

```bash
wget -qO- https://github.com/delminator/kidcode-fedora/archive/refs/heads/main.tar.gz | tar xz
cd kidcode-fedora-main && ./install/install.sh
```

`install.sh` installs `paramiko`/`cryptography`, creates the **`kidcode`** command in
`~/.local/bin`, and adds a **menu entry** ("KidCode"). If `kidcode` is not found, add
`~/.local/bin` to your `PATH`.

### Simple launch

```bash
kidcode
```

That's it — it starts the dashboard **and opens your browser** at <http://127.0.0.1:8765>.
Equivalent ways:

```bash
./install/kidcode                              # run from the repo, no install
python3 dashboard/kid-admin.py --open          # the raw command
```

---

## 🪟 Windows

### Install

Download and unzip (PowerShell has `curl`/`Invoke-WebRequest` built in):

```powershell
Invoke-WebRequest https://github.com/delminator/kidcode-fedora/archive/refs/heads/main.zip -OutFile kidcode.zip
Expand-Archive kidcode.zip -DestinationPath .
cd kidcode-fedora-main
powershell -ExecutionPolicy Bypass -File install\install.ps1
```

`install.ps1` installs `paramiko`/`cryptography` and creates a **KidCode** shortcut on your Desktop.
(If `python` is missing, install it from <https://www.python.org/downloads/> and tick
*"Add python.exe to PATH"*.)

### Simple launch

- **Double-click `KidCode`** on the Desktop, **or** run `install\kidcode.bat`.
- It starts the dashboard **and opens your browser** at <http://127.0.0.1:8765>.

Equivalent raw command:

```bat
python dashboard\kid-admin.py --open
```

---

## First run, unlock & options

- **First launch** asks for a **master password** and encrypts your machines list right away
  (you can choose *"Later"* to stay in plaintext, or *Import* an existing `machines.conf.enc`).
- **Next launches** ask that master password once to **unlock** (decrypt) for the session.
- Add/edit your PCs in **⚙️ Settings**. **Export/Import** the encrypted file to move to another PC.

Environment variables (optional):

| Variable | Default | Use |
|----------|---------|-----|
| `KIDCODE_PORT` | `8765` | change the local port |
| `KIDCODE_DIR`  | `~/.config/kid-admin` | where `machines.conf[.enc]` lives |
| `KIDCODE_OPEN` | – | set to `1` to open the browser (same as `--open`) |

> The dashboard listens only on `127.0.0.1` — it is never exposed to the network.

---

# 🇫🇷 Français

## Pré-requis

- **Python 3** (3.8+). Les installeurs ajoutent automatiquement les deux libs Python :
  `paramiko` (SSH) et `cryptography` (config chiffrée).

## 🐧 Linux (Fedora et dérivés)

### Installer

```bash
git clone https://github.com/delminator/kidcode-fedora.git
cd kidcode-fedora
./install/install.sh
```

Pas de git ? Avec `wget` :

```bash
wget -qO- https://github.com/delminator/kidcode-fedora/archive/refs/heads/main.tar.gz | tar xz
cd kidcode-fedora-main && ./install/install.sh
```

`install.sh` installe `paramiko`/`cryptography`, crée la commande **`kidcode`** dans
`~/.local/bin` et ajoute une **entrée de menu** (« KidCode »). Si `kidcode` est introuvable,
ajoute `~/.local/bin` à ton `PATH`.

### Lancement simple

```bash
kidcode
```

Voilà — ça démarre le tableau de bord **et ouvre ton navigateur** sur <http://127.0.0.1:8765>.
Variantes équivalentes :

```bash
./install/kidcode                              # depuis le dépôt, sans installation
python3 dashboard/kid-admin.py --open          # la commande brute
```

## 🪟 Windows

### Installer

Télécharge et décompresse (PowerShell a `curl`/`Invoke-WebRequest` intégrés) :

```powershell
Invoke-WebRequest https://github.com/delminator/kidcode-fedora/archive/refs/heads/main.zip -OutFile kidcode.zip
Expand-Archive kidcode.zip -DestinationPath .
cd kidcode-fedora-main
powershell -ExecutionPolicy Bypass -File install\install.ps1
```

`install.ps1` installe `paramiko`/`cryptography` et crée un raccourci **KidCode** sur le Bureau.
(Si `python` manque, installe-le depuis <https://www.python.org/downloads/> en cochant
*« Add python.exe to PATH »*.)

### Lancement simple

- **Double-clique `KidCode`** sur le Bureau, **ou** lance `install\kidcode.bat`.
- Ça démarre le tableau de bord **et ouvre ton navigateur** sur <http://127.0.0.1:8765>.

Commande brute équivalente :

```bat
python dashboard\kid-admin.py --open
```

## Premier lancement, déverrouillage & options

- **Au premier lancement**, un **mot de passe maître** est demandé et chiffre aussitôt ta liste de
  machines (tu peux choisir *« Plus tard »* pour rester en clair, ou *Importer* un
  `machines.conf.enc` existant).
- **Aux lancements suivants**, ce mot de passe est demandé une fois pour **déverrouiller**
  (déchiffrer) le temps de la session.
- Ajoute/modifie tes PC dans **⚙️ Réglages**. **Exporter/Importer** le fichier chiffré pour migrer
  vers un autre PC.

Variables d'environnement (optionnel) :

| Variable | Défaut | Rôle |
|----------|--------|------|
| `KIDCODE_PORT` | `8765` | changer le port local |
| `KIDCODE_DIR`  | `~/.config/kid-admin` | où vit `machines.conf[.enc]` |
| `KIDCODE_OPEN` | – | mettre `1` pour ouvrir le navigateur (= `--open`) |

> Le tableau de bord n'écoute que sur `127.0.0.1` — jamais exposé au réseau.
