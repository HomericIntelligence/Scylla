# arXiv Submission Guide

## Current Status

**Status**: ⚠️ **IN PROGRESS** - LaTeX conversion has been partially completed but requires manual fixes before submission.

The conversion from `docs/research_paper.tex` to arXiv-ready submission package has been implemented with the following components:

### Completed

✅ Python converter script (`scripts/build_arxiv_paper.py`)
✅ Build pipeline script (`scripts/build_arxiv_submission.sh`)
✅ Bibliography updates (`docs/arxiv/dryrun/references.bib`) - Added 4 missing @misc entries
✅ Figure handling (25 PDF figures + captions)
✅ Table handling (10 generated .tex files)
✅ Citation mapping ([1]-[10] → BibTeX keys)
✅ Basic Markdown → LaTeX conversion (sections, bold, italic, code, lists)
✅ Unicode math symbol handling (≥, ≤, ×, ±, →)
✅ Abstract and keywords handling
✅ Directory structure and 00README.json

### Known Issues Requiring Manual Fixes

The automated conversion has several edge cases that need manual attention:

1. **Inline Tables**: Complex markdown tables with multi-line cells are not converting correctly
   - Column alignment issues
   - Text split across table rows incorrectly
   - **Location**: Throughout main.tex, especially sections 4-6

2. **Unescaped Underscores**: Variable names like `pass_rate`, `code_quality` in regular text
   - Need to escape as `pass\_rate`, `code\_quality`
   - **Location**: Scattered throughout, especially in metrics sections

3. **Greek Letters**: Unicode characters ρ, Δ, α, σ need math mode
   - Should be: `$\\rho$`, `$\\Delta$`, `$\\alpha$`, `$\\sigma$`
   - **Location**: Statistical sections (correlation, significance tests)

4. **Dollar Signs in Tables**: Pricing tables have literal $ that conflict with math mode
   - Need to escape as `\$` or use proper formatting
   - **Location**: Cost analysis sections

5. **Large Figure Dimensions**: Some figures may have dimension errors
   - May need width adjustments
   - **Location**: Appendix figures

## Files Generated

```
docs/paper-dryrun-arxiv/
├── main.tex                    # Main LaTeX document (needs manual fixes)
├── references.bib              # Bibliography (complete)
├── main.bbl                    # Pre-compiled bibliography (will be generated)
├── 00README.json               # arXiv compiler config (complete)
├── figures/                    # 25 PDF figures (complete)
│   ├── fig01_score_variance_by_tier.pdf
│   ├── fig02_judge_variance.pdf
│   └── ... (23 more)
├── tables/                     # 10 LaTeX tables (complete)
│   ├── tab01_tier_summary.tex
│   ├── tab02_tier_comparison.tex
│   └── ... (8 more)
└── submission.tar.gz           # Will be created after successful compilation
```

## Important: main.tex Manual Edits

⚠️ **The build script will NOT overwrite `main.tex` if it already exists.**

This protects your manual edits. The `build_arxiv_submission.sh` script will:

- Skip LaTeX generation if `main.tex` exists
- Only compile the existing `main.tex` → PDF
- Copy figures, tables, and bibliography
- Create the submission tarball

If you need to regenerate `main.tex` from `research_paper.tex` (discarding manual edits):

```bash
bash scripts/regenerate_main_tex.sh  # Will prompt for confirmation
```

## How to Complete the Conversion

### Option A: Manual LaTeX Editing (Recommended for Quality)

1. **Open `docs/paper-dryrun-arxiv/main.tex` in a LaTeX editor**

2. **Fix inline tables** (search for `\begin{tabular}` in main body):
   - Check column counts match header
   - Ensure all rows end with `\\`
   - Fix any text split across rows
   - Example fix:

     ```latex
     % BEFORE (broken):
     Category & Weight & Description \\
     \hline
     Functional & 35% & File exists; \\
     \hline

     % AFTER (fixed):
     Category & Weight & Description \\
     \hline
     Functional & 35% & File exists; output correct; exit code 0 \\
     \hline
     ```

3. **Escape underscores in text** (search for `_` outside of `\texttt{}`):

   ```latex
   % BEFORE:
   pass_rate = 1.0

   % AFTER:
   pass\_rate = 1.0
   ```

4. **Convert Greek letters to math mode** (search for ρ, Δ, α, σ):

   ```latex
   % BEFORE:
   correlation ρ = 0.95

   % AFTER:
   correlation $\rho$ = 0.95
   ```

5. **Escape dollar signs in tables**:

   ```latex
   % BEFORE:
   Claude Opus & $15.00 & $75.00 \\

   % AFTER:
   Claude Opus & \$15.00 & \$75.00 \\
   ```

6. **Compile and test**:

   ```bash
   cd docs/paper-dryrun-arxiv
   pdflatex main.tex
   bibtex main
   pdflatex main.tex
   pdflatex main.tex
   ```

7. **Create submission tarball**:

   ```bash
   tar -czf submission.tar.gz main.tex main.bbl references.bib 00README.json figures/ tables/
   ```

### Option B: Improve the Converter Script

If you want to automate the fixes, enhance `scripts/build_arxiv_paper.py`:

1. **Better table parsing**: Handle multi-line cells in markdown tables
2. **Comprehensive text escaping**: Escape underscores in all regular text
3. **Greek letter conversion**: Add Unicode → LaTeX math mappings
4. **Dollar sign handling**: Context-aware escaping

Then re-run:

```bash
bash scripts/build_arxiv_submission.sh
```

## arXiv Submission Steps (After Fixes)

1. **Create arXiv account** at <https://arxiv.org/user/register>

2. **Upload submission package**:
   - Go to <https://arxiv.org/submit>
   - Upload `docs/paper-dryrun-arxiv/submission.tar.gz`
   - arXiv will automatically detect main.tex and compile

3. **Enter metadata**:
   - **Title**: Measuring the Value of Enhanced Reasoning in Agentic AI Architectures: An Economic Analysis of Testing Tiers
   - **Authors**: [Your Name]
   - **Abstract**: (Plain text version from research_paper.tex Abstract section)
   - **Primary Category**: cs.AI (Artificial Intelligence)
   - **Secondary Categories**: cs.SE (Software Engineering), cs.LG (Machine Learning)
   - **Comments**: 32 pages, 25 figures, 10 tables

4. **Select license**:
   - **Recommended**: Creative Commons Attribution 4.0 International (CC BY 4.0)
   - **Rationale**: Closest to BSD-3-Clause spirit - permissive, allows commercial use with attribution

5. **Submit for moderation**:
   - arXiv moderators will review (typically 1-2 business days)
   - You'll receive an arXiv ID (e.g., arXiv:2501.12345)

## Validation Checklist

Before submitting to arXiv:

- [ ] PDF compiles without errors (`pdflatex main.tex` succeeds)
- [ ] All citations resolve (no `[?]` markers in PDF)
- [ ] All figures appear correctly
- [ ] All tables render properly
- [ ] Page count reasonable (~25-35 pages)
- [ ] No absolute paths in .tex files
- [ ] No auxiliary files in tarball (.aux, .log, etc.)
- [ ] 00README.json is present and valid
- [ ] Abstract and sections match research_paper.tex content
- [ ] Bibliography complete (all [1]-[10] citations defined)

## Content Preservation

The converter has been designed to preserve all content from `research_paper.tex` without changes:

- ✅ All data values, statistics, and numerical results unchanged
- ✅ All 7 testing tiers (T0-T6) descriptions intact
- ✅ All metrics formulas and definitions preserved
- ✅ All experimental results and findings maintained
- ✅ Tone cleanup applied (contractions removed: don't → do not)
- ⚠️ Formatting converted to LaTeX (structure preserved, presentation adapted)

## Known Limitations

1. **Dryrun Data**: Paper contains N=1 dryrun data (Hello World task only)
2. **Manual Review Needed**: Automated conversion requires manual LaTeX fixes
3. **Figure Quality**: PDFs generated from Python (matplotlib) - check resolution
4. **Table Complexity**: Complex markdown tables may need manual restructuring

## Tools Required

- **LaTeX Distribution**: TeX Live 2023 or later (already installed)
- **Compilers**: pdflatex, bibtex (already available)
- **Python 3.10+**: For converter script (via uv)
- **arXiv Account**: For submission

## Support

- **Converter Script**: `scripts/build_arxiv_paper.py`
- **Build Pipeline**: `scripts/build_arxiv_submission.sh`
- **Source Paper**: `docs/research_paper.tex` (Canonical LaTeX source)
- **arXiv Help**: <https://info.arxiv.org/help/submit_tex.html>

## Next Steps

1. **Manually fix LaTeX issues** listed above in main.tex
2. **Test compilation** until PDF builds successfully
3. **Review PDF** for content accuracy and formatting
4. **Create tarball** after successful compilation
5. **Submit to arXiv** when ready

---

**Last Updated**: 2026-02-05
**Status**: Awaiting manual LaTeX fixes before submission
