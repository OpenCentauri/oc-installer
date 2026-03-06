#!/bin/sh

if [[ -f "/app/uninstall.sh" ]]; then
    chmod a+x /app/uninstall.sh
    /app/uninstall.sh || echo "Uninstall failed. Manual cleanup may be required."
else
    echo "Uninstall script not present. Skipping!"
fi