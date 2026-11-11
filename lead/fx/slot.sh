#!/usr/bin/env bash
# slot.sh <command...>: run a heavy command (tsc, vite build, pytest) in one of 3 machine-wide slots,
# so ten packages do not exhaust the 4 CPUs / 15 GB at once. Waits until a slot is free.
while :; do
  for i in 1 2 3; do
    exec {fd}>"/tmp/fx-slot.$i.lock"
    if flock -n "$fd"; then "$@"; exit $?; fi
    exec {fd}>&-
  done
  sleep 3
done
