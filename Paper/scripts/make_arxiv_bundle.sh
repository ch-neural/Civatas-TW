#!/bin/bash
# Build an arXiv-ready source tarball.
#
# arXiv's build system uses a flat file layout by default. The working
# source uses \graphicspath{{../paper_figures/}} to pull PDFs from a
# sibling directory; for submission we copy figures next to main.tex
# and rewrite graphicspath to the local directory.
#
# Output: ctw_va_2026_arxiv.tar.gz at repo root.

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGING="$(mktemp -d)/arxiv_submission"
mkdir -p "$STAGING"

echo "Staging into $STAGING"

# Copy LaTeX sources (flat, no sections subdirectory)
cp "$REPO_ROOT/paper_source/main.tex"   "$STAGING/main.tex"
cp "$REPO_ROOT/paper_source/refs.bib"   "$STAGING/refs.bib"

# arXiv forbids subdirectories in some configurations; inline sections.
# Instead of \input{sections/foo.tex} we concatenate. Easier: keep the
# sections/ subdirectory (arXiv accepts it) and just fix graphicspath.
mkdir -p "$STAGING/sections"
cp "$REPO_ROOT/paper_source/sections/"*.tex "$STAGING/sections/"

# Copy figures. We want flat layout, so strip any subdirectory.
# Only include files referenced by the paper (save bytes).
cp "$REPO_ROOT/paper_figures/fig1_per_vendor_distribution.pdf"   "$STAGING/"
cp "$REPO_ROOT/paper_figures/fig2_pairwise_jsd_heatmap.pdf"      "$STAGING/"
cp "$REPO_ROOT/paper_figures/fig3_kimi_api_blocked_by_topic.pdf" "$STAGING/"
cp "$REPO_ROOT/paper_figures/fig4_on_task_rate_by_vendor.pdf"    "$STAGING/"
cp "$REPO_ROOT/paper_figures/fig5_hr_sr_elasticity.pdf"          "$STAGING/"
cp "$REPO_ROOT/paper_figures/fig6_on_task_topic_heatmap.pdf"     "$STAGING/"
cp "$REPO_ROOT/paper_figures/fig7_tier_comparison.pdf"           "$STAGING/"
cp "$REPO_ROOT/paper_figures/table1_per_vendor_breakdown.tex"    "$STAGING/"

# Rewrite \graphicspath so arXiv finds figures in the same dir as main.tex
sed -i.bak 's|\\graphicspath{{../paper_figures/}}|\\graphicspath{{./}}|' "$STAGING/main.tex"
# Also fix Table 1 \input path (it was ../paper_figures/...)
sed -i.bak 's|\\input{../paper_figures/table1_per_vendor_breakdown.tex}|\\input{table1_per_vendor_breakdown.tex}|' "$STAGING/sections/results.tex"
rm -f "$STAGING"/*.bak "$STAGING"/sections/*.bak

# Verify critical files are present
echo ""
echo "Staged contents:"
ls -la "$STAGING/"
echo ""
echo "sections/:"
ls -la "$STAGING/sections/"

# Create tarball
OUT="$REPO_ROOT/ctw_va_2026_arxiv.tar.gz"
cd "$(dirname "$STAGING")"
tar czf "$OUT" "$(basename "$STAGING")"
echo ""
echo "✓ Wrote $OUT"
ls -lh "$OUT"

# Suggest sanity check
echo ""
echo "Sanity check: extract + compile locally to verify:"
echo "  mkdir /tmp/test_arxiv && tar xzf $OUT -C /tmp/test_arxiv"
echo "  cd /tmp/test_arxiv/arxiv_submission && xelatex main && xelatex main"
