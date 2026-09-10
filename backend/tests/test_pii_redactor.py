from pii_redactor import redact_pii


def test_email_is_redacted():
    out, flag = redact_pii("Reach me at tom.custom@netcorp.io for details.")
    assert flag is True
    assert "[REDACTED_EMAIL]" in out
    assert "tom.custom@netcorp.io" not in out


def test_phone_is_redacted():
    out, flag = redact_pii("Call us on (415) 555-0134 today please.")
    assert flag is True
    assert "[REDACTED_PHONE]" in out
    assert "(415) 555-0134" not in out


def test_full_name_is_redacted():
    out, flag = redact_pii("Please look into this, John Smith reported the outage.")
    assert flag is True
    assert "[REDACTED_NAME]" in out
    assert "John Smith" not in out


def test_no_pii_leaves_text_alone():
    out, flag = redact_pii("My laptop screen keeps flickering after the update.")
    assert flag is False
    assert out == "My laptop screen keeps flickering after the update."
