#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

usage() {
  printf 'Usage: %s {start|stop|restart}\n' "$0" >&2
}

if [ "$#" -ne 1 ]; then
  usage
  exit 2
fi

case "${1-}" in
  start|stop|restart)
    exec "$ROOT/bin/trading-agent-local" "$1"
    ;;
  *)
    usage
    exit 2
    ;;
esac
