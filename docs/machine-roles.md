# Rôles des machines enfants (timetrack vs lockdown)

Chaque enfant a **deux** machines, aux buts **opposés**. Il ne faut **jamais**
appliquer le mauvais agent sur une machine — c'est la bêtise du **2026‑07‑04**
(voir plus bas). Le rôle est matérialisé par le fichier **`/etc/kid-machine-role`**
(`timetrack` ou `lockdown`), écrit automatiquement par l'installeur.

## Les deux rôles

| Rôle | Script | Ce qu'il fait | Ce qu'il NE fait PAS |
|------|--------|---------------|----------------------|
| **timetrack** | `agent/kid-timetrack.sh` | Surveillance (logs sessions/commandes/temps par appli) + **quota de temps** + verrou PAM au login. Bureau + navigateurs **LIBRES**. | Ne touche ni sudo, ni la blacklist dnf, ni le boot target. |
| **lockdown** | `agent/kid-lockdown.sh` | Console-first (pas de DE/DM), sudo réduit, **navigateurs GUI interdits** (allowlist + blacklist dnf), **wrapper `cage` SANS réseau**, applis maison en plein écran. | — |

`kid-guard.sh` (watchdog anti-sabotage) se déploie sur **les deux** rôles.

## Inventaire (IP indicatives — DHCP dérive, se fier au rôle/hostname/mDNS)

| Enfant | Machine timetrack | Machine lockdown |
|--------|-------------------|------------------|
| Gustave (`nox`) | ~`192.168.1.10/.11` (`fedora`) | `192.168.1.47` |
| Léopoldine (`carmness`) | `192.168.1.19` (`fedora`) | `192.168.1.16` (ASUS) |

> ⚠️ Les IP bougent (DHCP). Utiliser le bouton **« 🔎 Vérifier IP ↔ PC »** du
> dashboard, et/ou les noms mDNS `<hostname>.local`. Le **rôle** est stable :
> `cat /etc/kid-machine-role`.

## Garde-fou anti‑erreur (depuis 2026‑07‑04)

- `kid-timetrack.sh` écrit `timetrack` dans `/etc/kid-machine-role`.
- `kid-lockdown.sh` **REFUSE de tourner** (exit 2) si le marqueur vaut `timetrack`,
  ou s'il détecte un install timetrack (`/usr/local/bin/kidtime-enforce`) sans marqueur.
  Pour passer outre (conversion volontaire) : retirer kid-timetrack puis relancer
  avec **`--force`**. En cas de succès il écrit `lockdown` dans le marqueur.

Ainsi, relancer `kid-lockdown.sh` par erreur sur `.19` (timetrack) s'arrête net
avec un message explicite, au lieu de casser Strudel et les MàJ.

## Piège Strudel « chrome verrouillé » (résolu 2026‑07‑04)

Symptôme : `strudel` ne se lance plus, « Chrome est verrouillé ».
Cause : un kiosque fermé salement laisse un **`SingletonLock` Chromium périmé**
dans `~/.strudel-kiosk/`. Aggravé par la **dérive DHCP du hostname**
(`fedora` ↔ `fedora.home`) : Chromium croit le profil « utilisé par un autre
ordinateur » et refuse de démarrer.

- **Réparation manuelle** : `rm -f ~/.strudel-kiosk/Singleton{Lock,Socket,Cookie}`
  (sûr : le profil n'est PAS surveillé par le watchdog kidtime).
- **Réparation permanente** : `games/strudel` retire désormais tout seul un verrou
  mort au démarrage (si plus aucun Chromium n'utilise le profil).

Rappel : `strudel` lance Chromium via le **vrai `/usr/bin/cage`** (avec réseau) ;
la restriction réseau vient du filtre DNS **`kidfw`** (liste blanche), qui autorise
déjà `strudel.cc` + `strudel.b-cdn.net` + `jsdelivr`/`unpkg`/`fonts`/`github`.
