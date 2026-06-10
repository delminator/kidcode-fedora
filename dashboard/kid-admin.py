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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    import paramiko
except ImportError:
    paramiko = None

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
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # = ssh accept-new
    cli.connect(m["ip"], username=m["user"], password=m["pwd"],
                timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
                look_for_keys=False, allow_agent=False)
    return cli


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


def load_machines():
    machines = []
    if not MACHINES_CONF.exists():
        return machines
    for line in MACHINES_CONF.read_text().splitlines():
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
        machines.append({"name": name, "ip": ip, "user": user, "pwd": pwd,
                         "account": account, "mode": mode})
    return machines


CONF_HEADER = (
    "# kidcode-fedora — machines (généré par la page Réglages).\n"
    "# Format : nom|ip|user|password[|compte][|mode]\n"
    "# Contient des MOTS DE PASSE — ne jamais committer (gitignore).\n")


def _clean(v, default=""):
    """Nettoie un champ : pas de | ni de saut de ligne (séparateurs du fichier)."""
    return str(v or default).replace("|", "").replace("\n", "").replace("\r", "").strip()


def _write_machines(machines):
    """Réécrit machines.conf (chmod 600) à partir de la liste de dicts."""
    MACHINES_CONF.parent.mkdir(parents=True, exist_ok=True)
    lines = [CONF_HEADER]
    for m in machines:
        lines.append("|".join([m["name"], m["ip"], m["user"], m["pwd"],
                               m.get("account", ""), m.get("mode", "timetrack")]))
    MACHINES_CONF.write_text("\n".join(lines) + "\n")
    try:
        os.chmod(MACHINES_CONF, 0o600)
    except OSError:
        pass


def save_machine(d):
    """Ajoute ou met à jour une machine. Mot de passe vide = on garde l'ancien."""
    name = _clean(d.get("name"))
    ip = _clean(d.get("ip"))
    user = _clean(d.get("user"), "root")
    account = _clean(d.get("account"))
    mode = _clean(d.get("mode"), "timetrack").lower()
    pwd = str(d.get("pwd") or "").replace("|", "").replace("\n", "").replace("\r", "")
    if not name or not ip:
        return {"ok": False, "msg": "nom et IP obligatoires"}
    if mode not in ("timetrack", "lockdown"):
        mode = "timetrack"
    machines = load_machines()
    existing = next((m for m in machines if m["name"] == name), None)
    if not pwd:                       # pas de nouveau mot de passe → garder l'ancien
        if existing and existing["pwd"]:
            pwd = existing["pwd"]
        else:
            return {"ok": False, "msg": "mot de passe requis pour une nouvelle machine"}
    entry = {"name": name, "ip": ip, "user": user, "pwd": pwd,
             "account": account, "mode": mode}
    if existing:
        machines = [entry if m["name"] == name else m for m in machines]
    else:
        machines.append(entry)
    _write_machines(machines)
    return {"ok": True, "msg": "machine enregistrée"}


def delete_machine(name):
    name = _clean(name)
    machines = [m for m in load_machines() if m["name"] != name]
    _write_machines(machines)
    return {"ok": True, "msg": "machine supprimée"}


def machines_public():
    """Liste des machines SANS mot de passe (jamais envoyé au navigateur)."""
    return [{"name": m["name"], "ip": m["ip"], "user": m["user"],
             "account": m["account"], "mode": m["mode"], "has_pwd": bool(m["pwd"])}
            for m in load_machines()]


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
<header><span style="font-size:22px">🛡️</span><h1>Gestion des PC enfants</h1>
<span class=pill>console-first · liste blanche</span></header>
<div class=wrap>

  <div class=card>
    <h2>⚙️ Réglages — mes PC enfants</h2>
    <p class=muted>Renseigne chaque PC (IP, compte SSH admin, mot de passe root). Stocké en local
    dans <code>machines.conf</code> (chmod 600) — <b>jamais</b> envoyé au navigateur ni publié.</p>
    <div id=setlist></div>
    <div style="border-top:1px solid var(--line);margin-top:10px;padding-top:10px">
      <b id=setformtitle>➕ Ajouter une machine</b>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0">
        <label>Nom de la machine<br><input id=s_name placeholder="ex. salon" style="width:95%"></label>
        <label>Adresse IP<br><input id=s_ip placeholder="192.168.1.50" style="width:95%"></label>
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
async function loadSet(){
  const L=await j('/api/settings'); window._SET=L;
  const el=document.getElementById('setlist');
  if(!L.length){ el.innerHTML='<p class=muted>Aucune machine enregistrée. Remplis le formulaire ci-dessous 👇</p>'; return; }
  el.innerHTML='<table><tr><th>Nom</th><th>IP</th><th>Compte enfant</th><th>Mode</th><th></th></tr>'+
    L.map(x=>'<tr><td><b>'+x.name+'</b></td><td>'+x.ip+'</td><td>'+(x.account||x.name)+'</td><td>'+x.mode+'</td>'+
      '<td style="white-space:nowrap"><button class=row onclick="editSet(\\''+x.name+'\\')">✏️ Modifier</button> '+
      '<button class=row onclick="delSet(\\''+x.name+'\\')">🗑️</button></td></tr>').join('')+'</table>';
}
function editSet(name){
  const x=(window._SET||[]).find(m=>m.name===name); if(!x)return;
  document.getElementById('s_name').value=x.name;
  document.getElementById('s_ip').value=x.ip;
  document.getElementById('s_user').value=x.user;
  document.getElementById('s_account').value=x.account||'';
  document.getElementById('s_pwd').value='';
  document.getElementById('s_mode').value=x.mode;
  document.getElementById('setformtitle').textContent='✏️ Modifier « '+name+' » (mot de passe vide = inchangé)';
  document.getElementById('s_name').focus();
}
function clearSet(){
  ['s_name','s_ip','s_account','s_pwd'].forEach(i=>document.getElementById(i).value='');
  document.getElementById('s_user').value='root';
  document.getElementById('s_mode').value='timetrack';
  document.getElementById('setformtitle').textContent='➕ Ajouter une machine';
  document.getElementById('setstatus').textContent='';
}
async function saveSet(){
  const g=i=>document.getElementById(i).value;
  const st=document.getElementById('setstatus'); st.textContent='⏳…';
  const r=await j('/api/settings/save',{method:'POST',body:JSON.stringify({
    name:g('s_name'),ip:g('s_ip'),user:g('s_user'),account:g('s_account'),pwd:g('s_pwd'),mode:g('s_mode')})});
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
        if u.path == "/":
            return self._send(200, PAGE, "text/html")
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
            return self._send(200, [{"name": m["name"], **machine_status(m)}
                                    for m in machines])
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
        if u.path == "/api/allowlist":
            return self._send(200, save_master(body))
        if u.path == "/api/push":
            q = parse_qs(u.query)
            name = q.get("machine", [""])[0]
            machines = load_machines()
            if name != "all":
                machines = [m for m in machines if m["name"] == name]
            out = []
            for m in machines:
                r = push_to(m)
                out.append({"name": m["name"], **r})
            return self._send(200, out)
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
