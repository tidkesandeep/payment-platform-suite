from payment_platform.security.scan import scan_repository


def test_tracked_product_files_have_no_pan_ssn_or_personal_email():
    report = scan_repository()
    pii = [item for item in report.findings if item.kind in {"pan", "ssn", "pii_email"}]
    assert pii == []
