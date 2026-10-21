"""Streamlit UI: paste a feature request -> technical spec, quality score, rubric feedback, downloads.

    streamlit run app.py
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from spec_agent.linter import load_event_dictionary
from spec_agent.llm import OFFLINE_BANNER, get_model, is_offline
from spec_agent.pipeline import PipelineResult, run_pipeline
from spec_agent.renderers import render_docx, render_json, render_markdown

ROOT = Path(__file__).parent
EXAMPLES = ROOT / "examples" / "inputs"
SAMPLE_DICTIONARY = EXAMPLES / "event_dictionary.csv"

st.set_page_config(page_title="Tech Spec Agent", page_icon="📐", layout="wide")
st.title("Tech Spec Agent")
st.caption("Feature request → structured, testable technical spec with a tracking plan, "
           "scored by a deterministic rubric.")

if is_offline():
    st.warning(OFFLINE_BANNER)
else:
    st.info(f"Using model `{get_model()}`")

# --- Sidebar: inputs ------------------------------------------------------------------------
with st.sidebar:
    st.header("Input")
    examples = {p.stem.replace("_", " ").title(): p for p in sorted(EXAMPLES.glob("*.md"))}
    choice = st.selectbox("Load an example", ["(paste your own)", *examples])
    st.header("Event dictionary")
    dict_mode = st.radio("Lint tracking events against", ["Sample dictionary", "Upload CSV",
                                                          "None"])
    uploaded_dict = (st.file_uploader("event_dictionary.csv", type=["csv"])
                     if dict_mode == "Upload CSV" else None)
    context_files = st.file_uploader("Extra context files (optional)", type=["md", "txt"],
                                     accept_multiple_files=True)
    single_pass = st.toggle("Single-pass baseline (skip critique + revise)", value=False)

default_text = examples[choice].read_text(encoding="utf-8") if choice in examples else ""
request_text = st.text_area("Feature request", value=default_text, height=320,
                            placeholder="Paste a feature request, PRD excerpt or Slack thread…")


def _load_dictionary():
    if dict_mode == "Sample dictionary":
        return load_event_dictionary(SAMPLE_DICTIONARY)
    if dict_mode == "Upload CSV" and uploaded_dict is not None:
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tmp:
            tmp.write(uploaded_dict.getvalue())
        return load_event_dictionary(tmp.name)
    return []


if st.button("Generate spec", type="primary", disabled=not request_text.strip()):
    with st.spinner("Extracting facts → drafting → critiquing → revising…"):
        st.session_state["result"] = run_pipeline(
            request_text,
            context_docs={f.name: f.getvalue().decode("utf-8", "ignore")
                          for f in context_files or []},
            dictionary=_load_dictionary(),
            source_file=examples[choice].name if choice in examples else "pasted request",
            single_pass=single_pass)

result: PipelineResult | None = st.session_state.get("result")
if result is None:
    st.stop()

# --- Results ---------------------------------------------------------------------------------
spec, score, lint = result.spec, result.score, result.lint
c1, c2, c3, c4 = st.columns(4)
c1.metric("Quality score", f"{score.total:g} / 100",
          None if result.critique is None
          else f"{score.total - result.draft_score.total:+.1f} vs draft")
c2.metric("Open questions", len(spec.open_questions),
          f"{sum(q.blocking for q in spec.open_questions)} blocking", delta_color="off")
c3.metric("Tracking events", len(spec.analytics.events))
c4.metric("Dictionary lint", f"{len(lint.errors)} err / {len(lint.warnings)} warn"
          if lint else "not run")

md = render_markdown(spec, score, lint, result.guardrail_notes)
docx_buf = io.BytesIO()
render_docx(spec, docx_buf, score, lint, result.guardrail_notes)
stem = Path(spec.meta.source_file or "spec").stem.replace(" ", "_")
d1, d2, d3 = st.columns(3)
d1.download_button("Download Markdown", md, f"{stem}.md", "text/markdown")
d2.download_button("Download Word (.docx)", docx_buf.getvalue(), f"{stem}.docx",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
d3.download_button("Download JSON", render_json(spec), f"{stem}.json", "application/json")

tab_spec, tab_score, tab_lint, tab_trace = st.tabs(
    ["Spec", "Rubric feedback", "Event lint", "Pipeline trace"])
with tab_spec:
    st.markdown(md)
with tab_score:
    st.dataframe(pd.DataFrame([{"Category": c.name, "Score": c.score, "Max": c.max_score}
                               for c in score.categories]), hide_index=True)
    findings = [{"Severity": f.severity, "Where": f.location, "Finding": f.message}
                for f in score.findings]
    if findings:
        st.dataframe(pd.DataFrame(findings), hide_index=True, width="stretch")
    else:
        st.success("No findings.")
with tab_lint:
    if lint is None:
        st.info("No event dictionary selected.")
    elif not lint.findings:
        st.success(f"All {lint.checked_events} events are consistent with the dictionary.")
    else:
        st.dataframe(pd.DataFrame([{"Severity": f.severity, "Event": f.event, "Rule": f.rule,
                                    "Finding": f.message, "Suggestion": f.suggestion}
                                   for f in lint.findings]), hide_index=True,
                     width="stretch")
with tab_trace:
    st.write(f"Draft score: **{result.draft_score.total:g}** → final: **{score.total:g}**")
    if result.guardrail_notes:
        st.write("Provenance guardrail relabels:", result.guardrail_notes)
    usage = result.client.usage
    st.write(f"LLM usage: {usage.summary()}" if not result.offline
             else "LLM usage: n/a (offline demo mode)")
    with st.expander("Step 1: extracted facts and ambiguities"):
        st.json(result.extraction.model_dump(mode="json"))
    if result.critique:
        with st.expander("Step 3: critique"):
            st.json(result.critique.model_dump(mode="json"))
