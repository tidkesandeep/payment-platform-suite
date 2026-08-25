from logging import LogRecord

from payment_platform.observability.jsonlog import JsonLogFormatter
from payment_platform.observability.redact import redact_text


def test_redact_strips_api_keys_passwords_and_private_jwk_d():
    live = "sk_" + "live_abc123"
    demo = "sk_" + "test_demo"
    exponent = "super-secret-exponent"
    raw = (
        "user=payments password=payments "
        "postgresql://payments:secret-pass@127.0.0.1:5432/payments "
        f"{demo} {live} "
        '{"kty":"EC","d":"' + exponent + '"} '
        "-----BEGIN EC " + "PRIVATE KEY-----\nMIIB\n-----END EC " + "PRIVATE KEY-----"
    )
    out = redact_text(raw)
    assert demo not in out
    assert live not in out
    assert "secret-pass" not in out
    assert "password=payments" not in out
    assert exponent not in out
    assert "BEGIN EC " + "PRIVATE KEY" not in out
    assert "sk_***" in out
    assert '"d":"***"' in out


def test_json_log_formatter_redacts_message():
    demo = "sk_" + "test_demo"
    record = LogRecord(
        name="payment_platform",
        level=20,
        pathname=__file__,
        lineno=1,
        msg=f"authorize key={demo}",
        args=(),
        exc_info=None,
    )
    line = JsonLogFormatter().format(record)
    assert demo not in line
    assert "sk_***" in line
