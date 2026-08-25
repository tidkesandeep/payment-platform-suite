# Security review (Phase 10)

This is a **local demo**. It is not PCI DSS compliant, GDPR certified, SOX
certified, or a Mastercard partnership. The checklist below is enforced by
tests and GitHub Actions, not by an auditor.

## Checklist

| Item | How it stays green |
|---|---|
| Secrets are not in git | `tests/security/test_secrets_not_in_git.py` scans tracked files; `.gitignore` covers `.env`, `demo-keys/`, `*.priv.jwk` |
| Secrets are not in Docker images | `.dockerignore` keeps private JWKs, `.env`, and Kaggle overlays out of the build context |
| Secrets are not in logs | JSON authorize logs run through `redact_text` (`tests/security/test_log_redaction.py`) |
| No real PANs or customer PII | `tests/security/test_no_real_pii.py`; fixtures are synthetic ids (`cust_001`); IEEE-CIS overlay is gitignored |
| Threats A–G, H, H2 in CI | `.github/workflows/security.yml` runs `tests/threat_model` |
| No PCI / SOX / GDPR / Mastercard-partnership claims | `tests/security/test_no_pci_claims.py` on product surfaces |

## What this review is not

- A PCI DSS assessment
- A production secrets-manager rollout
- Permission to put private issuer keys in git

Demo API key `sk_test_demo` and Compose Postgres `payments/payments` are local
fixtures. They are not production credentials.

Run the same scan the tests use:

```bash
payment-security-scan
```
