"""수집한 CSV로 지표를 계산해 docs/data.json(대시보드용)을 만듭니다.

하루치 신규 채팅 = (다음 날 첫 기록의 누적 chatCount) − (그날 첫 기록의 누적 chatCount)
  · 두 기록에 모두 있는 항목: 차이를 그대로 씀
  · 다음 날에만 있는 항목: 그날 출시됐으면 누적값 전체, 아니면(뒤늦게 발견) 제외
추정 매출 = 신규 채팅 × config.WON_PER_NEW_CHAT[지역]

사용법:  python collector/build.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "data.json"


def kst_date(iso: str | None) -> date | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST).date()


def quarter_of(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def quarter_bounds(q: str) -> tuple[date, date]:
    y, n = int(q[:4]), int(q[-1])
    start = date(y, 3 * (n - 1) + 1, 1)
    end = date(y + (n == 4), (3 * n) % 12 + 1, 1) - timedelta(days=1)
    return start, end


def load_daily() -> dict[str, dict[str, dict[tuple, dict]]]:
    """snap[region][date] = {(kind,id): row}"""
    snap: dict = defaultdict(lambda: defaultdict(dict))
    p = DATA / "daily_items.csv"
    if not p.exists():
        return snap
    with p.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for k in ("chatCount", "viewCount", "likeCount"):
                r[k] = int(r[k] or 0)
            snap[r["region"]][r["date"]][(r["kind"], r["id"])] = r
    return snap


def daily_series(snap_region: dict[str, dict]) -> list[dict]:
    days = sorted(snap_region)
    out = []
    for d0, d1 in zip(days, days[1:]):
        day = date.fromisoformat(d0)
        if (date.fromisoformat(d1) - day).days != 1:
            continue  # 하루 이상 비면 그 구간은 계산하지 않음(합쳐서 하루로 세지 않도록)
        a, b = snap_region[d0], snap_region[d1]
        if a and int(next(iter(a.values()))["ts"][11:13]) >= 3:
            continue  # 그날 첫 기록이 새벽 3시 이후면 하루치가 아니므로 제외
        row = {"date": d0, "character": 0, "multi": 0, "newItems": 0, "existingItems": 0,
               "launched": 0, "skipped": 0}
        for key, rb in b.items():
            ra = a.get(key)
            if ra is not None:
                delta = max(0, rb["chatCount"] - ra["chatCount"])
            elif kst_date(rb["startAt"]) and kst_date(rb["startAt"]) >= day:
                delta = rb["chatCount"]
                row["launched"] += 1
            else:
                row["skipped"] += 1
                continue
            row[rb["kind"]] += delta
            start = kst_date(rb["startAt"])
            is_new = start is not None and (day - start).days < config.NEW_ITEM_DAYS
            row["newItems" if is_new else "existingItems"] += delta
        row["total"] = row["character"] + row["multi"]
        out.append(row)
    return out


def ma(vals: list[float], n: int = 7) -> list[float | None]:
    return [sum(vals[i - n + 1:i + 1]) / n if i >= n - 1 else None for i in range(len(vals))]


def ratio(cur: list[float], n: int = 7):
    if len(cur) < 2 * n:
        return None
    prev = sum(cur[-2 * n:-n])
    return sum(cur[-n:]) / prev if prev else None


def build():
    snap = load_daily()
    now = datetime.now(KST)
    regions_out, all_dates = {}, set()

    for region in config.REGIONS:
        series = daily_series(snap.get(region, {}))
        coef = config.WON_PER_NEW_CHAT[region]
        for r in series:
            r["revenue"] = r["total"] * coef
            all_dates.add(r["date"])
        totals = [r["total"] for r in series]
        for r, m in zip(series, ma(totals)):
            r["total_ma7"] = m

        latest_path = DATA / "latest" / f"{region}.json"
        latest = json.loads(latest_path.read_text(encoding="utf-8")) if latest_path.exists() else None

        # 항목 순위: 최신 스냅샷 − 오늘(또는 가장 최근) 첫 기록
        ranking = []
        days = sorted(snap.get(region, {}))
        if latest and days:
            base = snap[region][days[-1]]
            if days[-1] == now.strftime("%Y-%m-%d") and len(days) >= 2:
                base_label = "오늘 0시 이후"
            else:
                base_label = f"{days[-1]} 첫 기록 이후"
            for x in latest["items"]:
                b = base.get((x["kind"], str(x["id"])))
                ranking.append({"kind": x["kind"], "id": x["id"], "name": x["name"],
                                "startAt": x["startAt"], "chatCount": x["chatCount"],
                                "viewCount": x["viewCount"],
                                "recent": x["chatCount"] - b["chatCount"] if b else None})
            ranking.sort(key=lambda r: (r["recent"] is None, -(r["recent"] or 0), -r["chatCount"]))
        else:
            base_label = None

        last7 = series[-7:]
        regions_out[region] = {
            "label": config.REGION_LABEL[region],
            "coef": coef,
            "series": series,
            "avg7": sum(r["total"] for r in last7) / len(last7) if len(last7) == 7 else None,
            "avg7_revenue": (sum(r["revenue"] for r in last7) / 7) if len(last7) == 7 else None,
            "wow": ratio(totals),
            "newShare7": (sum(r["newItems"] for r in last7) / max(1, sum(r["total"] for r in last7))) if last7 else None,
            "multiShare7": (sum(r["multi"] for r in last7) / max(1, sum(r["total"] for r in last7))) if last7 else None,
            "latest": None if not latest else {
                "ts": latest["ts"],
                "items": len(latest["items"]),
                "characters": sum(1 for x in latest["items"] if x["kind"] == "character"),
                "multis": sum(1 for x in latest["items"] if x["kind"] == "multi"),
                "chatCount": sum(x["chatCount"] for x in latest["items"]),
                "viewCount": sum(x["viewCount"] for x in latest["items"]),
            },
            "ranking": ranking[:25],
            "rankingBase": base_label,
            "recentLaunches": sorted(
                [r for r in ranking if r["startAt"]], key=lambda r: r["startAt"], reverse=True)[:15],
        }

    # 네 지역 합계 (네 지역 모두 값이 있는 날만)
    combined = []
    for d in sorted(all_dates):
        rows = [next((r for r in regions_out[g]["series"] if r["date"] == d), None) for g in config.REGIONS]
        if all(rows):
            combined.append({"date": d, "total": sum(r["total"] for r in rows),
                             "revenue": sum(r["revenue"] for r in rows),
                             "byRegion": {g: r["revenue"] for g, r in zip(config.REGIONS, rows)}})
    for r, m in zip(combined, ma([r["revenue"] for r in combined])):
        r["revenue_ma7"] = m

    # 분기 추정: 관측일 합 + 나머지 일수 × 최근 7일 평균
    quarter = None
    if combined:
        q = quarter_of(now.date())
        qs, qe = quarter_bounds(q)
        obs = [r for r in combined if qs <= date.fromisoformat(r["date"]) <= qe]
        avg7 = sum(r["revenue"] for r in combined[-7:]) / len(combined[-7:])
        days_total = (qe - qs).days + 1
        est = sum(r["revenue"] for r in obs) + (days_total - len(obs)) * avg7
        prev_q = quarter_of(qs - timedelta(days=1))
        prev_rev = config.QUARTERLY_REVENUE.get(prev_q)
        quarter = {"quarter": q, "estimate": est, "observedDays": len(obs), "days": days_total,
                   "avg7": avg7, "prevQuarter": prev_q, "prevRevenue": prev_rev,
                   "qoq": est / prev_rev - 1 if prev_rev else None}

    # 계수 보정: 분기 전체(85일 이상)가 관측된 분기만
    calibration = []
    for q, rev in config.QUARTERLY_REVENUE.items():
        qs, qe = quarter_bounds(q)
        obs = [r for r in combined if qs <= date.fromisoformat(r["date"]) <= qe]
        chats = sum(r["total"] for r in obs)
        calibration.append({"quarter": q, "revenue": rev, "observedDays": len(obs), "newChats": chats,
                            "wonPerChat": rev / chats if len(obs) >= 85 and chats else None})

    comments = []
    cp = DATA / "comments_monthly.csv"
    if cp.exists():
        with cp.open(encoding="utf-8") as f:
            comments = [{**r, "comments": int(r["comments"])} for r in csv.DictReader(f)]

    out = {"generatedAt": now.isoformat(timespec="seconds"), "regions": regions_out,
           "combined": combined, "quarter": quarter, "calibration": calibration,
           "commentsMonthly": comments, "newItemDays": config.NEW_ITEM_DAYS}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes, {len(combined)} combined days)")
    return out


if __name__ == "__main__":
    build()
