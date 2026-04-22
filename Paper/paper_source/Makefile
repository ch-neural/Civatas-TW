# CTW-VA-2026 paper build.
#
# Primary toolchain: XeLaTeX + Biber (required for xeCJK Chinese support).
# Run `make` to do a full 3-pass compile. Run `make clean` to wipe
# auxiliary files.
#
# On macOS install MacTeX from https://www.tug.org/mactex/. Alternatively
# copy the `paper_source/` directory to Overleaf.

MAIN = main
TEX  = xelatex -halt-on-error -interaction=nonstopmode

.PHONY: all clean once

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex sections/*.tex refs.bib
	$(TEX) $(MAIN)
	biber $(MAIN) || true
	$(TEX) $(MAIN)
	$(TEX) $(MAIN)

once: $(MAIN).tex
	$(TEX) $(MAIN)

clean:
	rm -f *.aux *.log *.out *.toc *.bbl *.bcf *.blg *.run.xml *.synctex.gz sections/*.aux
	rm -f $(MAIN).pdf
