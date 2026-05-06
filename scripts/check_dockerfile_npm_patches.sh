#!/usr/bin/env bash
# Compare npm packages pinned in docker/Dockerfile against the latest version
# published on the npm registry, so the pins do not drift silently.
#
# Exit code: 0 if all pins match latest; 1 if any are stale.
#
# See docs/dev/dockerfile-npm-cve-patches.md for the maintenance workflow.

set -euo pipefail

DOCKERFILE="docker/Dockerfile"
PACKAGES=(cross-spawn glob minimatch tar)

if ! command -v npm >/dev/null 2>&1; then
    echo "error: npm not found on PATH" >&2
    exit 2
fi

if [[ ! -f "$DOCKERFILE" ]]; then
    echo "error: $DOCKERFILE not found (run from repo root)" >&2
    exit 2
fi

stale=0
printf "%-13s  %-10s  %-10s  %s\n" "package" "pinned" "latest" "status"
printf "%-13s  %-10s  %-10s  %s\n" "-------" "------" "------" "------"

for pkg in "${PACKAGES[@]}"; do
    # Pinned version: first match of `<pkg>@<version>` in the Dockerfile.
    pinned=$(grep -oE "${pkg}@[0-9]+\\.[0-9]+\\.[0-9]+" "$DOCKERFILE" | head -1 | cut -d@ -f2 || true)
    if [[ -z "${pinned:-}" ]]; then
        printf "%-13s  %-10s  %-10s  %s\n" "$pkg" "?" "?" "NOT FOUND"
        stale=1
        continue
    fi

    latest=$(npm view "$pkg" version 2>/dev/null || true)
    if [[ -z "${latest:-}" ]]; then
        printf "%-13s  %-10s  %-10s  %s\n" "$pkg" "$pinned" "?" "REGISTRY ERROR"
        stale=1
        continue
    fi

    if [[ "$pinned" == "$latest" ]]; then
        status="ok"
    else
        status="STALE"
        stale=1
    fi
    printf "%-13s  %-10s  %-10s  %s\n" "$pkg" "$pinned" "$latest" "$status"
done

exit "$stale"
