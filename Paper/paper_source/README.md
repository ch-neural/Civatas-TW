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

## Drafting status (2026-04-22, batch 2 complete)

| Section | Status |
|---|---|
| Abstract | placeholder |
| §1 Introduction | placeholder |
| §2 Related Work | placeholder |
| §3 Methodology | **drafted** |
| §4.1 Per-vendor landscape | **drafted** |
| §4.2 Finding 1 JSD clustering | **drafted** |
| §4.3 Finding 2 Taiwan-statehood blocking | **drafted** |
| §4.4 Finding 3 Grok/Kimi low-refusal | **drafted** |
| §4.5 Finding 4 2-layer architecture | **drafted** |
| §4.6 Finding 5 4-profile taxonomy | **drafted** |
| §4.7 Finding 6 prompt bank validity | **drafted** |
| §4.8 Finding 7 elasticity | **drafted** |
| §5 Discussion | **drafted** (5 subsections) |
| §6 Limitations | placeholder (batch 3) |
| §7 Conclusion | placeholder (batch 3) |
| Appendix A: 14 blocked prompts | placeholder (batch 3) |
| References | stub (batch 3) |

Current line count: ~1,100 lines of TeX (est. 8-10 compiled pages before
Introduction, Related Work, Limitations, Conclusion, Appendix).

## Figures / tables

Figures are pulled from `../paper_figures/` via the `\graphicspath`
declaration in `main.tex`. Regenerate from the labeled CSV with:

```sh
python3 ../scripts/make_paper_figures.py --all
python3 ../scripts/compute_bootstrap_ci.py
```

`table1_per_vendor_breakdown.tex` provides a booktabs-formatted version
of Table 1 ready for `\input`.
