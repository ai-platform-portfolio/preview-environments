#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -e .env ]; then
  echo '.env already exists; keeping current local credentials.'
  exit 0
fi
umask 077
set -C
{
  printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)"
  printf 'MIGRATOR_PASSWORD=%s\n' "$(openssl rand -hex 24)"
  printf 'RUNTIME_PASSWORD=%s\n' "$(openssl rand -hex 24)"
} > .env
