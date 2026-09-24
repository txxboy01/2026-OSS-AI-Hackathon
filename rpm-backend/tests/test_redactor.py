import pytest

from app.redactor import detect_sensitive, detection_copy


@pytest.mark.parametrize(
    "text, expected",
    [
        ("비밀번호: SyntheticSecret!", "PASSWORD"),
        ("password = SyntheticSecret!", "PASSWORD"),
        ("인증번호는 123456 입니다", "OTP"),
        ("1234 인증코드", "OTP"),
        ("전화 010-0000-0000", "PHONE"),
        ("+82 10 0000 0000", "PHONE"),
        ("02-000-0000", "PHONE"),
        ("031-000-0000", "PHONE"),
        ("synthetic@example.invalid", "EMAIL"),
        ("계좌번호: 1234-5678", "ACCOUNT"),
        ("번호 1234567890", "ACCOUNT"),
        ("000000-1000000", "RRN"),
        ("0000-0000-0000-0000", "CARD"),
        ("인증번호 １２３４５６", "OTP"),
        ("전화 ０１０－００００－００００", "PHONE"),
        ("전화 010-00\u200b00-0000", "PHONE"),
        ("인증번호 ١٢٣٤٥٦", "OTP"),
    ],
)
def test_positive(text, expected):
    assert expected in detect_sensitive(text)


@pytest.mark.parametrize(
    "text",
    [
        "아래 링크에서 로그인하세요.",
        "계좌번호를 입력해 주세요.",
        "비밀번호를 입력하세요.",
        "비밀번호 입력하세요.",
        "비밀번호: 입력하세요.",
        "password: enter",
        "오늘 안에 앱을 설치해 주세요.",
        "비밀번호: [삭제]",
        "비밀번호: ****",
        "인증번호 [OTP]",
        "계좌번호 [계좌번호]",
        "이메일 [이메일]",
        "2026-09-24 회의입니다.",
        "주문번호 1234",
        "인증번호\n123456",
    ],
)
def test_negative(text):
    assert detect_sensitive(text) == []


def test_placeholder_does_not_disable_other_checks():
    assert "PHONE" in detect_sensitive("비밀번호: [삭제] 전화: 010-0000-0000")


def test_detection_copy_is_not_the_analysis_source():
    text = "인증번호 １２３\u200b４５６"
    assert detection_copy(text) == "인증번호 123456"
    assert text == "인증번호 １２３\u200b４５６"


def test_overlapping_categories_have_fixed_order():
    assert detect_sensitive("000000-1000000") == ["ACCOUNT", "RRN", "CARD"]
