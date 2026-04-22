# arXiv Submission Metadata

Copy-paste values for the arXiv submission form
([arxiv.org/submit](https://arxiv.org/submit)).

## 1. Title

```
Vendor-Specific Refusal Patterns in LLM Responses to Taiwan-Political
Prompts: Evidence Against a Monolithic East-West Alignment Dichotomy
```

(99 characters. arXiv title field accepts up to 240 characters with no
hard requirement; single-line titles without line breaks are standard.)

## 2. Authors

```
Cheng-Hsun Tseng
```

**Affiliation**: Sunplus Innovation Technology, Hsinchu, Taiwan

**Email (for arXiv correspondence)**: chtseng.neural@gmail.com

**ORCID** (optional, recommended): *add if you have one; skip otherwise*

## 3. Abstract (plain text, no LaTeX)

```
We audit the refusal behavior of five commercial large language models
- OpenAI gpt-4o-mini, Google gemini-2.5-flash-lite, xAI grok-4-fast,
DeepSeek V3.2, and Moonshot Kimi k2 - on a bank of 200 Traditional
Chinese prompts engineered to probe Taiwan political sensitivity,
yielding 1,000 prompt-vendor observations. Hand-labeled responses are
classified along a four-category taxonomy (hard refusal, soft refusal,
on-task, API-blocked), with all statistics reported under prompt-level
paired bootstrap 95% BCa confidence intervals. Four findings are
robust at the CI level. First, the intuitive East-West alignment
dichotomy is empirically refuted: the two Chinese-owned vendors
produce the most divergent refusal distributions in the panel (JSD
0.200, CI [0.149, 0.256]), while DeepSeek's aggregate distribution is
statistically indistinguishable from the U.S. vendors. Second, Kimi's
7% API-level content filter blocks 4 of 50 neutral factual prompts
about Republic of China state institutions, supporting a
Taiwan-statehood blocking rather than sovereignty-opinion blocking
characterization. Third, a topic-stratified view reveals a
four-profile vendor taxonomy, with DeepSeek's sovereignty on-task
rate collapsing to 10.3% ([2.6, 23.3]) while its non-sovereignty
behavior matches Western vendors - a disjoint-CI collapse unique in
our panel. Fourth, a HR-to-SR elasticity analysis distinguishes
responsive-RLHF vendors from ceiling-bound and stiff-RLHF vendors.
All code, prompts, per-response logs, hand-labels, and the auxiliary
AI-judge audit trail are released. For LLM agent simulation studies
in politically-sensitive domains, we recommend treating vendor as a
first-class experimental variable and reporting layer-stratified
refusal metrics.
```

(1,789 characters / ~253 words. arXiv limit is 1,920 characters or 300
words, whichever is shorter. We are within both limits.)

## 4. Comments field

```
25 pages, 6 figures, 2 tables, appendix with full 14-prompt
API-blocked enumeration. Code, prompts, per-response logs, hand-labels,
and AI-judge audit trail released at
https://github.com/chtseng-neural/Civatas-TW
```

## 5. Subject categories

Primary (choose exactly one):

```
cs.CL  (Computation and Language)
```

Cross-listed / secondary (choose up to 3):

```
cs.CY  (Computers and Society)
cs.AI  (Artificial Intelligence)
stat.AP  (Statistics - Applications)
```

**Rationale for this assignment**:

- `cs.CL` is the canonical category for LLM-related studies and will
  be read by the core NLP / alignment audience.
- `cs.CY` (Computers and Society) is warranted because the paper's
  central claims concern vendor-level alignment policy, with direct
  implications for downstream simulation studies in political contexts
  — a theme squarely within Computers and Society.
- `cs.AI` is customary for LLM-audit papers and broadens the readership.
- `stat.AP` is appropriate because the paper reports paired bootstrap
  BCa confidence intervals throughout and argues multiple findings from
  CI-disjoint evidence; applied-statistics readers may find the
  methodological contribution relevant.

## 6. MSC / ACM classifications (optional)

Usually safe to leave blank for cs.* papers. If arXiv prompts you:

- ACM-CCS: `Computing methodologies → Natural language processing`
  and `Social and professional topics → Computing / technology policy`
- MSC: leave blank (statistics primary class does not need MSC)

## 7. License

Recommended: **CC BY 4.0**
(arXiv option: "Creative Commons Attribution 4.0 International").

This permits reuse with attribution and is the standard choice for
open-research papers releasing datasets and code.

## 8. Report number

Leave blank (no institutional report series).

## 9. Journal reference

Leave blank on first arXiv submission. If the paper is later accepted
to a venue (workshop, journal), update the arXiv listing's "Journal
reference" field at that time.

---

## Submission Checklist

Before clicking "Submit" on arXiv:

- [ ] Final `main.pdf` compiled cleanly from source (this repo at
      current commit).
- [ ] All 19 bibliography entries resolve; no "Citation undefined"
      warnings in the latest `main.log`.
- [ ] Traditional Chinese renders correctly in §3.2, §4.3, and
      Appendix A (visible PingFang TC glyphs, not tofu boxes).
- [ ] Author byline reads "Cheng-Hsun Tseng" with affiliation
      "Sunplus Innovation Technology, Hsinchu, Taiwan".
- [ ] Corresponding email `chtseng.neural@gmail.com` is current.
- [ ] GitHub repo URL in the abstract/comments field is public
      (or will be by the time arXiv announces the paper — typically
      1 business day after submission).
- [ ] The `responses_n200.csv` + `responses_n200.ai_suggest.jsonl` +
      `04_REFUSAL_LABELING_RULES.md` are committed and will be
      accessible at the cited GitHub URL.

## Day-of-submission tips

- **Submit Monday–Tuesday EST** for maximum visibility: arXiv
  announcements run each weekday at 20:00 EST, and Monday/Tuesday
  listings see the most weekday traffic.
- **Source or PDF**: submit the XeLaTeX source bundle (zip of
  `paper_source/` with `../paper_figures/` figures copied in and the
  `\graphicspath` adjusted) rather than a PDF-only submission. arXiv
  prefers source when available and will rebuild a canonical PDF.
- **Reserve a handle**: you can reserve a paper ID before uploading.
  After submission, the listing becomes public once the daily
  announcement runs.

## After submission

- Tweet / LinkedIn share the arXiv URL with a one-sentence hook
  (suggested: "DeepSeek is statistically indistinguishable from
  OpenAI on refusal shape — but its sovereignty on-task rate collapses
  to 10%. A 5-vendor audit of LLM refusal on Taiwan politics.").
- Email close collaborators / relevant researchers (the cited
  authors of Ko 2026, Naseh 2025, Röttger 2024) for feedback.
- Track citations via Semantic Scholar / Google Scholar alerts
  on the arXiv ID.
