#!/usr/bin/env bash
# Regenerates src/graphann/_generated.py from the GraphANN OpenAPI spec.
#
# Requires `datamodel-codegen` (dev dependency: `pip install -e '.[dev]'`).
# Prefer the standalone SDK's bundled spec, then the shared monorepo spec.
# Override either with GRAPHANN_SPEC_PATH.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SPEC="$PYTHON_DIR/api/openapi/spec.yaml"
if [[ ! -f "$SPEC" ]]; then
  SPEC="$PYTHON_DIR/../api/openapi/spec.yaml"
fi
SPEC="${GRAPHANN_SPEC_PATH:-$SPEC}"
if [[ "$SPEC" != /* ]]; then
  SPEC="$PWD/$SPEC"
fi
OUT="$PYTHON_DIR/src/graphann/_generated.py"
HEADER="$SCRIPT_DIR/_generated_header.txt"

if [[ ! -f "$SPEC" ]]; then
  echo "error: spec not found at $SPEC (set GRAPHANN_SPEC_PATH)" >&2
  exit 1
fi

if ! command -v datamodel-codegen >/dev/null 2>&1; then
  echo "error: datamodel-codegen not on PATH (pip install -e '.[dev]')" >&2
  exit 1
fi

cd "$PYTHON_DIR"

datamodel-codegen \
  --input "$SPEC" \
  --input-file-type openapi \
  --output "$OUT" \
  --target-python-version 3.10 \
  --formatters black \
  --disable-timestamp \
  --field-constraints \
  --custom-file-header-path "$HEADER"

# datamodel-codegen's internal --formatters black pass does not always
# match a standalone `black`+`isort` invocation byte-for-byte (observed:
# quote normalization, import order). The repo's pre-commit hook runs
# standalone black then isort on every staged .py file and re-stages the
# result, so run both here too -- otherwise the committed file drifts
# from what the hook rewrites it to on the very next commit, and the
# staleness test flags a false positive.
if command -v black >/dev/null 2>&1; then
  black --quiet "$OUT"
fi
if command -v isort >/dev/null 2>&1; then
  isort --quiet "$OUT"
fi

echo "generated $OUT from $SPEC"
