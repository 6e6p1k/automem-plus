"""Patterns for things that look like credentials. A note that matches is never pushed to the store."""

import re

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # a named secret with a value that looks like one; prose such as "token: refresh it hourly" passes
    re.compile(r"(?i)\b(password|passwd|api[_-]?key|secret|token)\s*[:=]\s*[\"']?[A-Za-z0-9_\-/+=.]{16,}"),
]


def has_secret(text):
    return any(p.search(text) for p in SECRET_PATTERNS)
