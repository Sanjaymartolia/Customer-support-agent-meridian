# Convenience targets. `make help` lists them.
PY ?= python

.PHONY: help check setup index run dev test submit app clean

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | column -t -s "$$(printf '\t')"

check:   ## preflight: python version, packages, key, index
	$(PY) scripts/check_env.py

setup:   ## install dependencies and build the index
	$(PY) scripts/check_env.py || true
	$(PY) -m pip install -r requirements.txt
	$(PY) scripts/build_index.py --force

index:   ## rebuild the knowledge-base index
	$(PY) scripts/build_index.py --force

run:     ## one query, full trace:  make run Q="Can I return MRD-700028?"
	$(PY) scripts/run_one.py "$(Q)" $(if $(C),--customer $(C),)

dev:     ## run and score the 42-query dev set
	$(PY) scripts/evaluate_dev.py --workers 4 --show 10

retrieval: ## retrieval recall only — no LLM calls, no cost
	$(PY) scripts/evaluate_dev.py --retrieval-only

app:     ## launch the Gradio console on http://127.0.0.1:7860
	$(PY) -m support_agent.app

test:    ## contract tests
	$(PY) -m pytest tests -q

submit:  ## produce submission.jsonl from the 126 test queries
	$(PY) scripts/run_batch.py --in data/test_queries.jsonl --out submission.jsonl --workers 4

clean:   ## drop the index, the LLM cache and run artefacts
	rm -rf .index .cache dev_traces.jsonl submission.jsonl
