#!/bin/sh

set -e

wlan_conf="/board-resource/wlan_entery"
wlan_conf_str="/tmp/wlan_entery_str"
wpa_conf="/user-resource/wpa_supplicant.conf"

# Extract WiFi credentials from Elegoo's proprietary format
echo "Extracting WiFi credentials..."
./wifi-network-config-tool "$wlan_conf" extract | strings > "$wlan_conf_str"

num_lines=$(wc -l < "$wlan_conf_str")
if [ "$num_lines" -lt 2 ]; then
    echo "Error: No WiFi credentials found in $wlan_conf"
    exit 1
fi

# Read the first SSID (line 1) and PSK (line 2)
ssid="$(sed '1q;d' "$wlan_conf_str")"
psk="$(sed '2q;d' "$wlan_conf_str")"

if [ -z "$ssid" ] || [ -z "$psk" ]; then
    echo "Error: Failed to parse SSID or PSK from extracted data"
    exit 1
fi

echo "Generating wpa_supplicant.conf for SSID: $ssid"

mkdir -p "$(dirname "$wpa_conf")"

cat > "$wpa_conf" <<EOF
network={
    ssid="$ssid"
    psk="$psk"
}
EOF

echo "wpa_supplicant.conf written to $wpa_conf"


