PY ?= python3
PIP ?= $(PY) -m pip
EXAMPLES := trade_in_estimate ai_chat_bill_page plan_comparison
DICT := examples/inputs/event_dictionary.csv
SMOKE_PORT ?= 8599

.PHONY: setup demo demo-llm test eval app smoke

setup:  ## install dependencies
	$(PIP) install --break-system-packages -r requirements.txt

demo:  ## offline demo: md/docx/json specs for every example (always mock mode, labelled)
	@for f in $(EXAMPLES); do \
		echo "== $$f"; \
		LLM_MODEL=mock $(PY) -m spec_agent generate examples/inputs/$$f.md \
			--format md,docx,json --event-dictionary $(DICT) --out-dir examples/outputs || exit 1; \
	done

demo-llm:  ## same with your configured model (needs a key); writes *.llm.* files
	@for f in $(EXAMPLES); do \
		$(PY) -m spec_agent generate examples/inputs/$$f.md --name $$f.llm \
			--format md,docx,json --event-dictionary $(DICT) --out-dir examples/outputs || exit 1; \
	done

test:  ## offline unit + end-to-end tests
	LLM_MODEL=mock $(PY) -m pytest -q

eval:  ## full pipeline vs single-pass baseline (mock unless a key is configured)
	$(PY) -m spec_agent.evaluation

app:  ## Streamlit UI
	$(PY) -m streamlit run app.py

smoke:  ## start the Streamlit app headless, check its health endpoint, stop it
	@LLM_MODEL=mock $(PY) -m streamlit run app.py --server.headless true \
		--server.port $(SMOKE_PORT) > .streamlit_smoke.log 2>&1 & pid=$$!; \
	ok=0; for i in $$(seq 1 30); do \
		if curl -sf http://localhost:$(SMOKE_PORT)/_stcore/health >/dev/null; then ok=1; break; fi; \
		sleep 1; \
	done; kill $$pid; \
	if [ $$ok = 1 ]; then echo "Streamlit smoke check: OK"; else cat .streamlit_smoke.log; exit 1; fi
