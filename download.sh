#!/bin/bash
set -e

# ---- CONFIG: edit these ----
INTERNET_SSID="Ohadphone"
INTERNET_PASS="pxwj8287"
HOTSPOT_CONN_NAME="PiNet"   # the nmcli connection name for your local hotspot, NOT necessarily the SSID
PACKAGE="python3-picamera2"
# -----------------------------

echo "[1/5] Connecting to $INTERNET_SSID..."
nmcli device wifi connect "$INTERNET_SSID" password "$INTERNET_PASS"

echo "[2/5] Sleeping 10s to let connection settle..."
sleep 10

echo "[3/5] Installing $PACKAGE..."
apt update
apt install -y "$PACKAGE"

echo "[4/5] Sleeping 3s before switching back..."
sleep 3

echo "[5/5] Switching back to $HOTSPOT_CONN_NAME..."
nmcli connection up "$HOTSPOT_CONN_NAME"

echo "Done. Verify with: nmcli device status"
