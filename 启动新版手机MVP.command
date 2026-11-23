#!/bin/zsh
set -e
cd -- "$(dirname "$0")"
python3 ops/guest_access.py --local "$@"
printf '\n请打开 output/Pivot-Demo-V1.1.3-2026-11-20/00-打开Pivot手机MVP.html\n'
