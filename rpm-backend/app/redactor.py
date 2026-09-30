"""Local detection only. Never redact the analysis source silently."""

import re
import unicodedata

from .constants import PII_ORDER

EMAIL = re.compile(
    r"(?<![a-z0-9._%+\-])[a-z0-9._%+\-]+@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(?![a-z0-9-])",
    re.IGNORECASE,
)
NUMBERS = re.compile(r"(?<!\d)\+?\d(?:[\d .\t-]*\d)?(?!\d)")
PASSWORD = re.compile(r"(?:비밀번호|패스워드|\bpassword\b|\bpwd\b)[ \t:=]+([^\s]{4,128})(?!\S)")
OTP_WORD = re.compile(r"인증번호|인증코드|\botp\b|\bverification code\b")
ACCOUNT_WORD = re.compile(r"계좌번호|계좌|\baccount\b")
PLACEHOLDERS = {"[삭제]", "[마스킹]", "[redacted]", "[otp]", "[계좌번호]", "[전화번호]", "[이메일]", "****"}
INSTRUCTIONS = {
    "입력하세요",
    "입력해주세요",
    "입력해",
    "알려주세요",
    "제출하세요",
    "등록하세요",
    "변경하세요",
    "확인하세요",
    "input",
    "enter",
}


def detection_copy(message):
    normalized = unicodedata.normalize("NFKC", message)
    return "".join(
        str(unicodedata.decimal(c)) if c.isdecimal() else c
        for c in normalized
        if unicodedata.category(c) != "Cf"
    ).casefold()


def _near(keyword, start, end, line):
    return any(max(start - match.end(), match.start() - end, 0) <= 20 for match in keyword.finditer(line))


def detect_sensitive(message):
    text = detection_copy(message)
    found = set()
    if EMAIL.search(text):
        found.add("EMAIL")
    for line in text.splitlines():
        for match in PASSWORD.finditer(line):
            value = match.group(1).rstrip(".,!?。")
            if value not in PLACEHOLDERS and value not in INSTRUCTIONS:
                found.add("PASSWORD")
        for match in NUMBERS.finditer(line):
            token = match.group()
            digits = "".join(c for c in token if c.isdigit())
            size = len(digits)
            local = "0" + digits[2:] if token.startswith("+82") else digits
            if re.fullmatch(r"(?:01[016789]\d{7,8}|02\d{7,8}|0[3-6][1-5]\d{7,8})", local):
                found.add("PHONE")
            if 4 <= size <= 8 and _near(OTP_WORD, match.start(), match.end(), line):
                found.add("OTP")
            if 10 <= size <= 16 or (
                8 <= size <= 16 and _near(ACCOUNT_WORD, match.start(), match.end(), line)
            ):
                found.add("ACCOUNT")
            if size == 13 and digits[6] in "12345678":
                found.add("RRN")
            if 13 <= size <= 19:
                found.add("CARD")
    return [kind for kind in PII_ORDER if kind in found]
