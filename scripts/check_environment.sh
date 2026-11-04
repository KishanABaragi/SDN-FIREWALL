#!/usr/bin/env bash
set +e
printf '%s\n' '=== OS ==='
lsb_release -a 2>/dev/null || cat /etc/os-release
printf '\n%s\n' '=== Commands ==='
for c in gcc python3 sudo mn ovs-vsctl ovs-ofctl ryu-manager pyenv; do
  if command -v "$c" >/dev/null 2>&1; then printf '%-14s %s\n' "$c" "$(command -v "$c")"; else printf '%-14s MISSING\n' "$c"; fi
done
printf '\n%s\n' '=== Versions ==='
gcc --version 2>/dev/null | head -1
python3 --version 2>&1
sudo mn --version 2>&1 | head -3
ovs-vsctl --version 2>&1 | head -2
if command -v pyenv >/dev/null 2>&1; then pyenv versions; fi
