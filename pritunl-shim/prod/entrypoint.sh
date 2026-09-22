#!/usr/bin/env sh
set -e
# Point Pritunl's conf at the shared MongoDB, then run the shim (data ops only).
pritunl set-mongodb "${MONGODB_URI:-mongodb://mongo:27017/pritunl}" >/dev/null 2>&1 || true
exec python3 /shim/shim_app.py
