"""
PII masking engine.

Masks PAN numbers and Aadhaar numbers before any DB write or LLM call.
GSTIN values are intentionally NOT masked — they are public business identifiers.

Masking is deterministic: the same input always produces the same [MASKED-xxxxxxxx]
token using a SHA-256 hash of the original value truncated to 8 hex characters.
"""
import re
import hashlib

# ── Compiled regexes ──────────────────────────────────────────────────────────
# GSTIN must be matched FIRST so the PAN embedded inside it is protected.
GSTIN_RE = re.compile(r'\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b')

# PAN: 5 uppercase letters, 4 digits, 1 uppercase letter
PAN_RE = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b')

# Aadhaar: 12 digits optionally separated by spaces in groups of 4
AADHAAR_RE = re.compile(r'\b\d{4}\s?\d{4}\s?\d{4}\b')


def _hash_token(value: str) -> str:
    """Return a deterministic 8-char hex token for the given raw value."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def _protected_ranges(text: str) -> list[tuple[int, int]]:
    """Return character ranges covered by GSTINs (must not be masked)."""
    return [(m.start(), m.end()) for m in GSTIN_RE.finditer(text)]


def _is_protected(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(ps <= start and end <= pe for ps, pe in ranges)


def mask_pii(text: str) -> str:
    """
    Replace PAN and Aadhaar numbers with deterministic hash tokens.
    GSTIN values are preserved unchanged.
    """
    if not text:
        return text

    protected = _protected_ranges(text)

    def replacer(match: re.Match) -> str:
        if _is_protected(match.start(), match.end(), protected):
            return match.group()
        return f"[MASKED-{_hash_token(match.group())}]"

    text = PAN_RE.sub(replacer, text)
    text = AADHAAR_RE.sub(replacer, text)
    return text


def unmask_count(text: str) -> dict[str, int]:
    """
    Count PII occurrences in *text* BEFORE masking.
    Used for audit logging — call on original text, not masked text.
    """
    protected = _protected_ranges(text)
    pan_count = sum(
        1 for m in PAN_RE.finditer(text)
        if not _is_protected(m.start(), m.end(), protected)
    )
    aadhaar_count = sum(
        1 for m in AADHAAR_RE.finditer(text)
        if not _is_protected(m.start(), m.end(), protected)
    )
    return {"pan": pan_count, "aadhaar": aadhaar_count}
