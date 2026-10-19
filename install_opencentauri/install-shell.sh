#!/bin/sh
set -e
exec 2>&1
payload=$(CDPATH='' cd "$(dirname "$0")" && pwd)
exec sh "$payload/shell-service.sh" /user-resource/oc-root-shell
