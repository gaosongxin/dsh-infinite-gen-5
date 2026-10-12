#!/usr/bin/env bash
# Sync upstream Minglink/dsh-infinite-gen-5 into this fork's darwin-x64 changes.
#
# Usage:
#   ./sync-upstream.sh            # fetch upstream and rebase our changes
#   ./sync-upstream.sh --check    # only show what upstream has; change nothing
#   ./sync-upstream.sh --merge    # use merge instead of rebase
#
# On rebase conflict: edit files, then
#   git add <file> && git rebase --continue
# or abort with: git rebase --abort
set -euo pipefail

cd "$(dirname "$0")"

BRANCH="${IG5_BRANCH:-darwin-x64}"
MODE="${1:-rebase}"

if ! git remote get-url upstream >/dev/null 2>&1; then
  echo "[init] adding upstream remote"
  git remote add upstream https://github.com/Minglink/dsh-infinite-gen-5.git
fi

echo "[1/4] fetching upstream"
git fetch upstream --tags --prune

CURRENT="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT" != "$BRANCH" ]; then
  echo "      switching to ${BRANCH} (from ${CURRENT})"
  git checkout "$BRANCH"
fi

echo
echo "[2/4] upstream commits"
UPSTREAM_HEAD="$(git rev-parse upstream/master)"
LOCAL_BASE="$(git merge-base HEAD upstream/master)"
if [ "$UPSTREAM_HEAD" = "$LOCAL_BASE" ]; then
  echo "      already up to date"
  exit 0
fi
git log --oneline "$LOCAL_BASE..upstream/master" | sed 's/^/      /'
echo
echo "      our commits:"
git log --oneline "$LOCAL_BASE..HEAD" | sed 's/^/      /'

if [ "$MODE" = "--check" ]; then
  echo
  echo "[--check] nothing changed. Drop --check to sync."
  exit 0
fi

echo
echo "[3/4] syncing (${MODE})"
if [ "$MODE" = "--merge" ]; then
  git merge upstream/master -m "chore: merge upstream $(git rev-parse --short upstream/master)"
else
  git rebase upstream/master
fi

echo
echo "[4/4] verifying"
node --check engine_runtime.js
node --check source/host_platform.js
node --check source/worker_transport.js
echo "      syntax OK"
echo
echo "changed files:"
git diff --stat "$(git merge-base HEAD upstream/master)"..HEAD -- \
  engine_runtime.js source/host_platform.js source/worker_transport.js \
  adapters/ghidra/local-project-path/build_patch.py | sed 's/^/      /'

cat <<'EOF'

Next steps:
  1. Deploy to the plugin directory (keep runtimes/ and third_party/):
       rsync -av --delete --exclude='runtimes' --exclude='third_party' \
             --exclude='.git' --exclude='.ig5-local' ./ ~/.dsh/plugins/dsh-infinite-gen-5/
  2. Restart DSH (no --expose-internals, so code does not hot reload)
  3. Run ig5_doctor and confirm runtimeReady / startupVerified are true
EOF
