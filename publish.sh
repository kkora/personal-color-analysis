#!/usr/bin/env bash
# Publish this repo to GitHub as a public repository.
# Requires: gh CLI (https://cli.github.com) authenticated, OR set GITHUB_TOKEN.
set -euo pipefail
REPO_NAME="${1:-personal-color-analysis}"

if command -v gh >/dev/null 2>&1; then
  gh repo create "$REPO_NAME" --public --source . --push \
    --description "Diagram-first personal colour analysis board built with Streamlit"
else
  : "${GITHUB_USER:?Set GITHUB_USER}"; : "${GITHUB_TOKEN:?Set GITHUB_TOKEN (repo scope)}"
  curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
    https://api.github.com/user/repos \
    -d "{\"name\":\"$REPO_NAME\",\"private\":false,\"description\":\"Diagram-first personal colour analysis board built with Streamlit\"}" >/dev/null
  git remote add origin "https://$GITHUB_USER:$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git" 2>/dev/null || true
  git push -u origin main
fi
echo "Published: https://github.com/${GITHUB_USER:-$(gh api user -q .login 2>/dev/null || echo '<you>')}/$REPO_NAME"
