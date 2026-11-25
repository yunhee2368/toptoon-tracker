"""수집 대상과 매출 환산 설정.

매출 계수는 반드시 직접 보정해야 합니다. 아래 기본값은 임시값입니다.
"""

REGIONS = {
    "KR": "https://chat.toptoon.com",
    "JP": "https://chat.toptoon.jp",
    "TW": "https://chat.toptoon.net",
    "GL": "https://chat.global.toptoon.com",
}

REGION_LABEL = {"KR": "한국", "JP": "일본", "TW": "대만", "GL": "글로벌"}

# 요청 사이 대기(초). 서버에 부담을 주지 않도록 너무 줄이지 마세요.
REQUEST_DELAY = 0.5
TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (research tracker; contact: your-email@example.com)"

# 출시 후 이 일수 이내면 '신규 캐릭터'로 분류
NEW_ITEM_DAYS = 30

# 신규 채팅 1건당 매출(원). 지역별로 따로 둘 수 있습니다.
# 임시값: 원본 트래커의 11/25 기준 일매출(3,720만 원) ÷ 일간 신규 채팅(약 1.63만 건) ≈ 2,280원.
# 분기 전체가 수집되면 대시보드 '계수 보정' 표에 실측 계수가 나옵니다. 그 값으로 바꾸세요.
WON_PER_NEW_CHAT = {"KR": 2280, "JP": 2280, "TW": 2280, "GL": 2280}

# 회사가 밝힌 분기 챗 매출(원). 계수 보정과 차트 비교에 씁니다.
QUARTERLY_REVENUE = {
    "2026Q2": 2_040_000_000,
    "2026Q3": 2_370_000_000,
}
