"""탑툰챗 공개 지표 수집기.

매 실행마다
  1) 네 지역의 캐릭터(/api/characters)와 멀티챗(/api/content) 목록을 받아
  2) data/latest/<지역>.json 에 최신 스냅샷을 덮어쓰고
  3) data/hourly_totals.csv 에 지역별 합계를 한 줄씩 붙이고
  4) 그날(KST) 첫 실행이면 data/daily_items.csv 에 항목별 누적값을 기록합니다.
     (자정 직후 값끼리 빼면 하루치 신규 채팅이 됩니다)
  --comments 옵션을 주면 항목별 댓글 총수도 기록합니다(하루 한 번 권장).

사용법:  python collector/collect.py [--comments]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

DAILY_FIELDS = ["date", "ts", "region", "kind", "id", "name", "startAt",
                "chatCount", "viewCount", "likeCount", "isOfficial"]
HOURLY_FIELDS = ["ts", "region", "kind", "items", "chatCount", "viewCount", "likeCount"]
COMMENT_FIELDS = ["date", "ts", "region", "kind", "id", "comments"]


class Client:
    def __init__(self, base: str):
        self.base = base
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})

    def get(self, path: str, **params):
        for attempt in range(3):
            try:
                r = self.s.get(self.base + path, params=params, timeout=config.TIMEOUT)
                time.sleep(config.REQUEST_DELAY)
                r.raise_for_status()
                j = r.json()
                if not j.get("success"):
                    raise RuntimeError(f"API error: {j.get('error')}")
                return j["data"]
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    raise
                print(f"  retry {attempt + 1} {path}: {e}", file=sys.stderr)
                time.sleep(3 * (attempt + 1))


def fetch_characters(c: Client) -> list[dict]:
    items, page = [], 1
    while True:
        d = c.get("/api/characters", page=page, limit=50)
        items += d["data"]
        if page >= d["pagination"]["totalPages"]:
            break
        page += 1
    return [{
        "kind": "character", "id": x["id"], "name": x.get("name"),
        "startAt": x.get("startAt") or x.get("createdAt"),
        "chatCount": x.get("chatCount") or 0, "viewCount": x.get("viewCount") or 0,
        "likeCount": x.get("likeCount") or 0, "isOfficial": x.get("isOfficial"),
    } for x in items]


def fetch_contents(c: Client) -> list[dict]:
    items, page = [], 1
    while True:
        d = c.get("/api/content", page=page, limit=50)
        items += d["items"]
        if page >= d["totalPages"]:
            break
        page += 1
    return [{
        "kind": "multi", "id": x["id"], "name": x.get("title"),
        "startAt": x.get("startAt"),
        "chatCount": x.get("chatCount") or 0, "viewCount": x.get("viewCount") or 0,
        "likeCount": x.get("likeCount") or 0, "isOfficial": None,
    } for x in items]


def fetch_comment_total(c: Client, kind: str, item_id: int) -> int | None:
    target = "character" if kind == "character" else "content"
    try:
        d = c.get("/api/comments", targetType=target, targetId=item_id, limit=1, sort="latest")
        return d.get("totalCount")
    except Exception as e:  # noqa: BLE001
        print(f"  comments fail {kind}/{item_id}: {e}", file=sys.stderr)
        return None


def append_csv(path: Path, fields: list[str], rows: list[dict]):
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def dates_already_recorded(path: Path) -> set[tuple[str, str]]:
    """(date, region) 조합 중 이미 기록된 것."""
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {(r["date"], r["region"]) for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comments", action="store_true", help="항목별 댓글 총수도 수집")
    ap.add_argument("--regions", default=",".join(config.REGIONS))
    args = ap.parse_args()

    now = datetime.now(KST)
    ts = now.isoformat(timespec="seconds")
    today = now.strftime("%Y-%m-%d")
    daily_path = DATA / "daily_items.csv"
    done = dates_already_recorded(daily_path)
    failures = 0

    for region in args.regions.split(","):
        base = config.REGIONS[region]
        c = Client(base)
        try:
            items = fetch_characters(c) + fetch_contents(c)
        except Exception as e:  # noqa: BLE001
            print(f"[{region}] 수집 실패: {e}", file=sys.stderr)
            failures += 1
            continue

        (DATA / "latest").mkdir(parents=True, exist_ok=True)
        (DATA / "latest" / f"{region}.json").write_text(
            json.dumps({"ts": ts, "region": region, "items": items}, ensure_ascii=False),
            encoding="utf-8")

        hourly = []
        for kind in ("character", "multi"):
            sub = [x for x in items if x["kind"] == kind]
            hourly.append({"ts": ts, "region": region, "kind": kind, "items": len(sub),
                           "chatCount": sum(x["chatCount"] for x in sub),
                           "viewCount": sum(x["viewCount"] for x in sub),
                           "likeCount": sum(x["likeCount"] for x in sub)})
        append_csv(DATA / "hourly_totals.csv", HOURLY_FIELDS, hourly)

        if (today, region) not in done:
            append_csv(daily_path, DAILY_FIELDS,
                       [{"date": today, "ts": ts, "region": region, **x} for x in items])

        if args.comments:
            rows = []
            for x in items:
                n = fetch_comment_total(c, x["kind"], x["id"])
                if n is not None:
                    rows.append({"date": today, "ts": ts, "region": region,
                                 "kind": x["kind"], "id": x["id"], "comments": n})
            append_csv(DATA / "daily_comments.csv", COMMENT_FIELDS, rows)

        tot = sum(h["chatCount"] for h in hourly)
        print(f"[{region}] {len(items)}개 항목, 누적 채팅 {tot:,}")

    if failures == len(args.regions.split(",")):
        sys.exit("모든 지역 수집 실패")


if __name__ == "__main__":
    main()
