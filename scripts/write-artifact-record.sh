#!/usr/bin/env bash
set -euo pipefail

for revision in "$FRONTEND_REVISION" "$BACKEND_REVISION" "$MIGRATION_REVISION"; do
  if [[ ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ || "$revision" != "$SOURCE_SHA" ]]; then
    echo 'All published artifacts must come from the selected source commit.' >&2
    exit 1
  fi
done

if [[ -z "$FRONTEND_IMAGE" || -z "$BACKEND_IMAGE" ]]; then
  echo 'Both published image references are required.' >&2
  exit 1
fi

for digest in "$FRONTEND_DIGEST" "$BACKEND_DIGEST"; do
  if [[ ! "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo 'Both published image digests are required.' >&2
    exit 1
  fi
done

checksum=$(shasum -a 256 migrations/atlas.sum | cut -d ' ' -f 1)
if [[ "$checksum" != "$MIGRATION_CHECKSUM" ]]; then
  echo 'Published migration checksum does not match this checkout.' >&2
  exit 1
fi

jq -n \
  --arg repository "$GITHUB_REPOSITORY" --arg revision "$SOURCE_SHA" \
  --arg run_id "$GITHUB_RUN_ID" --arg attempt "$GITHUB_RUN_ATTEMPT" \
  --arg frontend "$FRONTEND_IMAGE" --arg frontend_digest "$FRONTEND_DIGEST" \
  --arg backend "$BACKEND_IMAGE" --arg backend_digest "$BACKEND_DIGEST" \
  --arg checksum "$checksum" \
  '{
    source: {repository: $repository, revision: $revision},
    workflow: {runId: $run_id, attempt: $attempt},
    images: {
      frontend: {tag: $frontend, digest: $frontend_digest,
        reference: (($frontend | split(":")[0]) + "@" + $frontend_digest)},
      backend: {tag: $backend, digest: $backend_digest,
        reference: (($backend | split(":")[0]) + "@" + $backend_digest)}
    },
    migrations: {repository: "preview-environments", tag: $revision,
      url: ("atlas://preview-environments?tag=" + $revision), atlasSumSha256: $checksum}
  }' > artifacts.json
