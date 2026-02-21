#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pdfplumber>=0.11", "typer>=0.12"]
# ///

"""Rename PDF receipts to `YYYY-MM-DD Service $0.00 Card-1234.pdf`.

The script extracts:
- paid date (falls back to invoice date if paid date is unavailable),
- service (one of: Github, OpenAI, Anthropic, Weaviate, Cloudflare, Hetzner, Google, Hostgator),
- total charged amount with currency symbol,
- card last 4 digits (optional if unavailable).

If the target filename exists:
- identical content => delete source,
- different content => warn and skip.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber
import typer

DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\b")
MONEY_RE = r"([$€£])\s*([0-9][0-9,]*\.\d{2})"
SERVICE_PATTERNS = (
    ("Github", ("we received payment for your sponsorship", "github, inc.")),
    ("OpenAI", ("openai",)),
    ("Anthropic", ("anthropic, pbc", "anthropic bill to", "support@anthropic.com")),
    ("Weaviate", ("weaviate",)),
    ("Cloudflare", ("cloudflare",)),
    ("Hetzner", ("hetzner online gmbh",)),
    ("Google", ("google cloud", "google one", "contact google llc")),
    ("Hostgator", ("hostgator.com, llc",)),
)

CARD_PATTERNS = (
    re.compile(r"(?:American Express|Amex|Visa|Mastercard|MasterCard|Discover)\s*-\s*(\d{4})", re.IGNORECASE),
    re.compile(r"Charged to [^\n]*\*(\d{4})\)", re.IGNORECASE),
    re.compile(
        r"(?:American Express|Amex|Visa|Mastercard|MasterCard|Discover)[^\n]{0,80}[•* ]{2,}(\d{4})",
        re.IGNORECASE,
    ),
    re.compile(r"\bCreditCard\s+\*{2,}(\d{4})\b", re.IGNORECASE),
    re.compile(r"(?:card|payment method|charged to)[^\n]{0,80}(\d{4})", re.IGNORECASE),
)

COMMON_DATE_RULES = (
    (re.compile(r"\bDate paid\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})\b", re.IGNORECASE), "%B %d, %Y"),
    (re.compile(r"\bpaid on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})\b", re.IGNORECASE), "%B %d, %Y"),
    (re.compile(r"\bPaid on\s+(\d{1,2}/\d{1,2}/\d{4})\b", re.IGNORECASE), "%d/%m/%Y"),
    (re.compile(r"\bDate of issue\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})\b", re.IGNORECASE), "%B %d, %Y"),
    (re.compile(r"\bInvoice date:?\s+(\d{1,2}/\d{1,2}/\d{4})\b", re.IGNORECASE), "%d/%m/%Y"),
    (re.compile(r"\bInvoice date:?\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})\b", re.IGNORECASE), "%B %d, %Y"),
)
GITHUB_DATE_RULE = (
    re.compile(r"\bDate\s+(\d{4}-\d{2}-\d{2})\s+\d{1,2}:\d{2}(?:AM|PM)\s+[A-Z]{2,4}\b", re.IGNORECASE),
    "%Y-%m-%d",
)
HOSTGATOR_PAYMENT_RE = re.compile(
    r"\bPayments:\s*Date[^\n]*\n(?P<date>\d{1,2}/\d{1,2}/\d{2})[^\n]*?(?P<amount>\$[0-9][0-9,]*\.\d{2})\b",
    re.IGNORECASE | re.DOTALL,
)
GOOGLE_STATEMENT_DATE_RE = re.compile(r"\bStatement issue date\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})", re.IGNORECASE)
GOOGLE_ONE_DATE_RE = re.compile(
    r"\b([A-Za-z]+),\s+([A-Za-z]+)\s+(\d{1,2})\s+\d{1,2}:\d{2}\s*(?:AM|PM)\b",
    re.IGNORECASE,
)
GOOGLE_MONTHLY_CHARGE_DATE_RE = re.compile(r"\b([A-Za-z]{3}\s+\d{1,2})\s+Monthly charge:", re.IGNORECASE)
GOOGLE_SUMMARY_YEAR_RE = re.compile(r"Summary for [A-Za-z]{3}\s+\d{1,2},\s+(\d{4})", re.IGNORECASE)
GOOGLE_ISSUE_YEAR_RE = re.compile(r"Statement issue date.*?(\d{4})", re.IGNORECASE)
GOOGLE_TOTAL_CODE_RE = re.compile(r"\bTotal\s+([A-Z]{3})\s+([0-9][0-9,]*\.\d{2})\b", re.IGNORECASE)
GOOGLE_TOTAL_PAYMENTS_RE = re.compile(rf"\bTotal payments received\s+[-−]?\s*{MONEY_RE}\b", re.IGNORECASE)
GOOGLE_BALANCE_RULES = (
    re.compile(rf"\bEnding balance in USD\s+{MONEY_RE}\b", re.IGNORECASE),
    re.compile(rf"\bTotal new activity\s+{MONEY_RE}\b", re.IGNORECASE),
)
COMMON_AMOUNT_RULES = (
    re.compile(rf"\bAmount paid\s+{MONEY_RE}\b", re.IGNORECASE),
    re.compile(rf"\b{MONEY_RE}\s+paid on\b", re.IGNORECASE),
    re.compile(rf"\bAmount due:?\s*{MONEY_RE}\b", re.IGNORECASE),
    re.compile(rf"\bTotal\s+{MONEY_RE}\b", re.IGNORECASE),
)
GITHUB_TOTAL_RULE = re.compile(rf"\bTotal\s+{MONEY_RE}\s*USD\*?", re.IGNORECASE)
CURRENCY_SYMBOL_BY_CODE = {"USD": "$", "SGD": "S$", "EUR": "€", "GBP": "£"}
RESULT_PREFIXES = {"RENAME ": "renamed", "DELETE-DUPLICATE ": "deleted", "UNCHANGED ": "unchanged"}


class ParseError(ValueError):
    """Raised when required receipt fields cannot be extracted."""


@dataclass(frozen=True)
class ReceiptFields:
    """Normalized fields needed to build the destination filename."""

    paid_date: date
    service: str
    currency_symbol: str
    amount: Decimal
    card_last4: str | None

    def filename(self) -> str:
        """Return canonical receipt filename."""
        normalized_amount = self.amount.quantize(Decimal("0.01"))
        stem = (
            f"{self.paid_date.isoformat()} {self.service} "
            f"{self.currency_symbol}{normalized_amount:.2f}"
        )
        if self.card_last4:
            stem = f"{stem} Card-{self.card_last4}"
        return f"{stem}.pdf"


def load_pdf_text(path: Path) -> str:
    """Extract all text from a PDF and strip NUL chars from OCR/text layer artifacts."""
    with pdfplumber.open(str(path)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    return text.replace("\x00", "")


def to_decimal(raw_amount: str) -> Decimal:
    """Convert captured currency amount text to Decimal."""
    return Decimal(raw_amount.replace(",", ""))


def parse_date(raw: str, fmt: str) -> date:
    """Parse a date string using one expected format."""
    return datetime.strptime(raw.strip(), fmt).date()  # noqa: DTZ007


def detect_service(text: str) -> str:
    """Map PDF body text to one service name in the allowed set."""
    lower = text.lower()
    for service, markers in SERVICE_PATTERNS:
        if any(marker in lower for marker in markers):
            return service
    raise ParseError("unknown vendor format")


def parse_card_last4(text: str) -> str | None:
    """Extract payment card last 4 digits from known card markers when available."""
    for pattern in CARD_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def parse_date_by_rules(text: str, rules: tuple[tuple[re.Pattern[str], str], ...]) -> date | None:
    """Return the first date that matches one of the supplied regex/format rules."""
    for pattern, fmt in rules:
        match = pattern.search(text)
        if match:
            return parse_date(match.group(1), fmt)
    return None


def parse_hostgator_payment_row(text: str) -> re.Match[str] | None:
    """Return Hostgator payment row with captured `date` and `amount` groups."""
    return HOSTGATOR_PAYMENT_RE.search(text)


def parse_google_paid_date(text: str, source_path: Path) -> date | None:
    """Parse Google dates, preferring statement date for Cloud statements."""
    normalized = text.replace(".", "")
    statement_date = GOOGLE_STATEMENT_DATE_RE.search(normalized)
    if statement_date:
        return parse_date(statement_date.group(1), "%b %d, %Y")

    receipt_date = GOOGLE_ONE_DATE_RE.search(text)
    if receipt_date:
        weekday = receipt_date.group(1)
        month = parse_date(receipt_date.group(2), "%B").month
        day = int(receipt_date.group(3))
        year = infer_year_with_weekday(month, day, weekday, source_path)
        return date(year, month, day)

    monthly_charge = GOOGLE_MONTHLY_CHARGE_DATE_RE.search(text)
    if monthly_charge:
        with_year = f"{monthly_charge.group(1)} {parse_date_from_google_year(text)}"
        return parse_date(with_year, "%b %d %Y")

    return None


def parse_hostgator_amount(text: str) -> tuple[str, Decimal] | None:
    """Parse Hostgator amount from the payment row."""
    payment_row = parse_hostgator_payment_row(text)
    if not payment_row:
        return None
    return "$", to_decimal(payment_row.group("amount").replace("$", ""))


def parse_google_amount(text: str) -> tuple[str, Decimal] | None:
    """Parse Google amount from totals or payments summary."""
    google_total = GOOGLE_TOTAL_CODE_RE.search(text)
    if google_total:
        code = google_total.group(1).upper()
        symbol = CURRENCY_SYMBOL_BY_CODE.get(code, f"{code} ")
        return symbol, to_decimal(google_total.group(2))

    received = GOOGLE_TOTAL_PAYMENTS_RE.search(text)
    if received and to_decimal(received.group(2)) != Decimal("0.00"):
        return received.group(1), abs(to_decimal(received.group(2)))

    for pattern in GOOGLE_BALANCE_RULES:
        match = pattern.search(text)
        if match:
            return match.group(1), to_decimal(match.group(2))

    return None


def parse_paid_date(text: str, service: str, source_path: Path) -> date:
    """Extract paid date and fall back to invoice date when needed."""
    if service == "Hostgator":
        payment_row = parse_hostgator_payment_row(text)
        if payment_row:
            return parse_date(payment_row.group("date"), "%m/%d/%y")

    if service == "Google":
        google_date = parse_google_paid_date(text, source_path)
        if google_date:
            return google_date

    if service == "Github":
        github_date = parse_date_by_rules(text, (GITHUB_DATE_RULE,))
        if github_date:
            return github_date

    common_date = parse_date_by_rules(text, COMMON_DATE_RULES)
    if common_date:
        return common_date

    raise ParseError("missing paid date and invoice date")


def parse_amount(text: str, service: str) -> tuple[str, Decimal]:
    """Extract charged amount and currency symbol."""
    if service == "Hostgator":
        hostgator_amount = parse_hostgator_amount(text)
        if hostgator_amount:
            return hostgator_amount

    if service == "Google":
        google_amount = parse_google_amount(text)
        if google_amount:
            return google_amount

    if service == "Github":
        github_total = GITHUB_TOTAL_RULE.search(text)
        if github_total:
            return github_total.group(1), to_decimal(github_total.group(2))

    for pattern in COMMON_AMOUNT_RULES:
        match = pattern.search(text)
        if match:
            return match.group(1), to_decimal(match.group(2))

    raise ParseError("missing total amount")


def parse_date_from_google_year(text: str) -> int:
    """Extract the statement year from Google summary range text."""
    summary_year = GOOGLE_SUMMARY_YEAR_RE.search(text)
    if summary_year:
        return int(summary_year.group(1))

    issue_year = GOOGLE_ISSUE_YEAR_RE.search(text.replace(".", ""))
    if issue_year:
        return int(issue_year.group(1))

    raise ParseError("missing year for Google payment date")


def infer_year_with_weekday(month: int, day: int, weekday_name: str, source_path: Path) -> int:
    """Infer year for month/day+weekday receipts that omit year."""
    reference_date = datetime.fromtimestamp(source_path.stat().st_mtime).date()  # noqa: DTZ006
    target_weekday = weekday_name.strip().lower()

    for year in range(reference_date.year, reference_date.year - 15, -1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate.strftime("%A").lower() == target_weekday and candidate <= reference_date:
            return year

    raise ParseError("missing inferable year for date without year")


def parse_receipt(path: Path) -> ReceiptFields:
    """Extract normalized fields from one receipt PDF."""
    text = load_pdf_text(path)
    service = detect_service(text)
    paid_date = parse_paid_date(text, service, path)
    currency_symbol, amount = parse_amount(text, service)
    card_last4 = parse_card_last4(text)
    return ReceiptFields(
        paid_date=paid_date,
        service=service,
        currency_symbol=currency_symbol,
        amount=amount,
        card_last4=card_last4,
    )


def files_identical(left: Path, right: Path) -> bool:
    """Treat files as identical when file sizes match."""
    return left.stat().st_size == right.stat().st_size


def process_file(path: Path, dry_run: bool = False) -> str:
    """Process one file and return status string."""
    fields = parse_receipt(path)
    target = path.with_name(fields.filename())

    if target == path:
        return f"UNCHANGED {path.name}"

    if target.exists():
        if files_identical(path, target):
            if dry_run:
                return f"DELETE-DUPLICATE {path.name} (would delete; same as {target.name})"
            path.unlink()
            return f"DELETE-DUPLICATE {path.name} (same as {target.name})"
        return f"WARNING {path.name} -> {target.name} exists and differs; skipped"

    if dry_run:
        return f"RENAME {path.name} -> {target.name}"
    path.rename(target)
    return f"RENAME {path.name} -> {target.name}"


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def rename_receipts(
    directory: Path = typer.Argument(Path("."), exists=True, file_okay=False, dir_okay=True),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show actions without renaming/deleting."),
    recursive: bool = typer.Option(False, "--recursive", help="Also process PDFs in subdirectories."),
) -> None:
    """Rename PDF receipts using paid date, service, amount, and card last-4."""
    globber = directory.rglob if recursive else directory.glob
    pdf_paths = sorted(p for p in globber("*.pdf") if p.is_file() and not DATE_PREFIX_RE.match(p.name))

    if not pdf_paths:
        typer.echo("No eligible PDF files found.")
        raise typer.Exit(0)

    counts: Counter[str] = Counter({"renamed": 0, "deleted": 0, "unchanged": 0, "skipped": 0})

    for pdf_path in pdf_paths:
        try:
            result = process_file(pdf_path, dry_run=dry_run)
            typer.echo(result)
            bucket = next((name for prefix, name in RESULT_PREFIXES.items() if result.startswith(prefix)), "skipped")
            counts[bucket] += 1
        except ParseError as exc:
            counts["skipped"] += 1
            typer.echo(f"WARNING {pdf_path.name}: {exc}; skipped")
        except Exception as exc:  # pragma: no cover - operational safety net for bulk renaming.
            counts["skipped"] += 1
            typer.echo(f"WARNING {pdf_path.name}: unexpected error: {exc}; skipped")

    typer.echo(
        f"\nSummary: processed={len(pdf_paths)} renamed={counts['renamed']} "
        f"deleted={counts['deleted']} unchanged={counts['unchanged']} skipped={counts['skipped']}"
    )


if __name__ == "__main__":
    app()
