# 🛡️ The agent — `kid-timetrack.sh` & `kid-lockdown.sh`

*(English first, [français plus bas](#-français))*

These scripts run **on each child PC** (as root). The dashboard talks to them over SSH.

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
