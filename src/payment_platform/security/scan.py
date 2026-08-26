"""Walk the repository for secrets, PAN-like numbers, and compliance claims."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

SKIP_NAMES = {"champion.json"}
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".rdb", ".so"}
SECRET_SUFFIXES = {".priv.jwk", ".pem", ".p12", ".pfx", ".key"}
SECRET_NAMES = {".env"}

PRIVATE_KEY_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
SK_LIVE = re.compile(r"sk_live_[A-Za-z0-9]+")
AWS_ACCESS_KEY = re.compile(r"AKIA[0-9A-Z]{16}")
JWK_PRIVATE_D = re.compile(r'"d"\s*:\s*"([A-Za-z0-9_-]{40,})"')
PAN_RUN = re.compile(r"(?<!\d)([3-6](?:[ -]?\d){14,15})(?!\d)")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "test.local",
    "localhost",
    "users.noreply.github.com",
}
FORBIDDEN_CLAIM = re.compile(
    "|".join(
        re.escape(phrase)
        for phrase in (
            "pci dss " + "compliant",
            "pci-" + "compliant",
            "pci " + "compliant",
            "gdpr " + "certified",
            "sox " + "certified",
            "sox " + "compliant",
            "mastercard " + "certified",
            "mastercard " + "partnership",
        )
    ),
    re.I,
)
NEGATION = re.compile(
    r"\b(not|no|never|do not|don't|out:|without|superseded|not building)\b",
    re.I,
)
PRODUCT_RELATIVE = (
    "src",
    "apps",
    "tests",
    "README.md",
    "SECURITY.md",
    "docker-compose.yml",
    "Dockerfile",
    ".github",
    "phases",
)


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    detail: str


@dataclass
class ScanReport:
    findings: list[Finding]

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict:
        return {"ok": self.ok, "findings": [asdict(item) for item in self.findings]}


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "PAYMENT_PLATFORM.md").is_file():
            return parent
    raise RuntimeError("repository root not found")


def tracked_files(root: Path | None = None) -> list[Path]:
    base = root or repo_root()
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=base,
        check=True,
        capture_output=True,
    )
    return [base / Path(name) for name in proc.stdout.decode().split("\0") if name]


def _luhn_valid(number: str) -> bool:
    digits = [int(ch) for ch in number if ch.isdigit()]
    if not (15 <= len(digits) <= 16):
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _unnegated_claim(text: str) -> str | None:
    collapsed = re.sub(r"\s+", " ", text)
    for match in FORBIDDEN_CLAIM.finditer(collapsed):
        window = collapsed[max(0, match.start() - 120) : match.end()]
        if not NEGATION.search(window):
            return match.group(0)
    return None


def _is_product_surface(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    parts = relative.parts
    if not parts:
        return False
    return parts[0] in PRODUCT_RELATIVE or relative.as_posix() in PRODUCT_RELATIVE


def _read_text(path: Path) -> str | None:
    if path.name in SKIP_NAMES or path.suffix.lower() in SKIP_SUFFIXES:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8000]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan_repository(root: Path | None = None) -> ScanReport:
    base = root or repo_root()
    findings: list[Finding] = []
    for path in tracked_files(base):
        rel = path.relative_to(base).as_posix()
        suffix = path.suffix.lower()
        if suffix in SECRET_SUFFIXES or path.name in SECRET_NAMES:
            findings.append(Finding("secret_file", rel, "tracked secret-shaped filename"))
            continue
        text = _read_text(path)
        if text is None:
            continue
        if PRIVATE_KEY_PEM.search(text):
            findings.append(Finding("private_key", rel, "PEM private key block"))
        if SK_LIVE.search(text):
            findings.append(Finding("live_key", rel, "sk_live_ credential"))
        if AWS_ACCESS_KEY.search(text):
            findings.append(Finding("aws_key", rel, "AKIA access key"))
        if JWK_PRIVATE_D.search(text):
            findings.append(Finding("jwk_private", rel, "JWK private exponent d"))
        if path.suffix.lower() != ".json":
            for match in PAN_RUN.finditer(text):
                raw = match.group(1)
                if _luhn_valid(raw):
                    findings.append(Finding("pan", rel, f"Luhn-valid card-like number {raw}"))
                    break
            if SSN.search(text):
                findings.append(Finding("ssn", rel, "SSN-shaped value"))
        if _is_product_surface(base, path):
            claim = _unnegated_claim(text)
            if claim:
                findings.append(Finding("pci_claim", rel, claim))
            for match in EMAIL.finditer(text):
                domain = match.group(1).lower()
                if domain not in ALLOWED_EMAIL_DOMAINS:
                    findings.append(Finding("pii_email", rel, match.group(0)))
                    break
    gitignore = (base / ".gitignore").read_text(encoding="utf-8")
    for required in (".env", "demo-keys/", "*.priv.jwk"):
        if required not in gitignore:
            findings.append(Finding("gitignore", ".gitignore", f"missing {required}"))
    dockerignore = (base / ".dockerignore").read_text(encoding="utf-8")
    for required in (".env", "demo-keys/", "*.priv.jwk"):
        if required not in dockerignore:
            findings.append(Finding("dockerignore", ".dockerignore", f"missing {required}"))
    return ScanReport(findings)


def report_json(report: ScanReport) -> str:
    return json.dumps(report.to_dict(), indent=2) + "\n"
