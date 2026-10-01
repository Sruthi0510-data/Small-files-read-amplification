.PHONY: help test cover experiment tables report proof check preflight verify clean

PY ?= python3
SRC := src

help:
	@echo "test        run the suite"
	@echo "cover       run the suite with branch coverage, failing under 100 percent"
	@echo "experiment  run the experiment, writing JSON under docs/experiments/"
	@echo "tables      regenerate the generated blocks in the README"
	@echo "report      build the HTML report, the diagram and the screenshots"
	@echo "proof       capture the command line and commit the transcript"
	@echo "check       fail if a document quotes a figure the code no longer produces"
	@echo "preflight   authorship, ascii, exit codes, determinism and offline checks"
	@echo "verify      everything, in the order CI runs it"

test:
	PYTHONPATH=$(SRC) $(PY) -m pytest tests

cover:
	PYTHONPATH=$(SRC) $(PY) -m pytest tests --cov=sfa --cov-report=term-missing --cov-branch --cov-fail-under=100

experiment:
	PYTHONPATH=$(SRC) $(PY) experiments/exp01_what_the_plan_cannot_see.py > /dev/null
	PYTHONPATH=$(SRC) $(PY) tools/collect_metrics.py

tables:
	PYTHONPATH=$(SRC) $(PY) tools/render_tables.py

report:
	PYTHONPATH=$(SRC) $(PY) tools/render_diagrams.py
	PYTHONPATH=$(SRC) $(PY) tools/build_report.py
	PYTHONPATH=$(SRC) $(PY) tools/capture_screenshots.py
	PYTHONPATH=$(SRC) $(PY) tools/verify_rendering.py

proof:
	PYTHONPATH=$(SRC) $(PY) tools/proof_of_work.py

check:
	PYTHONPATH=$(SRC) $(PY) tools/check_numbers.py

preflight:
	PYTHONPATH=$(SRC) $(PY) tools/preflight.py

verify: cover experiment tables report proof check
	@echo "verified"

clean:
	rm -rf .pytest_cache .coverage htmlcov coverage.json junit.xml
