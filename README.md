# 탑툰챗 트래커

탑툰챗(엔키AX, 134580) 네 지역 서비스의 **공개 chatCount**를 매시간 모아 하루치 신규 채팅과 추정 매출을 계산하고, 대시보드와 아침 텔레그램 요약을 만듭니다. 로그인이 필요 없는 공개 API만 씁니다.

| 지역 | 주소 | 2026-11-25 기준 항목 |
|---|---|---|
| 한국 | chat.toptoon.com | 캐릭터 130 · 멀티 26 |
| 일본 | chat.toptoon.jp | 캐릭터 124 · 멀티 30 |
| 대만 | chat.toptoon.net | 캐릭터 117 · 멀티 10 |
| 글로벌 | chat.global.toptoon.com | 캐릭터 120 · 멀티 16 |

## 구성

```
collector/
  config.py              지역 주소, 계수(원/신규 채팅), 분기 실적
  collect.py             매시간 수집 → data/ 에 기록
  backfill_comments.py   댓글 작성 시각으로 월별 이력 생성(처음 한 번)
  build.py               지표 계산 → docs/data.json
  summary.py             아침 요약 메시지(텔레그램 전송 선택)
docs/index.html          대시보드(정적 페이지, data.json을 읽음)
.github/workflows/collect.yml   매시간 자동 실행
tests/                   계산 검증(합성 데이터, 실제 API 응답 표본)
```

사용하는 공개 엔드포인트(지역 주소 뒤에 붙임):
- `/api/characters?page=N&limit=50` : 캐릭터 목록(chatCount, viewCount, likeCount, startAt)
- `/api/content?page=N&limit=50` : 멀티챗 목록
- `/api/comments?targetType=character|content&targetId=ID&limit=100&sort=latest&cursor=X` : 댓글

## 설정 방법 (GitHub Actions + GitHub Pages, 무료)

1. GitHub에 **비공개(private) 저장소**를 만들고 이 폴더 전체를 올립니다.
2. 저장소 **Settings → Pages**에서 Source를 `Deploy from a branch`, 브랜치 `main`, 폴더 `/docs`로 지정합니다.
   - 비공개 저장소의 Pages는 유료 플랜에서만 됩니다. 무료로 하려면 Cloudflare Pages에 저장소를 연결하고 출력 폴더를 `docs`로 지정하세요.
3. 저장소 **Actions** 탭에서 `collect` 워크플로를 켜고 `Run workflow`로 한 번 실행합니다.
   - 처음 실행할 때 `backfill_comments`를 체크하면 월별 댓글 이력도 만듭니다(수십 분 걸릴 수 있음).
4. (선택) 텔레그램 아침 요약
   - @BotFather로 봇을 만들어 토큰을 받고, 봇에게 말을 건 뒤 chat id를 확인합니다.
   - Settings → Secrets and variables → Actions에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`(Secrets), `DASHBOARD_URL`(Variables)을 넣습니다.
   - 매일 07:53 KST에 요약이 전송됩니다.

### GitHub 서버에서 막히는 경우
Actions는 해외(미국) 서버에서 돌아갑니다. 탑툰챗이 해외 접속을 막거나 제한하면 수집이 실패합니다(Actions 로그에 `수집 실패`). 그때는 PC에서 돌리세요.

```bash
pip install -r requirements.txt
python collector/collect.py            # 매시간 (Windows 작업 스케줄러 / macOS·Linux cron)
python collector/collect.py --comments # 하루 한 번
python collector/build.py && python collector/summary.py
```

## 계산 방식

- **하루 신규 채팅** = 다음 날 첫 기록의 누적 chatCount − 그날 첫 기록의 누적 chatCount (항목별 합)
  - 그날 출시된 항목은 누적값 전체를 그날 몫으로 셉니다.
  - 전날 기록에 없었는데 출시일이 더 이른 항목(뒤늦게 공개·발견)은 그날 계산에서 뺍니다.
  - 기록이 하루 이상 빈 구간은 계산하지 않습니다(이틀치를 하루로 세지 않도록).
- **추정 매출** = 신규 채팅 × `WON_PER_NEW_CHAT[지역]`
- **분기 추정** = 이번 분기 관측일 매출 합 + (분기 일수 − 관측일) × 최근 7일 평균
- **신규 비중** = 최근 7일 신규 채팅 중 출시 30일 이내 항목 몫

## 꼭 알아 둘 한계

1. **계수는 임시값입니다.** 기본값 2,280원/건은 원본 트래커의 11/25 일매출(3,720만 원)을 그날 신규 채팅(약 1.63만 건)으로 나눠 빌려 온 값입니다. 분기 전체가 쌓이면 대시보드 "계수 보정" 표에 실측값이 나오니 `config.py`를 그 값으로 바꾸세요. 탐방·IR에서 지역별 매출을 받으면 지역별 계수를 따로 둘 수 있습니다.
2. **chatCount는 채팅 시작 수입니다.** 한 채팅 안에서 오래 이어지는 대화(=메시지 과금의 대부분)는 잡히지 않습니다. 원본 트래커는 이를 보완하려고 로그인 계정으로 서비스 전체 메시지 일련번호를 기록하는데, 이 저장소에는 그 기능이 없습니다. 기존 이용자의 대화가 길어지는 국면에서는 매출을 과소 추정할 수 있습니다.
3. **멀티챗 목록이 원본보다 적습니다.** 원본 트래커는 한국 멀티 38개로 집계하지만 공개 목록 API는 26개만 돌려줍니다(계약 종료·비노출 항목 추정). 누적 채팅 기준 차이는 한국 약 2만 건(약 1%)입니다. 하루 증가분에는 영향이 작습니다.
4. **이용약관.** 공개 페이지의 숫자를 읽는 방식이지만, 수집 간격(기본 매시간, 요청 사이 0.5초)을 줄이지 말고 서비스 약관을 확인하세요.

## 테스트

```bash
python tests/test_pipeline.py     # 합성 데이터로 계산 검증
python tests/test_parse_real.py   # 실제 API 응답 표본으로 파싱 검증
```
