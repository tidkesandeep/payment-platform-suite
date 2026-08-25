from payment_platform.security.scan import scan_repository


def test_product_surfaces_do_not_claim_pci_sox_gdpr_or_mastercard():
    report = scan_repository()
    claims = [item for item in report.findings if item.kind == "pci_claim"]
    assert claims == []
