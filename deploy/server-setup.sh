#!/bin/bash
# One-time set-up of a fresh Ubuntu 24.04 server (deploy/RUNBOOK.md step 2): a DigitalOcean
# droplet or an Oracle Cloud VM. Run as root (DigitalOcean) or with sudo (Oracle, user ubuntu):
#   curl -fsSL https://raw.githubusercontent.com/PowerPii/csit321-secure-pay/main/deploy/server-setup.sh -o setup.sh
#   less setup.sh && sudo bash setup.sh
#
# - security updates installed now and every day after (unattended-upgrades)
# - Docker Engine + Compose plugin from Docker's own apt repository
# - a 'securepay' user (sudo + docker) that signs in with your SSH keys
# - Oracle images only: their REJECT-all iptables rules replaced by ufw, and the public IP
#   made local so containers can reach the server's own public names (webhooks to the shop)
# - SSH: keys only, no root sign-in
# - firewall: only 22, 80 and 443 open
# - 2 GB swap, so image builds do not run a 4 GB droplet out of memory
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get -y upgrade
apt-get -y install ca-certificates curl git ufw unattended-upgrades openssl
dpkg-reconfigure -f noninteractive unattended-upgrades

# Docker (https://docs.docker.com/engine/install/ubuntu/)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# Deploy user, signing in with the same SSH keys as root
if ! id securepay >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" securepay
fi
usermod -aG sudo,docker securepay
install -d -m 700 -o securepay -g securepay /home/securepay/.ssh
# The keys of whoever ran this: root on DigitalOcean, the sudo user (ubuntu) on Oracle, where
# root's own authorized_keys only says "log in as ubuntu".
keys=/root/.ssh/authorized_keys
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
  keys="$(getent passwd "$SUDO_USER" | cut -d: -f6)/.ssh/authorized_keys"
fi
install -m 600 -o securepay -g securepay "$keys" /home/securepay/.ssh/authorized_keys
# sudo without a password (the account has none; it signs in with SSH keys only)
echo "securepay ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/securepay
chmod 440 /etc/sudoers.d/securepay

# SSH: keys only, no root
cat > /etc/ssh/sshd_config.d/10-securepay.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
systemctl reload ssh

# Oracle's Ubuntu images ship iptables rules that reject everything but SSH, restored at boot
# by netfilter-persistent. Replace them with ufw below.
if [ -e /etc/iptables/rules.v4 ] && grep -q REJECT /etc/iptables/rules.v4; then
  apt-get -y purge netfilter-persistent iptables-persistent || true
  iptables -P INPUT ACCEPT
  iptables -F INPUT
fi

# Firewall. Docker publishes only Caddy's 80/443 (compose.prod.yaml), so nothing else is open
# even though Docker's own rules bypass ufw.
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

# Swap
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

# On clouds that NAT the public IP (Oracle, AWS, Azure) the server does not hold its own public
# address, so a container calling shop.<domain> (the worker's webhooks) would leave the cloud
# and may not come back. With the address on the loopback interface, Docker routes it straight
# to Caddy. DigitalOcean droplets already hold their IP, so nothing changes there.
public_ip="$(curl -fsS https://api.ipify.org || true)"
if [ -n "$public_ip" ] && ! ip -4 addr | grep -q "inet $public_ip/"; then
  printf '%s\n' \
    "[Unit]" \
    "Description=Own public IP on loopback (container hairpin for SecurePay)" \
    "After=network-online.target" \
    "Wants=network-online.target" \
    "" \
    "[Service]" \
    "Type=oneshot" \
    "RemainAfterExit=yes" \
    "ExecStart=/usr/sbin/ip addr replace $public_ip/32 dev lo" \
    "" \
    "[Install]" \
    "WantedBy=multi-user.target" > /etc/systemd/system/securepay-public-ip.service
  systemctl daemon-reload
  systemctl enable --now securepay-public-ip.service
  echo "Public IP $public_ip put on the loopback interface (NAT cloud)."
fi

echo
echo "Done. From now on sign in as: ssh securepay@${public_ip:-<server-ip>}"
echo "(root sign-in is now off; keep this session open until the new one works)"
