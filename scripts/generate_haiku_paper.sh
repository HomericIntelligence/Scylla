#!/bin/bash
# Generate all artifacts for the Haiku paper from dryrun3 data.
#
# Usage:
#   bash scripts/generate_haiku_paper.sh [DATA_DIR]
#
# Arguments:
#   DATA_DIR  Path to dryrun3 results directory (default: ~/fullruns/dryrun3)
#
# Outputs:
#   docs/arxiv/haiku/data/     CSV exports
#   docs/arxiv/haiku/tables/   Markdown + LaTeX tables
#   docs/arxiv/haiku/figures/  Vega-Lite JSON + PNG figures
#   docs/arxiv/haiku/paper.pdf Compiled paper (if build.sh exists)

set -euo pipefail

DATA_DIR="${1:-$HOME/fullruns/dryrun3}"
PAPER_DIR="docs/arxiv/haiku"

if [ ! -d "$DATA_DIR" ]; then
    echo "ERROR: Data directory does not exist: $DATA_DIR" >&2
    exit 1
fi

echo "=== Generating Haiku Paper Artifacts ==="
echo "Data source: $DATA_DIR"
echo "Paper directory: $PAPER_DIR"
echo

echo "--- Step 1/3: Exporting data ---"
uv run python scripts/export_data.py --data-dir "$DATA_DIR" --output-dir "$PAPER_DIR/data"
echo

echo "--- Step 2/3: Generating tables ---"
uv run python scripts/generate_tables.py --data-dir "$DATA_DIR" --output-dir "$PAPER_DIR/tables"
echo

echo "--- Step 3/3: Generating figures ---"
uv run python scripts/generate_figures.py --data-dir "$DATA_DIR" --output-dir "$PAPER_DIR/figures"
echo

# Build PDF if build.sh exists
if [ -f "$PAPER_DIR/build.sh" ]; then
    echo "--- Building PDF ---"
    cd "$PAPER_DIR" && bash build.sh
    echo
fi

echo "=== Done ==="
