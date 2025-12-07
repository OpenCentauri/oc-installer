#!/bin/sh

if [[ -f "/app/uninstall.sh" ]]; then
    set -e
    chmod a+x /app/uninstall.sh
    /app/uninstall.sh
else
    echo "Uninstall script not present. Skipping!"
fi