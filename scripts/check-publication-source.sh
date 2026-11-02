#!/usr/bin/env bash
set -euo pipefail

if [[ ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ || "$(git rev-parse HEAD)" != "$SOURCE_SHA" ]]; then
  echo 'Source checkout does not match the selected full commit SHA.' >&2
  exit 1
fi

if [[ "$GITHUB_EVENT_NAME" == pull_request ]]; then
  if [[ ! "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
    echo 'A PR number is required.' >&2
    exit 1
  fi

  gh api "repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER" |
    jq -e --arg sha "$SOURCE_SHA" --arg repo "$GITHUB_REPOSITORY" --arg publish "${PUBLISH:-true}" \
      '.state == "open" and .head.sha == $sha and
        ($publish == "false" or .head.repo.full_name == $repo)' >/dev/null
elif [[ "$GITHUB_REF" == refs/heads/main ]]; then
  current=$(gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main" --jq '.object.sha')
  if [[ "$current" != "$SOURCE_SHA" ]]; then
    echo 'Main has advanced beyond this publication run.' >&2
    exit 1
  fi
elif [[ "${PUBLISH:-true}" != false ]]; then
  echo 'Publication requires a same-repository PR or the main branch.' >&2
  exit 1
fi
