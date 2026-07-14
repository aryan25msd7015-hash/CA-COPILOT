"""Unit tests for the PII masker engine."""
import pytest
from app.engines.pii_masker import mask_pii, unmask_count


def test_pan_is_masked():
    text = "Party PAN: ABCDE1234F and address follows."
    result = mask_pii(text)
    assert "ABCDE1234F" not in result
    assert "[MASKED-" in result


def test_aadhaar_is_masked():
    text = "Aadhaar: 1234 5678 9012"
    result = mask_pii(text)
    assert "1234 5678 9012" not in result
    assert "[MASKED-" in result


def test_aadhaar_no_spaces_is_masked():
    text = "Aadhaar number 123456789012 provided."
    result = mask_pii(text)
    assert "123456789012" not in result
    assert "[MASKED-" in result


def test_gstin_is_not_masked():
    gstin = "27ABCDE1234F1Z5"
    text = f"Vendor GSTIN: {gstin}"
    result = mask_pii(text)
    assert gstin in result


def test_masking_is_deterministic():
    text = "PAN ABCDE1234F appears twice: ABCDE1234F"
    result1 = mask_pii(text)
    result2 = mask_pii(text)
    assert result1 == result2
    tokens = [w for w in result1.split() if w.startswith("[MASKED-")]
    assert len(set(tokens)) == 1


def test_empty_string_unchanged():
    assert mask_pii("") == ""


def test_no_pii_unchanged():
    text = "This text has no sensitive data at all."
    assert mask_pii(text) == text


def test_gstin_pan_not_double_masked():
    """PAN embedded inside a GSTIN must not be masked."""
    text = "Invoice from 29AABCT1332L1ZD amount 50000"
    result = mask_pii(text)
    assert "29AABCT1332L1ZD" in result


def test_unmask_count_pan():
    text = "PAN1: ABCDE1234F  PAN2: FGHIJ5678K"
    counts = unmask_count(text)
    assert counts["pan"] == 2
    assert counts["aadhaar"] == 0


def test_unmask_count_aadhaar():
    text = "Aadhaar: 1234 5678 9012"
    counts = unmask_count(text)
    assert counts["aadhaar"] == 1


def test_unmask_count_gstin_excluded():
    """GSTIN should not count as PAN."""
    text = "GSTIN: 27ABCDE1234F1Z5"
    counts = unmask_count(text)
    assert counts["pan"] == 0
