"""PII detection and redaction for customer complaint text."""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\b"
)

_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?"
    r"(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)"
)

_FULL_NAME_RE = re.compile(
    r"\b(?!(?i:contact|customer|dear|hello|my|name|please|regards|team|thanks|thank|the|this|user|your)\b)"
    r"[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?\s+"
    r"[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?\b"
)


def redact_pii(text: str) -> tuple[str, bool]:
    """Replace common email, phone-number, and full-name patterns.



    Replacement is performed in a fixed order so that text inserted for one

    PII type is never accidentally processed as another type.

    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    redacted = text

    redacted_any = False

    for pattern, replacement in (
        (_EMAIL_RE, "[REDACTED_EMAIL]"),
        (_PHONE_RE, "[REDACTED_PHONE]"),
        (_FULL_NAME_RE, "[REDACTED_NAME]"),
    ):
        redacted, count = pattern.subn(replacement, redacted)

        redacted_any = redacted_any or count > 0

    return redacted, redacted_any
