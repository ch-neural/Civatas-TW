# CTW-VA-2026 Paper Source

LaTeX source for the manuscript *Vendor-Specific Refusal Patterns in LLM
Responses to Taiwan-Political Prompts*.

## Build

Requires XeLaTeX + Biber (MacTeX or TeX Live). The paper compiles with
Traditional Chinese support via `xeCJK`; PingFang TC is preferred, with
Noto Sans CJK TC as a fallback.

```sh
make           # 3-pass build → main.pdf
make clean     # remove auxiliary files
```

Or upload `paper_source/` and `../paper_figures/` to Overleaf and set the
compiler to XeLaTeX.

## Drafting status (2026-04-22, **batch 3 complete — full first draft**)

| Section | Status |
|---|---|
| Abstract | **drafted** |
| §1 Introduction | **drafted** |
| §2 Related Work | **drafted** |
| §3 Methodology | **drafted** |
| §4 Results (7 findings) | **drafted** |
| §5 Discussion | **drafted** (5 subsections) |
| §6 Limitations | **drafted** (5 items) |
| §7 Conclusion + Future Work | **drafted** |
| Appendix A: 14 blocked prompts | **drafted** (original Chinese + English gloss) |
| References (`refs.bib`) | **drafted** (19 entries; some placeholders to verify) |

Current line count: 1,486 lines of TeX (~12-15 compiled pages, 6 figures
+ 2 tables + appendix). Static sanity check on all .tex files: all braces
balanced, all `\begin{}`/`\end{}` paired, zero remaining `\todo{}` uses.

## Pre-submission TODOs

Before submitting to arXiv:

1. **Compile locally** with `make` and verify figure rendering (especially
   xeCJK Chinese glyphs in Appendix A and figure labels).
2. **Verify bibliography entries** marked `note = {Placeholder ...}` in
   `refs.bib` — resolve to the exact paper/venue the citation refers to.
   Current placeholders: Röttger 2024 SafetyPrompts, Zheng 2024, Zhang 2024,
   Huang 2023, Sun 2024.
3. **Optionally run flagship-tier sensitivity subset** (n=50 × 5 vendor,
   ~USD 20) to strengthen §6 model-tier-asymmetry disclosure.
4. **Final read-through** for tone, terminology consistency (e.g., always
   ``RoC state institutions'' not ``Taiwan government institutions''), and
   any figure-caption vs body-text number mismatches.
5. **Add ORCID + affiliation** on the title page if desired.

## Figures / tables

Figures are pulled from `../paper_figures/` via the `\graphicspath`
declaration in `main.tex`. Regenerate from the labeled CSV with:

```sh
python3 ../scripts/make_paper_figures.py --all
python3 ../scripts/compute_bootstrap_ci.py
```

`table1_per_vendor_breakdown.tex` provides a booktabs-formatted version
of Table 1 ready for `\input`.
