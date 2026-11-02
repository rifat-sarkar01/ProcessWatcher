#!/bin/sh
# Root is used only to make the Fly volume writable, then privileges are dropped.
set -eu

if [ "$(id -u)" = "0" ]; then
    mkdir -p "${PW_RUNS_DIR:-/data/runs}" "${PW_CACHE_DIR:-/data/cache}"
    chown -R pw:pw /data
    exec setpriv --reuid=pw --regid=pw --init-groups "$@"
fi

exec "$@"
