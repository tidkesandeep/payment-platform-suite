from pathlib import Path

from payment_platform.security.scan import repo_root, scan_repository


def test_tracked_tree_has_no_secret_files_or_live_keys():
    report = scan_repository()
    secrets = [
        item
        for item in report.findings
        if item.kind in {"secret_file", "private_key", "live_key", "aws_key", "jwk_private"}
    ]
    assert secrets == []


def test_gitignore_and_dockerignore_cover_issuer_keys():
    root = repo_root()
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8")
    for required in (".env", "demo-keys/", "*.priv.jwk"):
        assert required in gitignore
        assert required in dockerignore


def test_compose_api_loads_public_jwk_only():
    text = Path(repo_root() / "docker-compose.yml").read_text(encoding="utf-8")
    assert "PAYMENTS_VI_ISSUER_JWK_FILE: /keys/issuer.pub.jwk" in text
    assert "issuer.priv.jwk" not in text
