"""아침 요약 메시지를 만들고, 텔레그램 설정이 있으면 보냅니다.

환경변수 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DASHBOARD_URL(선택)
사용법:  python collector/summary.py [--send]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
WEEK = "월화수목금토일"


def man(won: float) -> str:
    """원 → '3,875만' / '37.8억'"""
    if abs(won) >= 1e8:
        return f"{won / 1e8:.1f}억"
    return f"{won / 1e4:,.0f}만"


def arrow(r: float | None) -> str:
    if r is None:
        return "  –"
    return f"{'▲' if r >= 0 else '▼'}{abs(r) * 100:.1f}%"


def dlabel(d: str) -> str:
    x = date.fromisoformat(d)
    return f"{x.month}/{x.day}({WEEK[x.weekday()]})"


def make_text(data: dict) -> str:
    comb = data["combined"]
    if len(comb) < 7:
        return f"📊 탑툰챗 추정 매출\n데이터 누적 중: 하루치 {len(comb)}일 (요약은 7일부터)"
    gen = data["generatedAt"]
    last7 = comb[-7:]
    prev7 = comb[-14:-7] if len(comb) >= 14 else None
    avg = sum(r["revenue"] for r in last7) / 7
    lines = ["📊 탑툰챗 추정 매출", f"{dlabel(gen[:10])} {gen[11:16]} 기준", "",
             f"최근 7일 평균 일매출 {man(avg)} 원"]
    if prev7:
        pavg = sum(r["revenue"] for r in prev7) / 7
        lines.append(f"전주 {man(pavg)} 원 → {arrow(avg / pavg - 1)}")
    q = data["quarter"]
    if q:
        lines += ["", f"{q['quarter'][-1]}분기 추정 {man(q['estimate'])} 원"
                  + (f" (관측 {q['observedDays']}/{q['days']}일)" if q["observedDays"] < q["days"] else "")]
        if q["prevRevenue"]:
            lines.append(f"{q['prevQuarter'][-1]}분기 {man(q['prevRevenue'])} 원 → {arrow(q['qoq'])}")

    tbl = ["지역       하루  비중 전주대비"]
    for g, reg in data["regions"].items():
        s = reg["series"][-7:]
        if len(s) < 7:
            continue
        rev = sum(r["revenue"] for r in s) / 7
        ps = reg["series"][-14:-7]
        wow = (rev / (sum(r["revenue"] for r in ps) / 7) - 1) if len(ps) == 7 and sum(r["revenue"] for r in ps) else None
        tbl.append(f"{reg['label']:<5}{man(rev):>8}  {rev / avg * 100:>3.0f}%  {arrow(wow):>7}")
    lines += ["", "```", *tbl, "```", "", "일자별 일매출", "```", "일자(요일)  일매출 전날대비"]
    tail = comb[-8:]
    for i in range(len(tail) - 1, -1, -1):
        r = tail[i]
        prev = comb[comb.index(r) - 1] if comb.index(r) > 0 else None
        ch = arrow(r["revenue"] / prev["revenue"] - 1) if prev and prev["revenue"] else "  –"
        lines.append(f"{dlabel(r['date']):<10}{man(r['revenue']):>7} {ch:>8}")
    lines += ["```", "※ 신규 채팅 수 × 건당 계수로 낸 추정치"]
    url = os.environ.get("DASHBOARD_URL")
    if url:
        lines += ["", f"[대시보드 열기]({url})"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args()
    data = json.loads((ROOT / "docs" / "data.json").read_text(encoding="utf-8"))
    text = make_text(data)
    print(text)
    if args.send:
        tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not (tok and chat):
            sys.exit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 없어 전송하지 않음")
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                          json={"chat_id": chat, "text": text, "parse_mode": "Markdown",
                                "disable_web_page_preview": True})
        r.raise_for_status()
        print("sent")


if __name__ == "__main__":
    main()
