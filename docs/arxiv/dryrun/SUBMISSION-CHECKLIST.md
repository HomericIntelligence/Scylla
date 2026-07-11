# arXiv Submission Checklist

**Paper**: "Taming Scylla: Measuring Cost-of-Pass in Agentic CLI Tools"
**Date**: 2026-02-07
**Submission Package**: `arxiv-submission.tar.gz` (398KB)

---

## Pre-Submission Verification ✅

- [x] **LaTeX compilation successful** (0 errors, 0 unresolved references)
- [x] **Bibliography cleaned** (10 cited entries, reduced from 36)
- [x] **All figures included** (24 PDFs in tarball)
- [x] **Table file included** (tab04_criteria_performance.tex)
- [x] **00README.json present** (arXiv configuration)
- [x] **paper.bbl pre-compiled** (required for arXiv)
- [x] **PDF validated** (494KB, 32 pages)

---

## Tarball Contents (29 files)

```
paper.tex                              # Main source (74KB)
paper.bbl                              # Pre-compiled bibliography (2.5KB)
references.bib                         # Bibliography source (3.2KB)
00README.json                          # arXiv configuration (175 bytes)
figures/fig01-fig26.pdf               # 24 figure PDFs (missing fig12, fig23, fig27)
tables/tab04_criteria_performance.tex  # 1 table file
```

---

## arXiv Submission Steps

### 1. Upload to arXiv

1. Go to <https://arxiv.org/submit>
2. Click "Start New Submission"
3. Select category: **cs.SE** (Software Engineering) or **cs.AI** (Artificial Intelligence)
4. Upload: `arxiv-submission.tar.gz`

### 2. arXiv Processing

arXiv will:

- Extract tarball
- Read `00README.json` for compiler settings
- Run: `pdflatex paper.tex` (no bibtex - uses paper.bbl)
- Validate PDF output
- Check file sizes and formats

### 3. Expected Warnings (Non-Critical)

- **PDF 1.7 version warnings**: 4 figures generated as PDF 1.7 (arXiv prefers 1.5)
  - Figures: fig02, fig07, fig09, fig14
  - Will render correctly, may trigger warning

- **Hfootnote.1 warning**: `\thanks{}` footnote in title
  - Known LaTeX/hyperref issue, non-blocking

### 4. Metadata Entry

**Title**: Taming Scylla: Measuring Cost-of-Pass in Agentic CLI Tools

**Authors**: [Fill in author names and affiliations]

**Abstract**: [Copy from paper.tex lines 69-86]

**Categories**:

- Primary: cs.SE (Software Engineering)
- Secondary: cs.AI (Artificial Intelligence), cs.LG (Machine Learning)

**Keywords**: LLM agents, software engineering benchmarks, cost-of-pass, multi-agent systems, prompt engineering, ablation studies, evaluation frameworks, CLI tools, agentic AI

**Comments**: 32 pages, 24 figures, 1 table. Dryrun experiment using Hello World baseline.

---

## Post-Submission

### If Compilation Fails

1. **Check arXiv logs** for specific errors
2. **Common issues**:
   - Missing package: Add to LaTeX preamble
   - Figure not found: Verify all PDFs in tarball
   - Bibliography issues: Ensure paper.bbl is valid
   - Overfull hbox: Cosmetic, can ignore

3. **Re-submission**:
   - Fix issues in `docs/arxiv/dryrun/paper.tex`
   - Re-compile: `pdflatex → bibtex → pdflatex × 2`
   - Re-create tarball
   - Upload new version

### Announcement Draft

```
We present Scylla, a framework for measuring Cost-of-Pass (CoP) in agentic
CLI tools through systematic ablation studies across 7 testing tiers (T0-T6).
Key findings: quality converges on simple tasks (ceiling effect), but cost
varies 3.8× ($0.065 to $0.247), revealing a Token Efficiency Chasm where
architectural complexity doubles token consumption without quality gains.

Paper: [arXiv link]
Code: https://github.com/HomericIntelligence/Scylla
```

---

## Files on Disk

**Submission tarball**: `docs/arxiv/dryrun/arxiv-submission.tar.gz`
**Source files**: `docs/arxiv/dryrun/`
**Compiled PDF**: `docs/arxiv/dryrun/paper.pdf`

---

## Next Steps

1. ✅ Review `paper.pdf` one final time
2. ⬜ Upload `arxiv-submission.tar.gz` to arXiv
3. ⬜ Monitor arXiv processing (24-48 hours)
4. ⬜ Announce on Twitter/HN/Reddit after publication
