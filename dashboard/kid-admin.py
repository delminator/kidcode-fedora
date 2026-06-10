#!/usr/bin/env python3
"""
kid-admin — Page web locale de gestion des PC enfants.

Fonctions :
  - Éditer la LISTE MAÎTRE des paquets autorisés (source de vérité unique).
  - La POUSSER vers un PC enfant ou vers tous (scp -> /etc/kid-install-allowlist).
  - Voir les tentatives d'installation de chaque enfant (journalctl -t install-pkg).
  - Documentation intégrée de l'usage côté enfant (commande `pkg`).

Sécurité :
  - Écoute UNIQUEMENT sur 127.0.0.1 (jamais exposé au réseau).
  - Les mots de passe SSH sont lus dans ~/.config/kid-admin/machines.conf (chmod 600),
    JAMAIS envoyés au navigateur ni écrits sur /data.

Lancement :  python3 /data/scripts/kid-admin.py   puis ouvrir http://127.0.0.1:8765
"""
import json
import os
import re
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    import paramiko
except ImportError:
    paramiko = None

try:
    import cryptography  # noqa: F401
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

HOST = "127.0.0.1"
PORT = int(os.environ.get("KIDCODE_PORT") or 8765)
# Dossier de config multiplateforme (Linux/Windows). Override : env KIDCODE_DIR.
CONFIG_DIR = Path(os.environ.get("KIDCODE_DIR") or (Path.home() / ".config" / "kid-admin"))
MACHINES_CONF = CONFIG_DIR / "machines.conf"
MASTER_LIST = CONFIG_DIR / "allowlist.txt"
REMOTE_PATH = "/etc/kid-install-allowlist"
PKG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._+-]*$")


# ── SSH via paramiko (multiplateforme, aucune dépendance sshpass) ──────────
def _ssh_client(m, timeout=8):
    if paramiko is None:
        raise RuntimeError("paramiko manquant — installez : pip install paramiko")
    # On essaie le nom mDNS/DNS d'abord (suit l'IP), puis la dernière IP connue.
    hosts = [h for h in (m.get("dns"), m.get("ip")) if h]
    if not hosts:
        raise RuntimeError("aucune adresse (IP ou nom mDNS/DNS)")
    last = None
    for h in hosts:
        try:
            cli = paramiko.SSHClient()
            cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # = ssh accept-new
            cli.connect(h, username=m["user"], password=m["pwd"],
                        timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
                        look_for_keys=False, allow_agent=False)
            return cli
        except paramiko.AuthenticationException:
            raise                       # mauvais mot de passe : inutile d'essayer l'autre
        except Exception as e:  # noqa  (injoignable sur ce host → on tente le suivant)
            last = e
    raise last


def _ssh_err(e):
    """Traduit une exception SSH en message lisible pour les parents."""
    s = str(e).lower()
    if paramiko and isinstance(e, paramiko.AuthenticationException):
        return "authentification refusée (mot de passe root ?)"
    if isinstance(e, socket.timeout) or "timed out" in s or "timeout" in s:
        return "timeout (PC éteint / injoignable ?)"
    for sig in ("unreachable", "no route", "refused", "not known",
                "unable to connect", "name or service", "no valid connections"):
        if sig in s:
            return "injoignable (PC éteint ou IP changée ?)"
    return str(e) or "erreur SSH"


def ssh_run(m, command, timeout=30, connect_timeout=8):
    """Exécute une commande distante. Retourne (code, stdout, stderr)."""
    cli = _ssh_client(m, connect_timeout)
    try:
        _in, out, err = cli.exec_command(command, timeout=timeout)
        so = out.read().decode("utf-8", "replace")
        se = err.read().decode("utf-8", "replace")
        rc = out.channel.recv_exit_status()
        return rc, so, se
    finally:
        cli.close()


def ssh_put_text(m, text, remote_path, connect_timeout=8):
    """Écrit du texte dans un fichier distant (via SFTP)."""
    cli = _ssh_client(m, connect_timeout)
    try:
        sftp = cli.open_sftp()
        try:
            with sftp.file(remote_path, "w") as f:
                f.write(text)
        finally:
            sftp.close()
    finally:
        cli.close()


# ── Coffre chiffré : machines.conf.enc protégé par un mot de passe maître ──
#    Au repos, IP + mots de passe sont chiffrés (Fernet/AES + PBKDF2-SHA256).
#    Le mot de passe maître n'est jamais stocké ; la clé dérivée vit en mémoire
#    le temps de la session (déverrouillage via la page).
ENC_PATH = CONFIG_DIR / "machines.conf.enc"
OPTOUT_PATH = CONFIG_DIR / ".plaintext-ok"     # marqueur : a refusé le chiffrement
_VAULT = {"key": None, "salt": None}


def _derive_key(password, salt):
    import base64
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def is_encrypted():
    return ENC_PATH.exists()


def is_locked():
    return is_encrypted() and _VAULT["key"] is None


def vault_state():
    enc = is_encrypted()
    # 1er démarrage : pas encore chiffré, crypto dispo, pas explicitement refusé
    setup_needed = _HAS_CRYPTO and not enc and not OPTOUT_PATH.exists()
    return {"encrypted": enc, "locked": is_locked(),
            "has_plain": MACHINES_CONF.exists(), "crypto": _HAS_CRYPTO,
            "setup_needed": setup_needed}


def skip_encryption():
    """L'utilisateur choisit de rester en clair : on ne le redemande plus."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    OPTOUT_PATH.touch()
    return {"ok": True}


def export_enc():
    """Renvoie les octets du fichier chiffré (pour sauvegarde / autre PC)."""
    return ENC_PATH.read_bytes() if is_encrypted() else None


def import_enc(b64data):
    """Importe un machines.conf.enc (depuis un autre PC) ; à déverrouiller ensuite."""
    import base64
    import binascii
    try:
        raw = base64.b64decode(b64data or "", validate=False)
    except (binascii.Error, ValueError):
        return {"ok": False, "msg": "fichier illisible"}
    if not raw or b"\n" not in raw:
        return {"ok": False, "msg": "ce n'est pas un fichier de config chiffré (.enc)"}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ENC_PATH.write_bytes(raw)
    try:
        os.chmod(ENC_PATH, 0o600)
    except OSError:
        pass
    lock_vault()
    return {"ok": True, "msg": "config importée — déverrouille-la avec son mot de passe maître"}


def unlock_vault(password):
    import base64
    from cryptography.fernet import Fernet, InvalidToken
    try:
        salt_b64, token = ENC_PATH.read_bytes().split(b"\n", 1)
        salt = base64.b64decode(salt_b64)
        key = _derive_key(password, salt)
        Fernet(key).decrypt(token)            # InvalidToken si mauvais mot de passe
        _VAULT["key"], _VAULT["salt"] = key, salt
        return {"ok": True}
    except InvalidToken:
        return {"ok": False, "msg": "mot de passe maître incorrect"}
    except Exception as e:  # noqa
        return {"ok": False, "msg": str(e)}


def lock_vault():
    _VAULT["key"] = _VAULT["salt"] = None
    return {"ok": True}


def _read_conf_text():
    if is_encrypted():
        if _VAULT["key"] is None:
            raise PermissionError("verrouillé")
        from cryptography.fernet import Fernet
        _, token = ENC_PATH.read_bytes().split(b"\n", 1)
        return Fernet(_VAULT["key"]).decrypt(token).decode("utf-8")
    return MACHINES_CONF.read_text() if MACHINES_CONF.exists() else ""


def _write_conf_text(text):
    if is_encrypted() or _VAULT["key"] is not None:
        import base64
        from cryptography.fernet import Fernet
        if _VAULT["key"] is None:
            raise PermissionError("verrouillé")
        token = Fernet(_VAULT["key"]).encrypt(text.encode("utf-8"))
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        ENC_PATH.write_bytes(base64.b64encode(_VAULT["salt"]) + b"\n" + token)
        try:
            os.chmod(ENC_PATH, 0o600)
        except OSError:
            pass
    else:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        MACHINES_CONF.write_text(text)
        try:
            os.chmod(MACHINES_CONF, 0o600)
        except OSError:
            pass


def enable_encryption(password):
    """Chiffre la config existante avec un mot de passe maître, puis efface le clair."""
    if not _HAS_CRYPTO:
        return {"ok": False, "msg": "module 'cryptography' manquant (pip install cryptography)"}
    if not password or len(password) < 4:
        return {"ok": False, "msg": "mot de passe maître trop court (4 caractères min)"}
    if is_encrypted():
        return {"ok": False, "msg": "déjà chiffré"}
    text = MACHINES_CONF.read_text() if MACHINES_CONF.exists() else ""
    _VAULT["salt"] = os.urandom(16)
    _VAULT["key"] = _derive_key(password, _VAULT["salt"])
    _write_conf_text(text)                    # crée le .enc
    try:
        MACHINES_CONF.unlink()                # efface le clair
    except OSError:
        pass
    return {"ok": True, "msg": "configuration chiffrée 🔐"}


def _decrypt_with(password):
    """Vérifie le mot de passe et renvoie le texte déchiffré (ou lève)."""
    import base64
    from cryptography.fernet import Fernet
    salt_b64, token = ENC_PATH.read_bytes().split(b"\n", 1)
    salt = base64.b64decode(salt_b64)
    key = _derive_key(password, salt)
    return Fernet(key).decrypt(token).decode("utf-8")


def change_master(old, new):
    """Change le mot de passe maître (re-chiffre avec un nouveau sel)."""
    from cryptography.fernet import InvalidToken
    if not is_encrypted():
        return {"ok": False, "msg": "la config n'est pas chiffrée"}
    if not new or len(new) < 4:
        return {"ok": False, "msg": "nouveau mot de passe trop court (4 caractères min)"}
    try:
        text = _decrypt_with(old)
    except InvalidToken:
        return {"ok": False, "msg": "ancien mot de passe incorrect"}
    except Exception as e:  # noqa
        return {"ok": False, "msg": str(e)}
    _VAULT["salt"] = os.urandom(16)
    _VAULT["key"] = _derive_key(new, _VAULT["salt"])
    _write_conf_text(text)
    return {"ok": True, "msg": "mot de passe maître changé 🔐"}


def remove_encryption(password):
    """Retire le chiffrement : revient à machines.conf en clair (chmod 600)."""
    from cryptography.fernet import InvalidToken
    if not is_encrypted():
        return {"ok": False, "msg": "la config n'est pas chiffrée"}
    try:
        text = _decrypt_with(password)
    except InvalidToken:
        return {"ok": False, "msg": "mot de passe maître incorrect"}
    except Exception as e:  # noqa
        return {"ok": False, "msg": str(e)}
    lock_vault()
    try:
        ENC_PATH.unlink()
    except OSError:
        pass
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MACHINES_CONF.write_text(text)
    try:
        os.chmod(MACHINES_CONF, 0o600)
    except OSError:
        pass
    return {"ok": True, "msg": "chiffrement retiré — config en clair (chmod 600)"}


def load_machines():
    machines = []
    try:
        text = _read_conf_text()
    except PermissionError:
        return machines                       # verrouillé : les routes gèrent le cas
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        name, ip, user, pwd = parts[0], parts[1], parts[2], parts[3]
        # 5e champ optionnel = compte de l'enfant (découplé du nom de machine,
        # utile quand 2 machines ont le même enfant). Défaut = nom de machine.
        account = parts[4] if len(parts) >= 5 and parts[4] else name
        # 6e champ optionnel = mode : "lockdown" (def.) ou "timetrack"
        mode = parts[5].lower() if len(parts) >= 6 and parts[5] else "lockdown"
        # 7e champ optionnel = nom mDNS/DNS (ex: salon.local) suivant l'IP
        dns = parts[6] if len(parts) >= 7 and parts[6] else ""
        machines.append({"name": name, "ip": ip, "user": user, "pwd": pwd,
                         "account": account, "mode": mode, "dns": dns})
    return machines


CONF_HEADER = (
    "# kidcode-fedora — machines (généré par la page Réglages).\n"
    "# Format : nom|ip|user|password[|compte][|mode]\n"
    "# Contient des MOTS DE PASSE — ne jamais committer (gitignore).\n")


def _clean(v, default=""):
    """Nettoie un champ : pas de | ni de saut de ligne (séparateurs du fichier)."""
    return str(v or default).replace("|", "").replace("\n", "").replace("\r", "").strip()


def _write_machines(machines):
    """Réécrit la config (clair ou chiffrée) à partir de la liste de dicts."""
    lines = [CONF_HEADER]
    for m in machines:
        lines.append("|".join([m["name"], m["ip"], m["user"], m["pwd"],
                               m.get("account", ""), m.get("mode", "timetrack"),
                               m.get("dns", "")]))
    _write_conf_text("\n".join(lines) + "\n")


def save_machine(d):
    """Ajoute ou met à jour une machine. Mot de passe vide = on garde l'ancien."""
    name = _clean(d.get("name"))
    orig = _clean(d.get("orig")) or name      # nom d'origine (pour renommer)
    ip = _clean(d.get("ip"))
    dns = _clean(d.get("dns"))
    user = _clean(d.get("user"), "root")
    account = _clean(d.get("account"))
    mode = _clean(d.get("mode"), "timetrack").lower()
    pwd = str(d.get("pwd") or "").replace("|", "").replace("\n", "").replace("\r", "")
    if not name or (not ip and not dns):
        return {"ok": False, "msg": "nom + (IP ou nom mDNS/DNS) obligatoires"}
    if mode not in ("timetrack", "lockdown"):
        mode = "timetrack"
    machines = load_machines()
    existing = next((m for m in machines if m["name"] == orig), None)
    if not pwd:                       # pas de nouveau mot de passe → garder l'ancien
        if existing and existing["pwd"]:
            pwd = existing["pwd"]
        else:
            return {"ok": False, "msg": "mot de passe requis pour une nouvelle machine"}
    # renommage vers un nom déjà utilisé par une AUTRE machine → refus
    if name != orig and any(m["name"] == name for m in machines):
        return {"ok": False, "msg": f"le nom « {name} » existe déjà"}
    entry = {"name": name, "ip": ip, "user": user, "pwd": pwd,
             "account": account, "mode": mode, "dns": dns}
    # on retire l'ancienne entrée (ancien nom) et l'éventuel homonyme, puis on ajoute
    machines = [m for m in machines if m["name"] not in (orig, name)]
    machines.append(entry)
    _write_machines(machines)
    return {"ok": True, "msg": ("machine renommée" if name != orig else "machine enregistrée")}


def delete_machine(name):
    name = _clean(name)
    machines = [m for m in load_machines() if m["name"] != name]
    _write_machines(machines)
    return {"ok": True, "msg": "machine supprimée"}


def machines_public():
    """Liste des machines SANS mot de passe (jamais envoyé au navigateur)."""
    return [{"name": m["name"], "ip": m["ip"], "user": m["user"],
             "account": m["account"], "mode": m["mode"], "dns": m.get("dns", ""),
             "has_pwd": bool(m["pwd"])}
            for m in load_machines()]


def _resolve_ip(dns):
    """Résout un nom (mDNS/DNS) en IPv4 (repli toute famille). Lève si échec."""
    try:
        infos = socket.getaddrinfo(dns, 22, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except socket.gaierror:
        infos = socket.getaddrinfo(dns, 22, type=socket.SOCK_STREAM)
    return infos[0][4][0]


def resolve_machine(name):
    """Résout le nom mDNS/DNS d'une machine → IP courante, et met à jour le stockage."""
    m = next((x for x in load_machines() if x["name"] == name), None)
    if not m:
        return {"ok": False, "msg": "machine inconnue"}
    if not m.get("dns"):
        return {"ok": False, "msg": "pas de nom mDNS/DNS pour cette machine"}
    try:
        ip = _resolve_ip(m["dns"])
    except Exception as e:  # noqa
        return {"ok": False, "msg": f"résolution impossible de '{m['dns']}' ({e})"}
    changed = ip != m["ip"]
    if changed:
        save_machine({"name": m["name"], "ip": ip, "user": m["user"], "pwd": "",
                      "account": m["account"], "mode": m["mode"], "dns": m["dns"]})
    return {"ok": True, "ip": ip, "changed": changed, "dns": m["dns"]}


# ── Échelle « classe » : parallélisme, actions groupées, déploiement ───────
def _parallel(items, fn, workers=16):
    """Applique fn à chaque item en parallèle (pool borné). Retourne la liste."""
    items = list(items)
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
        return list(ex.map(fn, items))


AGENT_SCRIPT = Path(__file__).resolve().parent.parent / "agent" / "kid-timetrack.sh"


def deploy_agent(m):
    """Envoie kid-timetrack.sh sur la machine et l'exécute (compte = m['account'])."""
    try:
        if not AGENT_SCRIPT.exists():
            return {"ok": False, "msg": "agent/kid-timetrack.sh introuvable"}
        ssh_put_text(m, AGENT_SCRIPT.read_text(), "/tmp/kid-timetrack.sh")
        rc, out, err = ssh_run(
            m, f"bash /tmp/kid-timetrack.sh {m['account']}; rm -f /tmp/kid-timetrack.sh",
            timeout=180)
        if rc == 0:
            return {"ok": True, "msg": "agent déployé"}
        return {"ok": False, "msg": (err.strip() or out.strip() or "échec")[:160]}
    except Exception as e:  # noqa
        return {"ok": False, "msg": _ssh_err(e)}


def resolve_all(machines):
    """Résout les noms mDNS en parallèle, puis met à jour les IP en une écriture."""
    def res(m):
        if not m.get("dns"):
            return {"name": m["name"], "ok": False, "msg": "pas de nom mDNS", "ip": m["ip"]}
        try:
            ip = _resolve_ip(m["dns"])
            return {"name": m["name"], "ok": True, "ip": ip, "changed": ip != m["ip"]}
        except Exception as e:  # noqa
            return {"name": m["name"], "ok": False, "msg": str(e), "ip": m["ip"]}
    results = _parallel(machines, res)
    cur = load_machines()
    changed = False
    by_name = {r["name"]: r for r in results}
    for m in cur:
        r = by_name.get(m["name"])
        if r and r.get("ok") and r.get("changed"):
            m["ip"] = r["ip"]
            changed = True
    if changed:
        _write_machines(cur)
    return results


def bulk_action(action, params=None, names=None):
    """Action de classe en parallèle. action: lock|unlock|time|deploy|resolve."""
    params = params or {}
    machines = load_machines()
    if names:
        machines = [m for m in machines if m["name"] in names]
    if action == "resolve":
        return resolve_all(machines)
    if action == "lock":
        def fn(m): return {"name": m["name"], **write_timelimit(m, 23, 1, 0)}
    elif action == "unlock":
        def fn(m): return {"name": m["name"], **write_timelimit(m, 0, 0, 0)}
    elif action == "time":
        hs, he, bd = params.get("hstart"), params.get("hend"), params.get("budget")
        def fn(m): return {"name": m["name"], **write_timelimit(m, hs, he, bd)}
    elif action == "deploy":
        def fn(m): return {"name": m["name"], **deploy_agent(m)}
    else:
        return [{"ok": False, "msg": "action inconnue"}]
    return _parallel(machines, fn)


def load_master():
    if MASTER_LIST.exists():
        return MASTER_LIST.read_text()
    return ""


def save_master(text):
    # Garde uniquement les noms de paquets valides, triés et dédupliqués.
    pkgs, bad = [], []
    for raw in text.splitlines():
        p = raw.strip()
        if not p or p.startswith("#"):
            continue
        if PKG_RE.match(p):
            pkgs.append(p)
        else:
            bad.append(p)
    pkgs = sorted(set(pkgs))
    MASTER_LIST.parent.mkdir(parents=True, exist_ok=True)
    MASTER_LIST.write_text("\n".join(pkgs) + "\n")
    try:
        os.chmod(MASTER_LIST, 0o600)
    except OSError:
        pass
    return {"saved": len(pkgs), "rejected": bad}


def push_to(m):
    """Envoie la liste maître sur /etc/kid-install-allowlist du PC cible."""
    try:
        ssh_put_text(m, MASTER_LIST.read_text() if MASTER_LIST.exists() else "",
                     "/tmp/.kid-allowlist.new")
        cmd = ("install -m 0644 -o root -g root /tmp/.kid-allowlist.new " + REMOTE_PATH +
               " && rm -f /tmp/.kid-allowlist.new && wc -l < " + REMOTE_PATH)
        rc, out, err = ssh_run(m, cmd, timeout=30)
        if rc != 0:
            return {"ok": False, "msg": err.strip() or "install a échoué"}
        return {"ok": True, "msg": f"{out.strip()} paquets en place"}
    except Exception as e:  # noqa
        return {"ok": False, "msg": _ssh_err(e)}


def fetch_logs(m, n=40):
    try:
        rc, out, err = ssh_run(
            m, f"journalctl -t install-pkg --no-pager -n {int(n)} -o short-iso", timeout=30)
        return out.strip() or "(aucune tentative enregistrée)"
    except Exception as e:  # noqa
        return f"(erreur : {_ssh_err(e)})"


def machine_status(m):
    """Vérifie si la machine est joignable + quelques infos de santé."""
    cmd = ("printf '%s|%s|%s|%s|%s' "
           "\"$(hostname)\" "
           "\"$(uptime -p 2>/dev/null)\" "
           "\"$(wc -l < /etc/kid-install-allowlist 2>/dev/null)\" "
           "\"$(journalctl -t install-pkg --no-pager 2>/dev/null | grep -c 'ACCEPTÉ')\" "
           "\"$(journalctl -t install-pkg --no-pager 2>/dev/null | grep -c 'REFUSÉ')\"")
    try:
        rc, out, err = ssh_run(m, cmd, timeout=15, connect_timeout=6)
        if rc != 0:
            return {"online": False, "msg": "injoignable"}
        p = (out.strip().split("|") + ["", "", "", "", ""])[:5]
        return {"online": True, "hostname": p[0], "uptime": p[1],
                "allowlist": p[2], "accepted": p[3], "refused": p[4]}
    except Exception as e:  # noqa
        return {"online": False, "msg": _ssh_err(e)}


def run_update(m):
    """Lance la mise à jour système (maj = dnf upgrade durci) en root via SSH."""
    try:
        rc, out, err = ssh_run(m, "maj 2>&1 || dnf upgrade -y --refresh 2>&1", timeout=900)
        lines = (out + err).strip().splitlines()
        return {"ok": rc == 0, "out": "\n".join(lines[-40:]) or "(pas de sortie)"}
    except Exception as e:  # noqa
        return {"ok": False, "out": _ssh_err(e)}


def read_timelimit(m):
    """Lit la ligne kidtime de l'enfant (compte = champ `compte`, sinon nom)."""
    user = m.get("account") or m["name"]
    try:
        rc, out, err = ssh_run(
            m, f"grep -E '^[[:space:]]*{user}[[:space:]]' /etc/kidtime.conf 2>/dev/null | head -1",
            timeout=15)
        p = out.split()
        if len(p) >= 4:
            return {"ok": True, "hstart": p[1], "hend": p[2], "budget": p[3]}
        return {"ok": True, "hstart": "0", "hend": "0", "budget": "0"}
    except Exception as e:  # noqa
        return {"ok": False, "msg": _ssh_err(e)}


def write_timelimit(m, hstart, hend, budget):
    user = m.get("account") or m["name"]
    try:
        hs, he, bd = int(hstart), int(hend), int(budget)
    except (TypeError, ValueError):
        return {"ok": False, "msg": "valeurs invalides"}
    hs = max(0, min(24, hs)); he = max(0, min(24, he)); bd = max(0, min(1440, bd))
    line = f"{user} {hs} {he} {bd}"
    cmd = (f"touch /etc/kidtime.conf; "
           f"grep -vE '^[[:space:]]*{user}[[:space:]]' /etc/kidtime.conf > /tmp/.kt 2>/dev/null || true; "
           f"echo '{line}' >> /tmp/.kt; install -m0644 /tmp/.kt /etc/kidtime.conf; rm -f /tmp/.kt; "
           f"systemctl start kidtime.service 2>/dev/null; echo OK")
    try:
        rc, out, err = ssh_run(m, cmd, timeout=20)
        ok = rc == 0 and "OK" in out
        lim = (hs != he) or (bd > 0)
        return {"ok": ok, "msg": ("limites appliquées" if lim else "aucune limite") if ok
                else (err.strip() or "échec")}
    except Exception as e:  # noqa
        return {"ok": False, "msg": _ssh_err(e)}


PAGE = """<!doctype html><html lang=fr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Gestion PC enfants</title>
<style>
:root{--bg:#0f1115;--panel:#191c23;--line:#2a2f3a;--fg:#e6e8ee;--mut:#9aa3b2;
--ok:#3fb950;--bad:#f85149;--accent:#58a6ff;}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
header{padding:18px 24px;border-bottom:1px solid var(--line);display:flex;
align-items:center;gap:12px}
header h1{font-size:18px;margin:0}
.wrap{max-width:980px;margin:0 auto;padding:24px;display:grid;gap:22px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}
.card h2{margin:0 0 12px;font-size:15px;color:var(--accent);
text-transform:uppercase;letter-spacing:.04em}
.machines{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
.machine{border:1px solid var(--line);border-radius:10px;padding:14px;background:#13161c}
.machine b{font-size:15px}.machine .ip{color:var(--mut);font-size:13px}
button{background:#222732;color:var(--fg);border:1px solid var(--line);
border-radius:8px;padding:8px 14px;cursor:pointer;font:inherit}
button:hover{border-color:var(--accent)}
button.primary{background:var(--accent);color:#06101f;border-color:var(--accent);font-weight:600}
button.row{margin:4px 6px 0 0}
textarea{width:100%;min-height:300px;background:#0c0e12;color:var(--fg);
border:1px solid var(--line);border-radius:8px;padding:12px;font:13px/1.5 ui-monospace,monospace;resize:vertical}
.bar{display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap}
.status{font-size:13px;color:var(--mut)}
pre{background:#0c0e12;border:1px solid var(--line);border-radius:8px;padding:12px;
overflow:auto;font:12px/1.45 ui-monospace,monospace;max-height:300px}
code{background:#0c0e12;border:1px solid var(--line);border-radius:5px;padding:1px 6px;
font:13px ui-monospace,monospace;color:#ffd479}
table{width:100%;border-collapse:collapse}
td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
td:first-child{white-space:nowrap;color:#ffd479;font-family:ui-monospace,monospace;width:1%}
.muted{color:var(--mut)}.ok{color:var(--ok)}.bad{color:var(--bad)}
.pill{font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid var(--line);color:var(--mut)}
</style></head><body>
<div id=unlock style="display:none;position:fixed;inset:0;background:rgba(8,20,40,.96);z-index:99;
  align-items:center;justify-content:center;flex-direction:column;color:#fff;text-align:center">
  <div style="font-size:54px">🔐</div>
  <h2 style="color:#fff;border:none">Configuration verrouillée</h2>
  <p class=muted style="color:#bcd">Entre ton mot de passe maître pour déverrouiller.</p>
  <input id=u_pwd type=password placeholder="mot de passe maître"
    style="font-size:16px;padding:10px 14px;border-radius:8px;border:none;width:260px"
    onkeydown="if(event.key==='Enter')doUnlock()">
  <div><button class=primary onclick=doUnlock() style="margin-top:12px">Déverrouiller</button></div>
  <div id=u_msg class=status style="color:#f9b"></div>
  <div style="margin-top:14px;font-size:13px"><a href="#" onclick="doImportFile();return false" style="color:#9cf">📥 Importer une autre config (.enc)</a></div>
</div>
<div id=setup style="display:none;position:fixed;inset:0;background:rgba(8,20,40,.96);z-index:99;
  align-items:center;justify-content:center;flex-direction:column;color:#fff;text-align:center;padding:20px">
  <div style="font-size:54px">🔐</div>
  <h2 style="color:#fff;border:none">Protège les données de tes enfants</h2>
  <p class=muted style="color:#bcd;max-width:460px">Première utilisation : choisis un <b>mot de passe maître</b>.
  Il chiffre tout de suite les IP et mots de passe root. ⚠️ Sans lui, la config sera irrécupérable — note-le en lieu sûr.</p>
  <input id=set_p1 type=password placeholder="mot de passe maître"
    style="font-size:16px;padding:10px 14px;border-radius:8px;border:none;width:260px;margin:4px"
    onkeydown="if(event.key==='Enter')document.getElementById('set_p2').focus()">
  <input id=set_p2 type=password placeholder="confirme le mot de passe"
    style="font-size:16px;padding:10px 14px;border-radius:8px;border:none;width:260px;margin:4px"
    onkeydown="if(event.key==='Enter')doSetup()">
  <div><button class=primary onclick=doSetup() style="margin-top:10px">🔐 Créer &amp; chiffrer</button></div>
  <div id=set_msg class=status style="color:#f9b"></div>
  <div style="margin-top:16px;font-size:13px">
    <a href="#" onclick="doImportFile();return false" style="color:#9cf">📥 Importer une config existante (.enc)</a>
    &nbsp;·&nbsp;
    <a href="#" onclick="doSkip();return false" style="color:#9ab">Plus tard (sans chiffrement)</a>
  </div>
</div>
<input id=importfile type=file accept=".enc,application/octet-stream" style="display:none" onchange="onImportFile(event)">
<header><span style="font-size:22px">🛡️</span><h1>Gestion des PC enfants</h1>
<span class=pill>console-first · liste blanche</span></header>
<div class=wrap>

  <div class=card>
    <h2>⚙️ Réglages — mes PC enfants</h2>
    <p class=muted>Renseigne chaque PC (IP <b>ou</b> nom mDNS, compte SSH admin, mot de passe root).
    Stocké en local — <b>jamais</b> envoyé au navigateur ni publié.</p>
    <div id=vaultbox style="margin:8px 0"></div>
    <div id=setlist></div>
    <div style="border-top:1px solid var(--line);margin-top:10px;padding-top:10px">
      <b id=setformtitle>➕ Ajouter une machine</b>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0">
        <label>Nom de la machine<br><input id=s_name placeholder="ex. salon" style="width:95%"></label>
        <label>Adresse IP<br><input id=s_ip placeholder="192.168.1.50" style="width:95%"></label>
        <label>Nom mDNS/DNS (suit l'IP)<br><input id=s_dns placeholder="ex. salon.local" style="width:95%"></label>
        <label>Compte SSH admin<br><input id=s_user value=root style="width:95%"></label>
        <label>Compte de l'enfant<br><input id=s_account placeholder="(si différent du nom)" style="width:95%"></label>
        <label>Mot de passe root<br><input id=s_pwd type=password placeholder="(vide = inchangé)" style="width:95%"></label>
        <label>Mode<br><select id=s_mode style="width:98%">
          <option value=timetrack>timetrack — surveillance + quota</option>
          <option value=lockdown>lockdown — console verrouillée</option></select></label>
      </div>
      <button class=primary onclick=saveSet()>💾 Enregistrer la machine</button>
      <button onclick=clearSet()>✖️ Annuler</button>
      <span class=status id=setstatus></span>
    </div>
  </div>

  <div class=card>
    <h2>Machines &nbsp;<button onclick=refreshStatus() style="font-size:12px;padding:4px 10px">🔄 Rafraîchir le statut</button></h2>
    <div class=bar style="margin:6px 0 10px;flex-wrap:wrap;gap:6px;align-items:center">
      <b>👥 Toute la classe :</b>
      <button class=row onclick="bulk('lock','🔒 Verrouiller TOUTE la classe (privé de PC) ?')">🔒 Verrouiller tous</button>
      <button class=row onclick="bulk('unlock','🔓 Déverrouiller toute la classe ?')">🔓 Déverrouiller tous</button>
      <button class=row onclick="bulkTime()">⏱ Temps pour tous</button>
      <button class=row onclick="bulk('resolve')">🔄 Résoudre les IP</button>
      <button class=row onclick="bulk('deploy','🚀 Déployer/réinstaller l’agent sur TOUS les PC en ligne ?')">🚀 Déployer l’agent</button>
      <span class=status id=bulkst></span>
    </div>
    <div class=machines id=machines></div>
  </div>

  <div class=card>
    <h2>Liste blanche maître</h2>
    <p class=muted>Un paquet par ligne. Source de vérité unique, poussée à l'identique
    sur les PC. Les noms invalides sont ignorés à l'enregistrement.</p>
    <textarea id=list spellcheck=false></textarea>
    <div class=bar>
      <button class=primary onclick=save()>💾 Enregistrer</button>
      <button onclick=pushAll()>⬆️ Enregistrer + Pousser vers TOUS</button>
      <span class=status id=lstatus></span>
    </div>
  </div>

  <div class=card>
    <h2>Journal des installations</h2>
    <p class=muted>Ce que les enfants ont tenté d'installer (accepté / refusé).</p>
    <div class=bar id=logbtns></div>
    <pre id=logs class=muted>Choisis une machine ci-dessus.</pre>
  </div>

  <div class=card>
    <h2>Aide — côté enfant (commande <code>pkg</code>)</h2>
    <p class=muted>Les enfants n'ont pas <code>sudo dnf</code>. Ils gèrent les paquets
    autorisés avec la commande <code>pkg</code> (sans sudo, sauf l'install) :</p>
    <table>
      <tr><td>pkg list</td><td>Liste tous les paquets autorisés.</td></tr>
      <tr><td>pkg search &lt;terme&gt;</td><td>Cherche parmi les autorisés (par nom <i>et</i> description).</td></tr>
      <tr><td>pkg info &lt;paquet&gt;</td><td>Affiche les détails d'un paquet autorisé.</td></tr>
      <tr><td>pkg install &lt;paquet&gt;</td><td>Installe (relaie vers <code>sudo install-pkg</code>, liste blanche uniquement).</td></tr>
    </table>
    <h2 style="margin-top:18px">Aide — verrous en place</h2>
    <table>
      <tr><td>Bureau</td><td>Aucun (console au boot). Pas de GNOME/KDE/Sway.</td></tr>
      <tr><td>Graphique</td><td><code>cage -- ./mon_app</code> lance une appli MAISON en plein écran (pas de WM).</td></tr>
      <tr><td>Navigateur</td><td>Web/mail/chat en <b>texte</b> (w3m, lynx, neomutt, weechat). Navigateur graphique <b>interdit</b>.</td></tr>
      <tr><td>Sudo</td><td>Pas de root complet. Autorisé : <code>install-pkg</code> (liste blanche) + reboot/poweroff/suspend.</td></tr>
      <tr><td>Install</td><td>Impossible hors liste blanche. <code>sudo dnf</code> direct refusé.</td></tr>
      <tr><td>Côté parent</td><td>Modifie la liste ci-dessus, clique « Pousser ». Tu peux toujours te connecter en <code>ssh root@&lt;ip&gt;</code> pour le reste.</td></tr>
    </table>
  </div>

</div>
<script>
let MACHINES=[];
let LOCKED={};
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function load(){
  const st=await j('/api/state');
  const ov=document.getElementById('unlock'), su=document.getElementById('setup');
  if(st.locked){ su.style.display='none'; ov.style.display='flex'; document.getElementById('u_pwd').focus(); return; }
  ov.style.display='none';
  if(st.setup_needed){ su.style.display='flex'; document.getElementById('set_p1').focus(); return; }
  su.style.display='none';
  renderVault(st);
  MACHINES=await j('/api/machines');
  document.getElementById('list').value=await (await fetch('/api/allowlist')).text();
  const m=document.getElementById('machines'),lb=document.getElementById('logbtns');
  m.innerHTML='';lb.innerHTML='';
  MACHINES.forEach(x=>{
    const d=document.createElement('div');d.className='machine';
    d.innerHTML=`<div id="dot_${x.name}" style="float:right">⚪</div>
      <b>${x.name}</b> <span class=ip>${x.user}@${x.ip}</span>
      <div class=status id="info_${x.name}" style="margin:6px 0">⏳ statut…</div>
      <button class="primary row" onclick="push('${x.name}')">⬆️ Pousser</button>
      <button class="row" onclick="updateM('${x.name}')">🔄 Mettre à jour</button>
      <span class=status id="st_${x.name}"></span>
      <div class=tl style="margin-top:8px;border-top:1px solid var(--line);padding-top:8px;font-size:13px">
        ⏱️ <b>Temps d'écran</b><br>
        de <input id="hs_${x.name}" type=number min=0 max=24 style="width:44px">h
        à <input id="he_${x.name}" type=number min=0 max=24 style="width:44px">h ·
        <input id="bd_${x.name}" type=number min=0 max=1440 style="width:58px"> min/j
        <button class=row onclick="saveTL('${x.name}')">Appliquer</button>
        <div class=status id="tl_${x.name}">…</div>
        <div class=muted style="font-size:11px">heures égales = toute la journée · 0 min/j = pas de limite de durée</div>
        <div style="margin-top:8px;border-top:1px dashed var(--line);padding-top:8px">
          🚫 <b>Punition</b> :
          <button id="lockbtn_${x.name}" onclick="toggleLock('${x.name}')" style="font-weight:bold">🔒 Verrouiller (privé de PC)</button>
          <span class=status id="lockst_${x.name}"></span>
        </div>
      </div>`;
    m.appendChild(d);
    const b=document.createElement('button');b.textContent='📜 '+x.name;
    b.onclick=()=>showLogs(x.name);lb.appendChild(b);
  });
  if(!MACHINES.length)m.innerHTML='<p class=muted>Aucune machine. Ajoute-en une dans ⚙️ Réglages ci-dessus.</p>';
  refreshStatus();
  MACHINES.forEach(x=>loadTL(x.name));
  loadSet();
}
function renderVault(st){
  const b=document.getElementById('vaultbox'); if(!b)return;
  if(!st.crypto){ b.innerHTML='<span class=muted>🔓 Chiffrement indisponible — installe le module Python <code>cryptography</code> (<code>pip install cryptography</code>).</span>'; return; }
  if(st.encrypted){
    b.innerHTML='<span class=ok>🔐 Configuration chiffrée.</span> '+
      '<button class=row onclick=doExport()>📤 Exporter</button> '+
      '<button class=row onclick=doImportFile()>📥 Importer</button> '+
      '<button class=row onclick=doChangeMaster()>🔑 Changer le mot de passe</button> '+
      '<button class=row onclick=doRemoveMaster()>🔓 Retirer le chiffrement</button> '+
      '<button class=row onclick=doLockVault()>🔒 Verrouiller</button>';
  }else{
    b.innerHTML='<span class=bad>🔓 Mots de passe stockés en clair.</span> '+
      '<button class=primary onclick=doEncrypt()>🔐 Protéger par un mot de passe maître</button> '+
      '<button class=row onclick=doImportFile()>📥 Importer une config (.enc)</button>';
  }
}
async function doSetup(){
  const p1=document.getElementById('set_p1').value, p2=document.getElementById('set_p2').value;
  const m=document.getElementById('set_msg');
  if(p1.length<4){ m.textContent='❌ 4 caractères minimum'; return; }
  if(p1!==p2){ m.textContent='❌ les deux mots de passe diffèrent'; return; }
  const r=await j('/api/encrypt',{method:'POST',body:JSON.stringify({password:p1})});
  if(r.ok){ m.textContent=''; load(); } else m.textContent='❌ '+(r.msg||'');
}
async function doSkip(){ await j('/api/skip-encrypt',{method:'POST'}); load(); }
function doExport(){ window.location='/api/export'; }
function doImportFile(){ document.getElementById('importfile').click(); }
function onImportFile(ev){
  const f=ev.target.files[0]; if(!f) return;
  const rd=new FileReader();
  rd.onload=async function(){
    const b64=(''+rd.result).split(',').pop();
    const r=await j('/api/import',{method:'POST',body:JSON.stringify({data:b64})});
    alert(r.ok?('✅ '+r.msg):('❌ '+(r.msg||'')));
    ev.target.value=''; load();
  };
  rd.readAsDataURL(f);
}
async function doUnlock(){
  const p=document.getElementById('u_pwd').value;
  const r=await j('/api/unlock',{method:'POST',body:JSON.stringify({password:p})});
  if(r.ok){ document.getElementById('u_pwd').value=''; document.getElementById('u_msg').textContent=''; load(); }
  else document.getElementById('u_msg').textContent='❌ '+(r.msg||'');
}
async function doEncrypt(){
  const p=prompt('Choisis un MOT DE PASSE MAÎTRE pour chiffrer la config.\\n\\n⚠️ Si tu l\\'oublies, la config sera IRRÉCUPÉRABLE. Note-le en lieu sûr.');
  if(!p) return;
  if(prompt('Confirme le mot de passe maître :')!==p){ alert('Les deux mots de passe diffèrent.'); return; }
  const r=await j('/api/encrypt',{method:'POST',body:JSON.stringify({password:p})});
  alert(r.ok?('✅ '+r.msg):('❌ '+(r.msg||'')));
  load();
}
async function doLockVault(){ await j('/api/lock-vault',{method:'POST'}); load(); }
async function doChangeMaster(){
  const o=prompt('Mot de passe maître ACTUEL :'); if(!o) return;
  const n=prompt('NOUVEAU mot de passe maître :'); if(!n) return;
  if(prompt('Confirme le nouveau mot de passe :')!==n){ alert('Les deux mots de passe diffèrent.'); return; }
  const r=await j('/api/change-master',{method:'POST',body:JSON.stringify({old:o,new:n})});
  alert(r.ok?('✅ '+r.msg):('❌ '+(r.msg||''))); load();
}
async function doRemoveMaster(){
  if(!confirm('Retirer le chiffrement ? Les mots de passe repasseront EN CLAIR (chmod 600).')) return;
  const p=prompt('Mot de passe maître pour confirmer :'); if(!p) return;
  const r=await j('/api/remove-master',{method:'POST',body:JSON.stringify({password:p})});
  alert(r.ok?('✅ '+r.msg):('❌ '+(r.msg||''))); load();
}
async function resolveIp(name){
  const r=await j('/api/resolve?machine='+encodeURIComponent(name),{method:'POST'});
  alert(r.ok?(r.changed?('✅ '+name+' : nouvelle IP → '+r.ip):('✅ '+name+' : IP inchangée ('+r.ip+')')):('❌ '+(r.msg||'')));
  load();
}
async function bulk(action,confirmMsg){
  if(confirmMsg && !confirm(confirmMsg)) return;
  const st=document.getElementById('bulkst'); st.textContent='⏳ en cours sur la classe…';
  const r=await j('/api/bulk?action='+action,{method:'POST',body:'{}'});
  const ok=r.filter(x=>x.ok).length, ko=r.length-ok;
  let s='<span class=ok>✅ '+ok+'</span> / <span class=bad>❌ '+ko+'</span>';
  if(ko) s+=' — '+r.filter(x=>!x.ok).map(x=>x.name+' ('+(x.msg||'?')+')').slice(0,4).join(' · ')+(ko>4?' …':'');
  st.innerHTML=s;
  refreshStatus(); MACHINES.forEach(x=>loadTL(x.name));
}
async function bulkTime(){
  const hs=prompt('Heure de DÉBUT autorisée (0-24) :','8'); if(hs===null) return;
  const he=prompt('Heure de FIN autorisée (0-24) :','17'); if(he===null) return;
  const bd=prompt('Budget en MINUTES/jour (0 = pas de limite de durée) :','0'); if(bd===null) return;
  const st=document.getElementById('bulkst'); st.textContent='⏳ application à toute la classe…';
  const r=await j('/api/bulk?action=time',{method:'POST',body:JSON.stringify({hstart:hs,hend:he,budget:bd})});
  const ok=r.filter(x=>x.ok).length, ko=r.length-ok;
  st.innerHTML='<span class=ok>✅ temps appliqué à '+ok+' PC</span>'+(ko?(' · <span class=bad>❌ '+ko+'</span>'):'');
  MACHINES.forEach(x=>loadTL(x.name));
}
async function loadSet(){
  const L=await j('/api/settings'); window._SET=L;
  const el=document.getElementById('setlist');
  if(!L.length){ el.innerHTML='<p class=muted>Aucune machine enregistrée. Remplis le formulaire ci-dessous 👇</p>'; return; }
  el.innerHTML='<table><tr><th>Nom</th><th>Adresse</th><th>Compte enfant</th><th>Mode</th><th></th></tr>'+
    L.map(function(x){
      var addr=x.ip+(x.dns?(' <span class=muted>('+x.dns+')</span>'):'');
      var rb=x.dns?(' <button class=row onclick="resolveIp(\\''+x.name+'\\')">🔄 IP</button>'):'';
      return '<tr><td><b>'+x.name+'</b></td><td>'+addr+'</td><td>'+(x.account||x.name)+'</td><td>'+x.mode+'</td>'+
        '<td style="white-space:nowrap"><button class=row onclick="editSet(\\''+x.name+'\\')">✏️</button> '+
        '<button class=row onclick="delSet(\\''+x.name+'\\')">🗑️</button>'+rb+'</td></tr>';
    }).join('')+'</table>';
}
function editSet(name){
  const x=(window._SET||[]).find(m=>m.name===name); if(!x)return;
  window._editOrig=x.name;
  document.getElementById('s_name').value=x.name;
  document.getElementById('s_ip').value=x.ip;
  document.getElementById('s_dns').value=x.dns||'';
  document.getElementById('s_user').value=x.user;
  document.getElementById('s_account').value=x.account||'';
  document.getElementById('s_pwd').value='';
  document.getElementById('s_mode').value=x.mode;
  document.getElementById('setformtitle').textContent='✏️ Modifier « '+name+' » (tu peux changer le nom · mot de passe vide = inchangé)';
  document.getElementById('s_name').focus();
}
function clearSet(){
  window._editOrig='';
  ['s_name','s_ip','s_dns','s_account','s_pwd'].forEach(i=>document.getElementById(i).value='');
  document.getElementById('s_user').value='root';
  document.getElementById('s_mode').value='timetrack';
  document.getElementById('setformtitle').textContent='➕ Ajouter une machine';
  document.getElementById('setstatus').textContent='';
}
async function saveSet(){
  const g=i=>document.getElementById(i).value;
  const st=document.getElementById('setstatus'); st.textContent='⏳…';
  const r=await j('/api/settings/save',{method:'POST',body:JSON.stringify({
    name:g('s_name'),orig:(window._editOrig||''),ip:g('s_ip'),dns:g('s_dns'),user:g('s_user'),account:g('s_account'),pwd:g('s_pwd'),mode:g('s_mode')})});
  st.innerHTML=r.ok?'<span class=ok>✅ '+r.msg+'</span>':'<span class=bad>❌ '+(r.msg||'')+'</span>';
  if(r.ok){ clearSet(); load(); }
}
async function delSet(name){
  if(!confirm('Supprimer la machine « '+name+' » de la liste ?')) return;
  await j('/api/settings/delete',{method:'POST',body:JSON.stringify({name:name})});
  load();
}
async function loadTL(name){
  let r; try{ r=await j('/api/timelimit?machine='+encodeURIComponent(name)); }catch(e){ return; }
  if(!r||!r.ok)return;
  const g=id=>document.getElementById(id+'_'+name);
  if(g('hs'))g('hs').value=r.hstart; if(g('he'))g('he').value=r.hend; if(g('bd'))g('bd').value=r.budget;
  const locked=(+r.hstart===23 && +r.hend===1);
  LOCKED[name]=locked;
  const lb=document.getElementById('lockbtn_'+name);
  if(lb)lb.textContent=locked?'🔓 Déverrouiller':'🔒 Verrouiller (privé de PC)';
  const card=document.getElementById('info_'+name);
  const tl=document.getElementById('tl_'+name);
  if(tl){ if(locked){ tl.innerHTML="<span class=bad>🔒 VERROUILLÉ jusqu'à nouvel ordre</span>"; }
    else { const lim=(r.hstart!==r.hend)||(+r.budget>0);
      tl.innerHTML= lim?'<span class=ok>limites actives</span>':'<span class=muted>aucune limite</span>'; } }
}
async function toggleLock(name){
  const lock=!LOCKED[name];
  if(lock && !confirm('Verrouiller '+name+' (privé de PC) jusqu\\'à nouvel ordre ?\\nLa session ouverte sera fermée et le PC affichera « VERROUILLÉ ».')) return;
  const st=document.getElementById('lockst_'+name); if(st)st.textContent='⏳…';
  const r=await j('/api/lock?machine='+encodeURIComponent(name)+'&on='+(lock?'1':'0'),{method:'POST'});
  if(st)st.innerHTML=r.ok?('<span class=ok>'+(lock?'🔒 verrouillé':'🔓 déverrouillé')+'</span>'):('<span class=bad>❌ '+(r.msg||'')+'</span>');
  loadTL(name);
}
async function saveTL(name){
  const g=id=>document.getElementById(id+'_'+name).value;
  const tl=document.getElementById('tl_'+name); tl.textContent='⏳…';
  const r=await j('/api/timelimit?machine='+encodeURIComponent(name),{method:'POST',
    body:JSON.stringify({hstart:g('hs'),hend:g('he'),budget:g('bd')})});
  tl.innerHTML= r.ok?'<span class=ok>✅ '+(r.msg||'réglé')+'</span>':'<span class=bad>❌ '+(r.msg||'')+'</span>';
}
async function refreshStatus(){
  MACHINES.forEach(x=>{
    const dot=document.getElementById('dot_'+x.name);
    const info=document.getElementById('info_'+x.name);
    if(dot)dot.textContent='⏳'; if(info)info.textContent='vérification…';
  });
  const r=await j('/api/status?machine=all');
  r.forEach(s=>{
    const dot=document.getElementById('dot_'+s.name);
    const info=document.getElementById('info_'+s.name);
    if(!dot||!info)return;
    if(s.online){
      dot.textContent='🟢';
      info.innerHTML=`<span class=ok>en ligne</span> · ${s.uptime||''}<br>`+
        `liste: ${s.allowlist} paquets · installs ✅ ${s.accepted} / ❌ ${s.refused}`;
    }else{
      dot.textContent='🔴';
      info.innerHTML=`<span class=bad>hors ligne</span> (${s.msg||'?'})`;
    }
  });
}
async function save(){
  const r=await j('/api/allowlist',{method:'POST',body:document.getElementById('list').value});
  let s=`✅ ${r.saved} paquets enregistrés`;
  if(r.rejected.length)s+=` · ⚠️ ignorés: ${r.rejected.join(', ')}`;
  document.getElementById('lstatus').textContent=s;
  return r;
}
async function push(name){
  const st=document.getElementById('st_'+name);st.textContent='⏳…';
  const r=await j('/api/push?machine='+encodeURIComponent(name),{method:'POST'});
  const res=r[0];st.innerHTML=res.ok?`<span class=ok>✅ ${res.msg}</span>`:`<span class=bad>❌ ${res.msg}</span>`;
}
async function pushAll(){
  await save();
  document.getElementById('lstatus').textContent='⏳ envoi en cours…';
  const r=await j('/api/push?machine=all',{method:'POST'});
  document.getElementById('lstatus').innerHTML=r.map(x=>
    `${x.name}: `+(x.ok?`<span class=ok>${x.msg}</span>`:`<span class=bad>${x.msg}</span>`)).join(' · ');
  MACHINES.forEach((x,i)=>{const st=document.getElementById('st_'+x.name);
    if(st&&r[i])st.innerHTML=r[i].ok?`<span class=ok>✅</span>`:`<span class=bad>❌</span>`;});
}
async function updateM(name){
  const p=document.getElementById('logs');p.className='';
  p.textContent='⏳ Mise à jour de '+name+'… (peut prendre quelques minutes, patiente)';
  const r=await j('/api/update?machine='+encodeURIComponent(name),{method:'POST'});
  p.textContent=(r.ok?'✅ ':'❌ ')+name+' :\\n\\n'+(r.out||'');
}
async function showLogs(name){
  const p=document.getElementById('logs');p.textContent='⏳ récupération…';
  const r=await fetch('/api/logs?machine='+encodeURIComponent(name));
  p.textContent=await r.text();p.className='';
}
load();
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):  # silencieux
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/state":
            return self._send(200, vault_state())
        if u.path == "/api/export":
            data = export_enc()
            if data is None:
                return self._send(404, {"ok": False, "msg": "rien à exporter (non chiffré)"})
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition",
                             "attachment; filename=machines.conf.enc")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path == "/":
            return self._send(200, PAGE, "text/html")
        if is_locked():
            return self._send(423, {"locked": True, "msg": "verrouillé"})
        if u.path == "/api/machines":
            return self._send(200, [{"name": m["name"], "ip": m["ip"],
                                     "user": m["user"]} for m in load_machines()])
        if u.path == "/api/allowlist":
            return self._send(200, load_master(), "text/plain")
        if u.path == "/api/status":
            q = parse_qs(u.query)
            name = q.get("machine", [""])[0]
            machines = load_machines()
            if name and name != "all":
                machines = [x for x in machines if x["name"] == name]
            return self._send(200, _parallel(
                machines, lambda m: {"name": m["name"], **machine_status(m)}))
        if u.path == "/api/logs":
            q = parse_qs(u.query)
            name = q.get("machine", [""])[0]
            m = next((x for x in load_machines() if x["name"] == name), None)
            if not m:
                return self._send(404, "machine inconnue", "text/plain")
            return self._send(200, fetch_logs(m), "text/plain")
        if u.path == "/api/timelimit":
            q = parse_qs(u.query)
            name = q.get("machine", [""])[0]
            m = next((x for x in load_machines() if x["name"] == name), None)
            if not m:
                return self._send(404, {"ok": False, "msg": "machine inconnue"})
            return self._send(200, read_timelimit(m))
        if u.path == "/api/settings":
            return self._send(200, machines_public())
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else ""
        if u.path in ("/api/unlock", "/api/encrypt", "/api/change-master",
                      "/api/remove-master"):
            try:
                d = json.loads(body or "{}")
            except ValueError:
                d = {}
            if u.path == "/api/unlock":
                return self._send(200, unlock_vault(d.get("password", "")))
            if u.path == "/api/encrypt":
                return self._send(200, enable_encryption(d.get("password", "")))
            if u.path == "/api/change-master":
                return self._send(200, change_master(d.get("old", ""), d.get("new", "")))
            return self._send(200, remove_encryption(d.get("password", "")))
        if u.path == "/api/skip-encrypt":
            return self._send(200, skip_encryption())
        if u.path == "/api/import":
            try:
                d = json.loads(body or "{}")
            except ValueError:
                d = {}
            return self._send(200, import_enc(d.get("data", "")))
        if u.path == "/api/lock-vault":
            return self._send(200, lock_vault())
        if is_locked():
            return self._send(423, {"locked": True, "msg": "verrouillé"})
        if u.path == "/api/resolve":
            q = parse_qs(u.query)
            return self._send(200, resolve_machine(q.get("machine", [""])[0]))
        if u.path == "/api/bulk":
            q = parse_qs(u.query)
            action = q.get("action", [""])[0]
            try:
                params = json.loads(body or "{}")
            except ValueError:
                params = {}
            names = params.get("names")        # None = toutes
            return self._send(200, bulk_action(action, params, names))
        if u.path == "/api/allowlist":
            return self._send(200, save_master(body))
        if u.path == "/api/push":
            q = parse_qs(u.query)
            name = q.get("machine", [""])[0]
            machines = load_machines()
            if name != "all":
                machines = [m for m in machines if m["name"] == name]
            return self._send(200, _parallel(
                machines, lambda m: {"name": m["name"], **push_to(m)}))
        if u.path == "/api/update":
            q = parse_qs(u.query)
            name = q.get("machine", [""])[0]
            m = next((x for x in load_machines() if x["name"] == name), None)
            if not m:
                return self._send(404, {"ok": False, "out": "machine inconnue"})
            return self._send(200, run_update(m))
        if u.path == "/api/timelimit":
            q = parse_qs(u.query)
            name = q.get("machine", [""])[0]
            m = next((x for x in load_machines() if x["name"] == name), None)
            if not m:
                return self._send(404, {"ok": False, "msg": "machine inconnue"})
            try:
                d = json.loads(body or "{}")
            except ValueError:
                d = {}
            return self._send(200, write_timelimit(m, d.get("hstart"), d.get("hend"),
                                                    d.get("budget")))
        if u.path == "/api/lock":
            # Verrou « privé de PC » : 23 1 0 = aucune heure autorisée
            # (écran « VERROUILLÉ JUSQU'À NOUVEL ORDRE »). on=0 -> 0 0 0 (libre).
            q = parse_qs(u.query)
            name = q.get("machine", [""])[0]
            on = q.get("on", ["1"])[0] == "1"
            m = next((x for x in load_machines() if x["name"] == name), None)
            if not m:
                return self._send(404, {"ok": False, "msg": "machine inconnue"})
            r = write_timelimit(m, 23, 1, 0) if on else write_timelimit(m, 0, 0, 0)
            r["locked"] = on
            return self._send(200, r)
        if u.path == "/api/settings/save":
            try:
                d = json.loads(body or "{}")
            except ValueError:
                d = {}
            return self._send(200, save_machine(d))
        if u.path == "/api/settings/delete":
            try:
                d = json.loads(body or "{}")
            except ValueError:
                d = {}
            return self._send(200, delete_machine(d.get("name", "")))
        return self._send(404, "not found", "text/plain")


def main():
    url = f"http://{HOST}:{PORT}"
    open_browser = "--open" in sys.argv or os.environ.get("KIDCODE_OPEN") == "1"
    if paramiko is None:
        print("⚠️  paramiko manquant : le SSH ne marchera pas.")
        print("    Installez :  pip install paramiko   (ou: dnf install python3-paramiko)")
    print(f"kidcode dashboard  ->  {url}")
    print(f"  config (machines + mots de passe) : {MACHINES_CONF}")
    try:
        srv = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        # déjà lancé : on ouvre juste le navigateur sur l'instance existante
        print("Déjà lancé — ouverture du navigateur.")
        if open_browser:
            import webbrowser
            webbrowser.open(url)
        return
    if open_browser:
        import webbrowser
        import threading
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print("Ctrl+C pour arrêter.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    main()
