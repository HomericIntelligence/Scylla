#!/usr/bin/env bash
# Build arXiv paper and submission package
# Run from this directory: cd docs/arxiv/haiku && ./build.sh
# Requires a LaTeX engine on PATH (tectonic preferred, or a texlive pdflatex).

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "=========================================="
echo "Building arXiv Paper: Navigating Scylla with Haiku"
echo "=========================================="
echo ""

# Step 1: Clean auxiliary files
echo "[1/4] Cleaning auxiliary files..."
rm -f paper.aux paper.log paper.out paper.toc paper.lof paper.lot paper.blg paper.bbl
echo "✓ Cleaned"
echo ""

# Step 2: Compile with available engine
echo "[2/4] Compiling LaTeX..."

if command -v tectonic &> /dev/null; then
    # Tectonic: self-contained engine (handles bibtex + multiple passes automatically)
    echo "  Using tectonic engine"
    tectonic paper.tex || {
        echo "✗ Error during tectonic compilation"
        exit 1
    }
elif command -v pdflatex &> /dev/null; then
    # Traditional: 4-step pdflatex + bibtex cycle
    echo "  Using pdflatex engine (4-step cycle)"
    echo "  Pass 1/4: pdflatex (generating aux)..."
    pdflatex -interaction=nonstopmode -halt-on-error paper.tex > /dev/null 2>&1 || {
        echo "✗ Error during first pdflatex pass"
        echo "Check paper.log for details"
        exit 1
    }

    echo "  Pass 2/4: bibtex (resolving citations)..."
    bibtex paper > /dev/null 2>&1 || {
        echo "✗ Error during bibtex pass"
        echo "Check paper.blg for details"
        exit 1
    }

    echo "  Pass 3/4: pdflatex (inserting citations)..."
    pdflatex -interaction=nonstopmode -halt-on-error paper.tex > /dev/null 2>&1 || {
        echo "✗ Error during second pdflatex pass"
        exit 1
    }

    echo "  Pass 4/4: pdflatex (finalizing references)..."
    pdflatex -interaction=nonstopmode -halt-on-error paper.tex > /dev/null 2>&1 || {
        echo "✗ Error during third pdflatex pass"
        exit 1
    }
else
    echo "✗ No LaTeX engine found. Install tectonic (https://tectonic-typesetting.github.io)"
    echo "  or a texlive distribution (pdflatex + bibtex) on your system."
    exit 1
fi

echo "✓ Compilation successful"
echo ""

# Step 3: Validate output
echo "[3/4] Validating output..."

# Check PDF exists
if [ ! -f "paper.pdf" ]; then
    echo "✗ Error: paper.pdf not generated"
    exit 1
fi

# Check file size
PDF_SIZE=$(stat -f%z "paper.pdf" 2>/dev/null || stat -c%s "paper.pdf" 2>/dev/null)
if [ "${PDF_SIZE}" -lt 10000 ]; then
    echo "✗ Warning: PDF file seems too small (${PDF_SIZE} bytes)"
    exit 1
fi

# Check for LaTeX errors (only relevant for pdflatex path)
if [ -f "paper.log" ]; then
    ERROR_COUNT=$(grep -c "^!" paper.log 2>/dev/null || echo "0")
    ERROR_COUNT=${ERROR_COUNT:-0}
    if [ "${ERROR_COUNT}" -gt 0 ]; then
        echo "✗ Warning: ${ERROR_COUNT} LaTeX errors found in log"
    fi

    # Check for unresolved references
    UNRESOLVED=$(grep "??" paper.log 2>/dev/null | grep -vc pdfTeX || echo "0")
    UNRESOLVED=${UNRESOLVED:-0}
    if [ "${UNRESOLVED}" -gt 0 ]; then
        echo "✗ Warning: ${UNRESOLVED} unresolved references"
    fi
fi

# Get page count if pdfinfo available
if command -v pdfinfo &> /dev/null; then
    PAGE_COUNT=$(pdfinfo paper.pdf 2>/dev/null | grep "Pages:" | awk '{print $2}')
    echo "  PDF: ${PDF_SIZE} bytes, ${PAGE_COUNT} pages"
else
    echo "  PDF: ${PDF_SIZE} bytes"
fi

echo "✓ Validation passed"
echo ""

# Step 4: Create submission tarball
echo "[4/4] Creating submission tarball..."

# Build list of table tex files that exist
TABLE_FILES=$(ls tables/*.tex 2>/dev/null || echo "")

# Derive the figure list from \includegraphics calls in paper.tex so the
# tarball contains exactly the figures the paper references — no more, no less.
# Append .png to bare names; prefix figures/ for any non-absolute path.
FIGURE_FILES=$(grep -oE '\\includegraphics(\[[^]]*\])?\{[^}]+\}' paper.tex \
    | sed -E 's/.*\{([^}]+)\}/\1/' \
    | sort -u \
    | awk '{ if ($0 !~ /\.[a-zA-Z0-9]+$/) $0 = $0 ".png"; if ($0 !~ /^\//) $0 = "figures/" $0; print }')

# Verify each referenced figure exists on disk before tarring.
MISSING_FIGS=""
for f in ${FIGURE_FILES}; do
    [ -f "$f" ] || MISSING_FIGS="${MISSING_FIGS} $f"
done
if [ -n "${MISSING_FIGS}" ]; then
    echo "✗ Error: paper references figures not present on disk:${MISSING_FIGS}"
    exit 1
fi

tar -czf arxiv-submission.tar.gz \
    paper.tex \
    references.bib \
    ${FIGURE_FILES} \
    ${TABLE_FILES} 2>/dev/null || {
    echo "✗ Error creating tarball"
    exit 1
}

TARBALL_SIZE=$(stat -f%z "arxiv-submission.tar.gz" 2>/dev/null || stat -c%s "arxiv-submission.tar.gz" 2>/dev/null)
FILE_COUNT=$(tar -tzf arxiv-submission.tar.gz | wc -l | tr -d ' ')

echo "✓ Tarball created: ${TARBALL_SIZE} bytes, ${FILE_COUNT} files"
echo ""

# Clean auxiliary files (arXiv generates .bbl from .bib)
echo "Cleaning auxiliary files..."
rm -f paper.aux paper.log paper.out paper.toc paper.lof paper.lot paper.blg paper.bbl
echo "✓ Cleaned"
echo ""

# Summary
echo "=========================================="
echo "Build Complete!"
echo "=========================================="
echo ""
echo "Output files:"
echo "  - paper.pdf (compiled paper)"
echo "  - arxiv-submission.tar.gz (upload to arXiv)"
echo ""
echo "Next steps:"
echo "  1. Review paper.pdf for correctness"
echo "  2. Upload arxiv-submission.tar.gz to arxiv.org"
echo ""
