# 🐧 kidcode-fedora

**A parental dashboard + offline coding adventure for kids, built for Linux (Fedora-first).**

*[🇫🇷 Lire en français](README.fr.md)*

`kidcode-fedora` turns a spare Linux PC into a safe, console-first computer your kids
*own* — where they learn real commands and code their own games — while you keep a light,
respectful hand on screen-time from a local web dashboard.

It comes in two halves:

| Part | For | What it does |
|------|-----|--------------|
| 🖥️ **Dashboard** | Parents | A tiny local web page (127.0.0.1) to set **screen-time quotas**, **lock a PC** ("locked until further notice"), see **activity logs**, and manage machines — all over SSH. Runs on **Linux & Windows**. |
| 📘 **Guides** | Kids | A printable, **offline** coding guide (FR & EN) — Linux basics, then building Snake, a plasma demo, music, Breakout, Lode Runner… in Python, step by step. |
| 🛡️ **Agent** | Each kid PC | Small scripts that enforce the time quota (with a friendly lock screen) and optionally lock the machine down to a console-first allow-list. |

> ⚠️ **Built for authorized family/parental use on your own machines.** It uses SSH with the
> root password you set. Keep `machines.conf` private (it is git-ignored).

---

## ✨ Features

- ⏱️ **Screen-time quotas** — allowed hours + minutes/day, enforced every minute; the session
  closes when time is up and **can't be reopened** until tomorrow (PAM login gate).
- 🔒 **One-click lock** — "locked until further notice": the kid's login screen shows a clear
  **VERROUILLÉ / LOCKED** message instead of a cryptic password error.
- 🖥️ **Kid-friendly lock screen** — current time, allowed hours, a **countdown** to the next
  session and a **remaining-time bar**, shown right on the GDM login screen.
- 📊 **Activity logging** — login sessions, the commands they ran (process accounting), and
  time-per-app.
- ⚙️ **Settings page** — add/edit/remove machines (IP, account, root password) from the browser;
  passwords are stored locally (chmod 600) and **never sent to the browser or committed**.
- 🔐 **Encrypted config** — on **first run** the dashboard asks for a **master password** and
  encrypts your machines immediately (AES + PBKDF2 via `cryptography`); it asks for it once per
  session to unlock. **Export / import** the encrypted file to move your setup to another PC, and
  **rotate or remove** the master password from the Settings page.
- 🩹 **Self-healing IPs (DHCP-proof)** — each agent advertises a **stable mDNS id**; when a PC
  becomes unreachable because its DHCP address changed, the dashboard **re-locates it by id and
  updates the IP automatically** — no manual fix. Discovery and a 🔄 Resolve button are there too.
- 📘 **Bilingual offline coding guide** — no internet needed; print it and go.
- 🪟 **Cross-platform dashboard** — pure-Python + paramiko, runs on Linux and Windows.

---

## 🚀 Quick start — the dashboard (parents)

> 📘 Full step-by-step install & launch (Linux **and** Windows): **[docs/install.md](docs/install.md)**.

### Linux (Fedora & co.)

```bash
git clone https://github.com/delminator/kidcode-fedora.git
cd kidcode-fedora
./install/install.sh        # installs paramiko + a 'kidcode' command + a menu entry
kidcode                     # starts the dashboard and opens your browser
```

No git? Grab it with `wget`:

```bash
wget -qO- https://github.com/delminator/kidcode-fedora/archive/refs/heads/main.tar.gz | tar xz
cd kidcode-fedora-main && ./install/install.sh
```

### Windows

**Easiest — nothing to install:** download **`KidCode.exe`** from the
[latest Release](https://github.com/delminator/kidcode-fedora/releases) and double-click it.
Python, `paramiko` and `cryptography` are **bundled inside** — no Python setup needed.
It starts the dashboard and opens your browser at **http://127.0.0.1:8765**.

<details><summary><b>From source</b> (if you prefer / for the guides & agent scripts)</summary>

```powershell
# needs Python 3 first:  winget install -e --id Python.Python.3.12
Invoke-WebRequest https://github.com/delminator/kidcode-fedora/archive/refs/heads/main.zip -OutFile kidcode.zip
Expand-Archive kidcode.zip -DestinationPath .
cd kidcode-fedora-main
powershell -ExecutionPolicy Bypass -File install\install.ps1   # installs deps + a Desktop shortcut
```

Then double-click **KidCode** on the Desktop (or run `install\kidcode.bat`).
</details>

> 💡 Already have `wget` on Windows? `wget https://github.com/delminator/kidcode-fedora/archive/refs/heads/main.zip -O kidcode.zip` works too.

### First run

Open the dashboard → **⚙️ Settings** → add each child PC (name, IP, SSH admin account, root
password). That's it — you can now set quotas, lock, and read logs.

---

## 🧒 Set up a child PC (the agent)

Pick the Fedora edition that matches the mode (full guide: **[docs/agent.md](docs/agent.md)**):

- 🟢 **Monitoring** → install **Fedora Workstation** (standard GNOME), then
  `sudo ./agent/kid-timetrack.sh <child_login>` — screen-time + login gate + activity logs.
- 🔒 **Lockdown** → install **Fedora console-only** (Server / minimal), then
  `sudo ./agent/kid-lockdown.sh <child_login>` — console-first with a package allow-list.

Both publish an mDNS id so the dashboard **self-heals their IP** on DHCP changes
(retrofit an old agent with `sudo ./agent/enable-mdns.sh`).

`kid-timetrack.sh` installs a per-minute guardian, a friendly GDM lock screen, and process
accounting — **without locking anything else down**. See [`docs/agent.md`](docs/agent.md).

To reach a PC from the dashboard, it needs SSH (root + password). On a fresh Fedora Workstation:

```bash
sudo dnf install -y openssh-server && sudo systemctl enable --now sshd
sudo firewall-cmd --permanent --add-service=ssh && sudo firewall-cmd --reload
echo 'root:YOUR_ROOT_PASSWORD' | sudo chpasswd
printf 'PermitRootLogin yes\nPasswordAuthentication yes\n' | sudo tee /etc/ssh/sshd_config.d/00-kidcode.conf
sudo systemctl restart sshd
```

---

## 📘 The kids' coding guide

Open or print these (one per language, **no internet required**):

- [`guides/guide-fr.html`](guides/guide-fr.html) — 🇫🇷 français
- [`guides/guide-en.html`](guides/guide-en.html) — 🇬🇧 English

They cover: logging in, the TAB key, navigating, installing apps, playing music & console games,
then **coding** Snake, a plasma demo, music with maths, Breakout, Lode Runner, and a cave generator.
Regenerate them (both languages) with:

```bash
python3 guides/gen-tuto.py
```

---

## 🗂️ Project layout

```
kidcode-fedora/
├── dashboard/        # the parental web dashboard (Python + paramiko)
│   ├── kid-admin.py
│   ├── machines.conf.example   # copy to machines.conf (git-ignored) or use ⚙️ Settings
│   └── requirements.txt
├── agent/            # scripts that run ON each child PC
│   ├── kid-timetrack.sh        # screen-time quota + login gate + activity logs
│   └── kid-lockdown.sh         # optional console-first lockdown
├── guides/           # the printable kids coding guide
│   ├── guide-fr.html  guide-en.html
│   └── gen-tuto.py             # regenerates both guides
├── install/          # installers + launchers (Linux & Windows)
└── docs/             # documentation (FR & EN)
```

## 🔐 Security model

- The dashboard listens **only on 127.0.0.1** — never exposed to the network.
- Machine **passwords live only in `machines.conf`** (chmod 600), which is **git-ignored**.
  They are never sent to the browser. You can additionally **encrypt** the file with a master
  password from the Settings page (→ `machines.conf.enc`, AES + PBKDF2-SHA256, 600k iterations).
- SSH uses paramiko with the root password you set; intended for **your own family PCs**.

## 🤝 Contributing

PRs welcome! A great **good first issue**: the `#` comments inside the code samples
(`guides/gen-tuto.py`, `CODES`) are in French — translating them to English (or another
language) would make the English guide even better.

## 🙏 Credits

Designed by Delminator
built with the help of **Claude** (Anthropic) on the client/helper part.

## 📄 License

[GPLv3](LICENSE) © contributors. Made with ❤️ for curious kids and the Fedora community.
