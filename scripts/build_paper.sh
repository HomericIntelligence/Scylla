#!/bin/bash
# Research Paper PDF Build Pipeline
# =================================

set -e

echo "Research Paper PDF Build Pipeline"
echo "=================================="
echo ""

SOURCE_DIR="docs"
OUTPUT_DIR="build/paper"
WORK_DIR="$OUTPUT_DIR/latex"

info() { echo "[INFO] $1"; }
success() { echo "[SUCCESS] $1"; }
error() { echo "[ERROR] $1"; }

info "Checking LaTeX dependencies..."
command -v pdflatex >/dev/null 2>&1 || { error "pdflatex not found"; exit 1; }
command -v bibtex >/dev/null 2>&1 || { error "bibtex not found"; exit 1; }
success "LaTeX tools available"

info "Setting up build environment..."
if [ -d "$WORK_DIR" ]; then
    rm -rf "$WORK_DIR"
fi
mkdir -p "$WORK_DIR"

info "Copying source files..."
cp "$SOURCE_DIR/research_paper.tex" "$WORK_DIR/main.tex"
cp "$SOURCE_DIR/references.bib" "$WORK_DIR/"

cd "$WORK_DIR"

info "Preparing document..."
if grep -q "%.*bibliography.*references" main.tex; then
    info "Enabling bibliography reference..."
    sed -i 's/%.*bibliography{bibliography}/bibliography{references}/g' main.tex
    sed -i 's/%.*bibliography{references}/bibliography{references}/g' main.tex
fi

info "Building PDF..."
pdflatex -interaction=nonstopmode main.tex > /dev/null 2>&1
# bibtex returns non-zero when there are no .aux entries or no citations were
# emitted by pdflatex on the first pass; that's expected and non-fatal here.
# Surface unexpected bibtex failures via the log so silent breakage stops happening.
if ! bibtex main > /tmp/bibtex.log 2>&1; then
    echo "warn: bibtex returned non-zero (often expected for citation-free runs); see /tmp/bibtex.log" >&2
fi
pdflatex -interaction=nonstopmode main.tex > /dev/null 2>&1
pdflatex -interaction=nonstopmode main.tex

if [ -f "main.pdf" ]; then
    mv main.pdf "../research_paper.pdf"
    file_size=$(du -h "../research_paper.pdf" | cut -f1)
    success "PDF generated successfully!"
    echo ""
    echo "Output: $OUTPUT_DIR/research_paper.pdf"
    echo "Size: $file_size"
    if [ -f "main.log" ]; then
        pages=$(grep "Output written on main.pdf" main.log | awk '{print $4}' || echo "11 pages")
        info "Compiled to $pages pages"
    fi
else
    error "PDF generation failed"
    if [ -f "main.log" ]; then
        echo "Check main.log for details"
    fi
    exit 1
fi

cd ..
rm -rf "$WORK_DIR"
success "Build complete!"
