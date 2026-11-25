"""댓글 작성 시각으로 출시 이후 월별 활동 추이를 만듭니다(처음 한 번, 이후 가끔).

채팅 수의 과거 값은 알 수 없지만, 댓글은 작성 시각이 남아 있어 과거 방향을 볼 수 있습니다.
결과: data/comments_monthly.csv  (region, month, comments)

사용법:  python collector/backfill_comments.py [--regions KR,JP]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from collect import DATA, Client, fetch_characters, fetch_contents  # noqa: E402

KST = timezone(timedelta(hours=9))


def month_of(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST).strftime("%Y-%m")


def item_comment_months(c: Client, kind: str, item_id: int) -> Counter:
    target = "character" if kind == "character" else "content"
    months, cursor = Counter(), None
    while True:
        params = {"targetType": target, "targetId": item_id, "limit": 100, "sort": "latest"}
        if cursor:
            params["cursor"] = cursor
        d = c.get("/api/comments", **params)
        for cm in d["data"]:
            for x in [cm] + (cm.get("replies") or []):
                if x.get("createdAt") and not x.get("isDeleted"):
                    months[month_of(x["createdAt"])] += 1
        cursor = d.get("nextCursor")
        if not cursor:
            return months


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", default=",".join(config.REGIONS))
    args = ap.parse_args()

    rows = []
    for region in args.regions.split(","):
        c = Client(config.REGIONS[region])
        items = fetch_characters(c) + fetch_contents(c)
        total = Counter()
        for i, x in enumerate(items, 1):
            try:
                total += item_comment_months(c, x["kind"], x["id"])
            except Exception as e:  # noqa: BLE001
                print(f"  [{region}] {x['kind']}/{x['id']} 실패: {e}", file=sys.stderr)
            if i % 25 == 0:
                print(f"  [{region}] {i}/{len(items)}")
        for m, n in sorted(total.items()):
            rows.append({"region": region, "month": m, "comments": n})
        print(f"[{region}] 완료: {json.dumps(dict(sorted(total.items())), ensure_ascii=False)}")

    out = DATA / "comments_monthly.csv"
    keep = []
    if out.exists():  # 이번에 안 돌린 지역은 기존 값 유지
        with out.open(encoding="utf-8") as f:
            keep = [r for r in csv.DictReader(f) if r["region"] not in args.regions.split(",")]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["region", "month", "comments"])
        w.writeheader()
        w.writerows(keep + rows)


if __name__ == "__main__":
    main()
