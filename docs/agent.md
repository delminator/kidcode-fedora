# 🛡️ The agent — `kid-timetrack.sh` & `kid-lockdown.sh`

*(English first, [français plus bas](#-français))*

These scripts run **on each child PC** (as root). The dashboard talks to them over SSH.

## Which Fedora edition for which mode?

There are **two ways** to set up a child PC — pick the matching Fedora install:

| Mode | Fedora edition to install | Agent | For |
|------|---------------------------|-------|-----|
| 🟢 **Monitoring (timetrack)** | **Fedora Workstation** (standard GNOME desktop) | `kid-timetrack.sh` | The kid keeps a normal desktop; you **watch activity and enforce screen-time** — a friendly GDM lock screen, quotas, logs. |
| 🔒 **Lockdown (console-only)** | **Fedora console-only** — Fedora **Server**, or the **Everything** net-install in *Minimal/Custom* (no GNOME) | `kid-lockdown.sh` | A **console-first** machine (no desktop): package allow-list, GUI browsers/desktops blocked. For older, command-line-curious kids. |

Both modes need **SSH reachable as root** (so the dashboard can manage them) and publish an
**mDNS id** (added by the agent) so the dashboard **auto-heals their IP** when DHCP changes it.

### A) Monitoring mode — Fedora Workstation (standard)

1. Install **Fedora Workstation** normally (GNOME, GDM). Create the child's account.
2. Make root reachable over SSH (once, at the keyboard):
   ```bash
   sudo dnf install -y openssh-server && sudo systemctl enable --now sshd
   sudo firewall-cmd --permanent --add-service=ssh && sudo firewall-cmd --reload
   echo 'root:YOUR_ROOT_PASSWORD' | sudo chpasswd
   printf 'PermitRootLogin yes\nPasswordAuthentication yes\n' | sudo tee /etc/ssh/sshd_config.d/00-kidcode.conf
   sudo systemctl restart sshd
   ```
3. Install the agent (copy this repo's `agent/` over, or via USB), then:
   ```bash
   sudo ./agent/kid-timetrack.sh <child_login>
   ```
4. Add the PC in the dashboard's **⚙️ Settings** (or let **🔎 Discover** find it).

### B) Lockdown mode — Fedora console-only

1. Install Fedora **without a desktop**: **Fedora Server**, or **Fedora Everything**
   (net-install) → *Software selection: Minimal / Custom*, no GNOME. Boot lands on a text console.
2. Enable root SSH the same way as step 2 above (sshd is usually already present on Server).
3. Install the agent:
   ```bash
   sudo ./agent/kid-lockdown.sh <child_login>
   ```
   This removes full sudo, restricts installs to an allow-list, blocks GUI browsers/desktops,
   and boots to the console. Graphical home-made apps still run with `cage -- ./app`.

> Already have an old agent without mDNS? Just run `sudo ./agent/enable-mdns.sh` to add
> IP self-healing without re-running the whole setup.

## `kid-timetrack.sh <child_login>` — screen-time + logs (no lockdown)

Installs, **without locking anything else down**:

1. **`kidtime` guardian** — a systemd timer that runs every minute and reads `/etc/kidtime.conf`
   (one line per child: `login hstart hend budget_minutes`). It closes the session when the child
   is out of the allowed hours or out of daily minutes.
2. **PAM login gate** (`/etc/pam.d/gdm-password`) — refuses to even *open* a session when time is
   up, and shows a clear message (current time, allowed hours, countdown, remaining-time bar, or
   **"LOCKED until further notice"**). Fail-open: root and unmanaged users are never blocked.
3. **GDM banner** — the same status, shown on the login screen *before* typing a password.
4. **Activity logs** — `psacct` (process accounting: `lastcomm`, `sa`, `ac`), session history
   (`last`), and time-per-app under `/var/lib/kidtime/apps/<login>.<date>`.

### `/etc/kidtime.conf` format

```
login  hstart  hend  budget_minutes
```

- `hstart == hend` → no hour limit. `budget = 0` → no daily limit.
- Example: `alice 8 20 60` → may log in 8:00–20:00, 60 min/day.
- **Lock convention**: `alice 23 1 0` = no allowed hour at all → "LOCKED until further notice".
  The dashboard's 🔒 button writes exactly this; **unlock** = set `0 0 0`.

You normally never edit this by hand — use the dashboard (Settings / time controls / lock button).

## `kid-lockdown.sh <child_login>` — optional console-first lockdown

Stricter: removes the desktop, boots to a console, restricts `sudo` to a vetted package
allow-list (`pkg install` wrapper), and blocks GUI browsers/desktops. Use it only if you want a
fully console-first machine for older, command-line-curious kids.

---

## 🇫🇷 Français

Ces scripts tournent **sur chaque PC enfant** (en root). Le tableau de bord leur parle en SSH.

### Quelle édition Fedora pour quel mode ?

Il y a **deux façons** de préparer un PC enfant — choisis l'install Fedora correspondante :

| Mode | Édition Fedora à installer | Agent | Pour |
|------|----------------------------|-------|------|
| 🟢 **Surveillance (timetrack)** | **Fedora Workstation** (bureau GNOME standard) | `kid-timetrack.sh` | L'enfant garde un bureau normal ; tu **surveilles l'activité et limites le temps d'écran** — écran de verrouillage GDM clair, quotas, logs. |
| 🔒 **Verrouillé (console seule)** | **Fedora console seule** — Fedora **Server**, ou l'install **Everything** en *Minimal/Custom* (sans GNOME) | `kid-lockdown.sh` | Machine **console-first** (pas de bureau) : liste blanche de paquets, navigateurs/bureaux GUI bloqués. Pour des enfants plus grands, curieux de la ligne de commande. |

Les deux modes ont besoin de **SSH joignable en root** (pour que le dashboard les gère) et publient
un **ID mDNS** (ajouté par l'agent) → le dashboard **auto-répare leur IP** quand le DHCP la change.

### A) Mode surveillance — Fedora Workstation (standard)

1. Installe **Fedora Workstation** normalement (GNOME, GDM). Crée le compte de l'enfant.
2. Rends le root joignable en SSH (une fois, au clavier) :
   ```bash
   sudo dnf install -y openssh-server && sudo systemctl enable --now sshd
   sudo firewall-cmd --permanent --add-service=ssh && sudo firewall-cmd --reload
   echo 'root:TON_MOT_DE_PASSE_ROOT' | sudo chpasswd
   printf 'PermitRootLogin yes\nPasswordAuthentication yes\n' | sudo tee /etc/ssh/sshd_config.d/00-kidcode.conf
   sudo systemctl restart sshd
   ```
3. Installe l'agent (copie le dossier `agent/` du dépôt, ou via clé USB), puis :
   ```bash
   sudo ./agent/kid-timetrack.sh <login_enfant>
   ```
4. Ajoute le PC dans **⚙️ Réglages** du dashboard (ou laisse **🔎 Découvrir** le trouver).

### B) Mode verrouillé — Fedora console seule

1. Installe Fedora **sans bureau** : **Fedora Server**, ou **Fedora Everything** (net-install)
   → *Sélection des logiciels : Minimal / Personnalisé*, sans GNOME. Le boot tombe sur une console texte.
2. Active le SSH root comme à l'étape 2 ci-dessus (sshd est souvent déjà présent sur Server).
3. Installe l'agent :
   ```bash
   sudo ./agent/kid-lockdown.sh <login_enfant>
   ```
   Ça retire le sudo complet, limite les installs à une liste blanche, bloque navigateurs/bureaux
   GUI, et démarre en console. Les applis maison graphiques tournent quand même avec `cage -- ./app`.

> Déjà un vieil agent sans mDNS ? Lance simplement `sudo ./agent/enable-mdns.sh` pour ajouter
> l'auto-réparation d'IP sans tout réinstaller.

### `kid-timetrack.sh <login_enfant>` — temps d'écran + logs (sans lockdown)

Installe, **sans rien verrouiller d'autre** :

1. **Gardien `kidtime`** — un timer systemd chaque minute qui lit `/etc/kidtime.conf`
   (une ligne par enfant : `login hdébut hfin budget_minutes`). Il ferme la session quand l'enfant
   est hors plage horaire ou hors quota de minutes.
2. **Verrou PAM au login** (`/etc/pam.d/gdm-password`) — refuse même d'*ouvrir* une session quand
   le temps est écoulé, avec un message clair (heure, heures autorisées, compte à rebours, jauge,
   ou **« VERROUILLÉ jusqu'à nouvel ordre »**). Fail-open : root et comptes non gérés jamais bloqués.
3. **Bannière GDM** — le même statut, affiché *avant* de taper le mot de passe.
4. **Logs d'activité** — `psacct` (commandes : `lastcomm`, `sa`, `ac`), historique des sessions
   (`last`) et temps par appli dans `/var/lib/kidtime/apps/<login>.<date>`.

### Format de `/etc/kidtime.conf`

```
login  hdébut  hfin  budget_minutes
```

- `hdébut == hfin` → pas de limite horaire. `budget = 0` → pas de limite quotidienne.
- Exemple : `alice 8 20 60` → connexion de 8h à 20h, 60 min/jour.
- **Convention de verrou** : `alice 23 1 0` = aucune heure autorisée → « VERROUILLÉ jusqu'à nouvel
  ordre ». Le bouton 🔒 du tableau de bord écrit exactement ça ; **déverrouiller** = mettre `0 0 0`.

En général on ne l'édite jamais à la main — on utilise le tableau de bord (Réglages / temps / verrou).

### `kid-lockdown.sh <login_enfant>` — verrouillage console-first (option)

Plus strict : retire le bureau, démarre en console, restreint `sudo` à une liste blanche de paquets
(wrapper `pkg install`) et bloque navigateurs/bureaux graphiques. À n'utiliser que si tu veux une
machine 100 % console pour des enfants plus grands, curieux de la ligne de commande.

### `kid-guard.sh <login_enfant>` — durcissement anti-sabotage (option)

À poser **après** `kid-timetrack.sh` quand l'enfant tente de désactiver l'agent (y compris via un
assistant IA). Il ajoute :

- un **watchdog « hydre »** (`kidtime-guard`) relancé par **trois voies indépendantes** —
  timer systemd (45 s), `path`-unit (sur modification de fichier) et **cron root** (1 min) — avec
  une copie de référence (`/var/lib/kidtime/pristine/`) restaurée à l'identique. Chaque passage
  ré-arme d'abord toutes les voies, donc une seule voie survivante fait repousser l'ensemble.
  Le watchdog tourne en priorité minimale (`Nice=19`, `idle` CPU/IO) : aucun pic de lag ;
- l'**immuabilité** (`chattr +i`) des binaires/units/cron, restaurés en moins de 45 s si on y touche ;
- un **avertissement destiné aux assistants IA** (`~/.claude/CLAUDE.md`, `~/CLAUDE.md`, `~/AGENTS.md`,
  `/etc/kidtime/NOTICE-TO-AI-AGENTS.txt`) qui rappelle que la machine appartient au parent et que
  désactiver le contrôle parental doit être **refusé** ;
- un **journal** (`/var/lib/kidtime/tamper.log`) et une **sanction** configurable
  (`/etc/kidtime/guard.conf`, `ON_TAMPER=warn|lock|terminate|lockpc`). En `lockpc`, toute tentative
  verrouille le poste et coupe la session ; le déverrouillage se fait **uniquement** depuis le
  tableau de bord parental (bouton 🔓, qui lève le verrou-sabotage immuable).

> ⚠️ **Limite** : si l'enfant conserve un accès **root/sudo**, aucun garde-fou logiciel n'est
> inviolable — root peut toujours, à la longue, tout retirer. `kid-guard.sh` **ralentit fortement**,
> **alerte** et **dissuade**, mais la seule étanchéité réelle est de retirer l'enfant du groupe
> `wheel`. À utiliser en conscience.

### `kidfw` — filtre web parental (liste blanche / liste noire)

Posé automatiquement par `kid-timetrack.sh` (binaire `/usr/local/bin/kidfw`), **désactivé par
défaut** (`MODE=off` → aucun changement réseau). Se pilote depuis le tableau de bord (carte
**🛡️ Pare-feu web**) : on choisit le mode, on liste des **domaines** (un par ligne, les
sous-domaines sont inclus), puis on applique à une classe ou à tous.

- **Mécanisme** : un résolveur DNS local (`dnsmasq` sur `127.0.0.1`) + une **redirection nftables**
  de tout le trafic DNS sortant (port 53) vers ce résolveur — donc impossible de contourner en
  changeant de serveur DNS. `resolv.conf`/`nsswitch` ne sont **pas** modifiés : tout est réversible
  en vidant les tables `nft kidfw*` et en arrêtant `dnsmasq` (c'est ce que fait `kidfw apply` en
  mode `off`).
- **Liste noire** (`blacklist`) : tout passe **sauf** les domaines listés (`address=/domaine/` →
  `0.0.0.0`). **Liste blanche** (`whitelist`) : tout est bloqué (`address=/#/`) **sauf** les domaines
  listés — plus les domaines système (maj Fedora, heure réseau) gardés automatiquement pour ne pas
  casser les mises à jour. L'accès admin (SSH/LAN/mDNS) reste toujours joignable.
- **Source de vérité** : `/etc/kidtime/firewall.conf` (`MODE`, `UPSTREAM`) + `/etc/kidtime/firewall.list`,
  copiés dans `pristine/` et rendus **immuables**. Le watchdog les restaure si l'enfant les édite et
  garantit l'enforcement (dnsmasq + nft) si un filtrage est actif ; la simple coupure d'un service
  est **ré-appliquée sans verrouiller** le PC (un DNS coupé ne donne aucun contournement).
- **Limite** : le filtrage par DNS n'arrête pas un navigateur qui force du **DNS-over-HTTPS** ; les
  PC enfants en mode console (cf. `kid-lockdown.sh`) n'en ont pas. Quad9 (`9.9.9.9`) est l'upstream
  par défaut (filtrage anti-malware côté résolveur en bonus).

Commandes locales : `kidfw status` (état), `kidfw set <mode>` puis `kidfw apply` (en root). En
usage normal, **tout passe par le tableau de bord**.
