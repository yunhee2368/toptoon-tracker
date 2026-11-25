"""합성 데이터로 build.py / summary.py 계산을 검증합니다.
실행: python tests/test_pipeline.py  (저장소 사본에서 돌리므로 실제 data/를 건드리지 않음)
"""
import csv
import json
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent


def main():
    tmp = Path(tempfile.mkdtemp())
    shutil.copytree(SRC / "collector", tmp / "collector")
    (tmp / "data" / "latest").mkdir(parents=True)
    random.seed(1)
    start = date(2026, 10, 27)
    days = [start + timedelta(i) for i in range(30)]
    per_item_daily = {"KR": 60, "JP": 50, "TW": 9, "GL": 2}
    rows, expected = [], {}
    for g, rate in per_item_daily.items():
        items = {i: {"kind": "multi" if i % 5 == 0 else "character",
                     "startAt": "2026-06-01T00:00:00Z", "chat": 1000} for i in range(1, 101)}
        for di, d in enumerate(days):
            if di == 12:  # 뒤늦게 발견된 오래된 항목(누적 5만): 제외돼야 함
                items[600] = {"kind": "character", "startAt": "2026-04-01T00:00:00Z", "chat": 50000}
            for iid, it in items.items():
                rows.append({"date": d.isoformat(), "ts": f"{d.isoformat()}T00:10:00+09:00", "region": g,
                             "kind": it["kind"], "id": iid, "name": f"n{iid}", "startAt": it["startAt"],
                             "chatCount": it["chat"], "viewCount": it["chat"] * 30, "likeCount": 1,
                             "isOfficial": True})
            if di == 10:  # 출시: 그날 0시 기록 이후(낮)에 시작
                items[500] = {"kind": "character", "startAt": f"{d.isoformat()}T03:00:00Z", "chat": 0}
            # 그날 동안 증가
            for iid, it in items.items():
                inc = rate * (3 if iid == 500 else 1)
                it["chat"] += inc
                expected[(g, d.isoformat())] = expected.get((g, d.isoformat()), 0) + inc
        (tmp / "data" / "latest" / f"{g}.json").write_text(json.dumps({"ts": "x", "region": g, "items": [
            {"kind": it["kind"], "id": iid, "name": f"n{iid}", "startAt": it["startAt"], "chatCount": it["chat"],
             "viewCount": 0, "likeCount": 0, "isOfficial": True} for iid, it in items.items()]}))
    with (tmp / "data" / "daily_items.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    subprocess.run([sys.executable, "collector/build.py"], cwd=tmp, check=True)
    data = json.loads((tmp / "docs" / "data.json").read_text())

    kr = {r["date"]: r for r in data["regions"]["KR"]["series"]}
    d10, d12 = days[10].isoformat(), days[12].isoformat()
    # 일반일: 100개 × 60
    assert kr[days[3].isoformat()]["total"] == 6000, kr[days[3].isoformat()]
    # 출시일: 출시 항목 그날 180 포함
    assert kr[d10]["total"] == 6000 + 180 and kr[d10]["launched"] == 1, kr[d10]
    # 뒤늦게 발견된 날 전날(d11→d12 구간에서 600은 d12에만 있음) → 제외
    d11 = days[11].isoformat()
    assert kr[d11]["skipped"] == 1 and kr[d11]["total"] == 6000 + 180, kr[d11]
    # 발견 다음 날부터는 정상 포함
    assert kr[d12]["total"] == 6000 + 180 + 60, kr[d12]
    # 신규/기존: 출시 항목만 신규
    assert kr[d12]["newItems"] == 180
    # 멀티 20개
    assert kr[days[3].isoformat()]["multi"] == 20 * 60
    # 시리즈 길이 = 날짜 29개 (마지막 날은 다음 기록이 없음)
    assert len(data["regions"]["KR"]["series"]) == 29
    # 매출 = 채팅 × 계수
    assert kr[days[3].isoformat()]["revenue"] == 6000 * 2280
    # 합계
    comb = data["combined"]
    assert comb[0]["total"] == (60 + 50 + 9 + 2) * 100
    # 분기 추정 존재
    q = data["quarter"]
    assert q["quarter"] and q["estimate"] > 0
    print("quarter", q)
    # 순위: 최신 - 마지막 기록일 (출시 항목이 1위)
    assert data["regions"]["KR"]["ranking"][0]["id"] == 500
    # 하루가 비면 그 구간은 계산하지 않음
    rows2 = [r for r in rows if not (r["region"] == "TW" and r["date"] == days[5].isoformat())]
    with (tmp / "data" / "daily_items.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows2)
    subprocess.run([sys.executable, "collector/build.py"], cwd=tmp, check=True, capture_output=True)
    data2 = json.loads((tmp / "docs" / "data.json").read_text())
    tw_dates = [r["date"] for r in data2["regions"]["TW"]["series"]]
    assert days[4].isoformat() not in tw_dates and days[5].isoformat() not in tw_dates
    assert len(data2["combined"]) == 27

    out = subprocess.run([sys.executable, "collector/summary.py"], cwd=tmp, check=True,
                         capture_output=True, text=True).stdout
    print(out)
    assert "최근 7일 평균 일매출" in out and "한국" in out
    shutil.copy(tmp / "docs" / "data.json", SRC / "tests" / "sample_data.json")
    print("ALL OK")


if __name__ == "__main__":
    main()
