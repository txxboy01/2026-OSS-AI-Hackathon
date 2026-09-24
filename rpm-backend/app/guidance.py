from .constants import USER_ACTION_ORDER
from .schemas import GuidanceRequest, GuidanceResponse, GuidanceStep

CATALOG = {
    "G_DEVICE": (
        10,
        "설치한 기기 사용 중단",
        "의심 앱을 설치한 기기의 네트워크 연결을 끊고, 다른 신뢰할 수 있는 기기에서 관련 서비스 또는 보안 지원 담당자에게 문의하세요.",
    ),
    "G_BANK": (
        20,
        "금융기관에 즉시 문의",
        "송금·결제한 금융기관의 공식 앱이나 직접 확인한 대표 연락처로 즉시 문의해 거래 확인과 가능한 보호 조치를 요청하세요.",
    ),
    "G_STOP": (
        30,
        "추가 행동 중단",
        "메시지의 링크 접속, 정보 입력, 송금·결제, 앱 설치를 더 진행하지 마세요.",
    ),
    "G_CLOSE": (
        40,
        "열린 페이지 닫기",
        "메시지를 통해 연 페이지를 닫고 파일 다운로드나 알림·권한 허용을 진행하지 마세요.",
    ),
    "G_PASSWORD": (
        50,
        "계정 보호",
        "신뢰할 수 있는 기기에서 공식 앱 또는 직접 입력한 주소로 접속해 입력한 비밀번호를 변경하고, 같은 비밀번호를 쓰는 다른 계정도 확인하세요.",
    ),
    "G_SESSIONS": (
        60,
        "로그인 상태 확인",
        "공식 계정 설정에서 최근 로그인과 연결 기기를 확인하고, 모르는 세션을 종료한 뒤 지원되는 추가 인증을 설정하세요.",
    ),
    "G_PRIVACY": (
        70,
        "입력한 정보의 관련 기관에 문의",
        "입력한 정보와 관련된 서비스 또는 금융기관의 공식 창구에 문의해 보호 조치를 확인하세요. 이 서비스에 실제 개인정보를 다시 입력하지 마세요.",
    ),
    "G_VERIFY": (
        80,
        "공식 경로로 확인",
        "메시지 안의 주소·연락처 대신, 평소 사용하던 공식 앱 또는 직접 확인한 주소·대표 연락처에서 사실을 확인하세요.",
    ),
    "G_HELP": (
        90,
        "상황을 정리해 문의",
        "이미 한 행동을 가능한 범위에서 확인하고 관련 서비스의 공식 지원 창구에 문의하세요. 필요한 자료는 본인이 보관하고 이 서비스에 전송하지 마세요.",
    ),
}
MAPPING = {
    "NOT_INTERACTED": ([], "routine"),
    "OPENED_LINK": (["G_CLOSE"], "prompt"),
    "SUBMITTED_CREDENTIALS": (["G_PASSWORD", "G_SESSIONS"], "prompt"),
    "SUBMITTED_PERSONAL": (["G_PRIVACY"], "prompt"),
    "SENT_MONEY": (["G_BANK", "G_HELP"], "urgent"),
    "INSTALLED_APP": (["G_DEVICE", "G_HELP"], "urgent"),
    "UNKNOWN": (["G_HELP"], "prompt"),
}


def get_guidance(actions, request_id):
    checked = GuidanceRequest(actions=actions).actions
    codes = {"G_STOP", "G_VERIFY"}
    urgency = "routine"
    levels = ["routine", "prompt", "urgent"]
    for action in checked:
        more, level = MAPPING[action]
        codes.update(more)
        urgency = max(urgency, level, key=levels.index)
    return GuidanceResponse(
        requestId=request_id,
        actions=sorted(checked, key=USER_ACTION_ORDER.index),
        urgency=urgency,
        steps=[
            GuidanceStep(code=code, priority=CATALOG[code][0], title=CATALOG[code][1], body=CATALOG[code][2])
            for code in sorted(codes, key=lambda c: CATALOG[c][0])
        ],
    )
