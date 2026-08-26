from pathlib import Path


def test_github_actions_runs_locust_against_payments():
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "scale.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "pytest tests/load" in text
    assert "locust-against-payments" in text
