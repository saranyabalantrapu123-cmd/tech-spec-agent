import json

from spec_agent.evaluation import ambiguity_recall, run_eval

from .conftest import EXAMPLES, ROOT


def test_ambiguity_recall(good_spec):
    gold = [{"gap": "sub-users", "any": ["sub-user"]}, {"gap": "fees", "any": ["fee"]}]
    recall, missed = ambiguity_recall(good_spec, gold)
    assert recall == 0.5 and missed == ["fees"]


def test_run_eval_writes_reports(tmp_path):
    report = run_eval(EXAMPLES, ROOT / "evals" / "expected_ambiguities.json", tmp_path)
    assert report["mode"] == "offline-demo" and len(report["rows"]) == 3
    for row in report["rows"]:
        assert 0 <= row["single_pass"]["ambiguity_recall"] <= row["full"]["ambiguity_recall"]
        assert row["full"]["score"] >= row["single_pass"]["score"]
    saved = json.loads((tmp_path / "mock_results.json").read_text())
    assert saved == report
    assert "Offline demo" in (tmp_path / "mock_results.md").read_text()
