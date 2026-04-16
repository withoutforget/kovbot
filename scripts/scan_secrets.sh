#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PATTERN='(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{30,}|-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----|xox[baprs]-[0-9A-Za-z-]{10,}|ghp_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{20,}|ya29\.[0-9A-Za-z\-_]+)'

echo "Scanning tracked files only (git ls-files)..."
git ls-files -z | xargs -0 rg -n "$PATTERN" -S || true

echo
echo "Heuristic scan for key-like assignments (tracked files only)..."
git ls-files -z | xargs -0 rg -n '(api[_-]?key|secret|token|password)\s*[:=]' -S || true

