# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = _build
CLEAN_TARGETS = $(BUILDDIR) $(SOURCEDIR)/_autosummary

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile clean

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

clean:
	rm -rf $(CLEAN_TARGETS)

github: html
	-git branch -D gh-pages
	-git push origin --delete gh-pages
	ghp-import -n -b gh-pages -m "Update documentation" ./_build/html
	git checkout gh-pages
	git push --set-upstream origin gh-pages
	git checkout ${BRANCH}
