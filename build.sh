#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/src"
gcc -Wall -Wextra -pthread logger_server.c -o logger_server
gcc -Wall -Wextra -pthread app_server.c -o app_server
gcc -Wall -Wextra client.c -o client
printf '\nBuild successful. Binaries are in %s\n' "$PWD"
