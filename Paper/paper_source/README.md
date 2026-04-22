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

## Drafting status (2026-04-22)

| Section | Status |
|---|---|
| Abstract | placeholder |
| §1 Introduction | placeholder |
| §2 Related Work | placeholder |
| §3 Methodology | **drafted (batch 1)** |
| §4.1 Per-vendor landscape | placeholder (batch 2) |
| §4.2 Finding 1 JSD clustering | **drafted (batch 1)** |
| §4.3 Finding 2 Taiwan-statehood blocking | placeholder (batch 2) |
| §4.4 Finding 3 Grok/Kimi low-refusal | placeholder (batch 2) |
| §4.5 Finding 4 2-layer architecture | placeholder (batch 2) |
| §4.6 Finding 5 4-profile taxonomy | placeholder (batch 2) |
| §4.7 Finding 6 prompt bank validity | placeholder (batch 2) |
| §4.8 Finding 7 elasticity | placeholder (batch 2) |
| §5 Discussion | placeholder (batch 2) |
| §6 Limitations | placeholder (batch 3) |
| §7 Conclusion | placeholder (batch 3) |
| Appendix A: 14 blocked prompts | placeholder (batch 3) |
| References | stub (batch 3) |

## Figures / tables

Figures are pulled from `../paper_figures/` via the `\graphicspath`
declaration in `main.tex`. Regenerate from the labeled CSV with:

```sh
python3 ../scripts/make_paper_figures.py --all
python3 ../scripts/compute_bootstrap_ci.py
```

`table1_per_vendor_breakdown.tex` provides a booktabs-formatted version
of Table 1 ready for `\input`.
