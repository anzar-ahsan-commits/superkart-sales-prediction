#!/usr/bin/env bash
set -euo pipefail

# Run from the repository root after docker compose up -d.
network_name="superkart-sales-prediction_default"
network_id=$(docker network inspect "$network_name" --format '{{.Id}}')
bridge="br-${network_id:0:12}"

ip link show "$bridge" >/dev/null
echo "Allowing internal API traffic on $bridge"

sudo iptables-legacy -C FORWARD \
    -i "$bridge" -o "$bridge" \
    -p tcp --dport 7860 \
    -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT 2>/dev/null ||
sudo iptables-legacy -I FORWARD 1 \
    -i "$bridge" -o "$bridge" \
    -p tcp --dport 7860 \
    -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT

sudo iptables-legacy -C FORWARD \
    -i "$bridge" -o "$bridge" \
    -p tcp --sport 7860 \
    -m conntrack --ctstate ESTABLISHED -j ACCEPT 2>/dev/null ||
sudo iptables-legacy -I FORWARD 1 \
    -i "$bridge" -o "$bridge" \
    -p tcp --sport 7860 \
    -m conntrack --ctstate ESTABLISHED -j ACCEPT

echo "Scoped network rules are in place."
