from payment_platform.security.scan import repo_root


def test_github_actions_runs_threat_model_and_checklist():
    workflow = (repo_root() / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
    assert "tests/threat_model" in workflow
    assert "tests/security" in workflow
    assert "pytest" in workflow
