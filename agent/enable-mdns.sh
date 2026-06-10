#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
#  enable-mdns.sh — publie le service mDNS _kidcode._tcp avec un ID STABLE.
#  À lancer EN ROOT sur un PC enfant. Permet au tableau de bord de retrouver
#  ce PC (auto-réparation d'IP) même si son adresse DHCP change.
#  Déjà inclus dans kid-timetrack.sh et kid-lockdown.sh ; utile pour mettre à
#  jour un PC qui tourne une ancienne version de l'agent.
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "À lancer en root." >&2; exit 1; }
dnf install -y avahi nss-mdns >/dev/null 2>&1 || true
systemctl enable --now avahi-daemon >/dev/null 2>&1 || true
mkdir -p /etc/avahi/services
KID_ID=$(cat /etc/machine-id 2>/dev/null || hostname); KID_ID=${KID_ID:0:16}
cat > /etc/avahi/services/kidcode.service <<XML
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">kidcode %h</name>
  <service>
    <type>_kidcode._tcp</type>
    <port>22</port>
    <txt-record>id=$KID_ID</txt-record>
  </service>
</service-group>
XML
systemctl reload avahi-daemon 2>/dev/null || systemctl restart avahi-daemon 2>/dev/null || true
echo "mDNS _kidcode publié : id=$KID_ID  host=$(hostname) → auto-réparation d'IP active"
