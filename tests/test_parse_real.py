"""실제 API 응답 표본(2026-11-25, 긴 텍스트 필드 제거)으로 collect.py 파싱을 검증."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collector"))
import collect

FIX = json.loads((Path(__file__).parent / "fixture_api.json").read_text(encoding="utf-8"))

class Fake:
    def get(self, path, **params):
        if path == "/api/characters":
            d = json.loads(json.dumps(FIX["characters"]["data"])); d["pagination"]["totalPages"] = 1; return d
        if path == "/api/content":
            d = json.loads(json.dumps(FIX["content"]["data"])); d["totalPages"] = 1; return d
        if path == "/api/comments":
            return {"data": [], "nextCursor": None, "totalCount": FIX["commentsTotal"]}
        raise KeyError(path)

c = collect.fetch_characters(Fake())
m = collect.fetch_contents(Fake())
assert c[1] == {"kind": "character", "id": 299, "name": "한가연", "startAt": "2026-08-25T12:00:00.000Z",
                "chatCount": 5179, "viewCount": 41176, "likeCount": 291, "isOfficial": True}, c[1]
assert m[0]["kind"] == "multi" and m[0]["name"] == "아줌마는 SOLO" and m[0]["chatCount"] == 17193 and m[0]["startAt"].startswith("2026-10-04")
assert collect.fetch_comment_total(Fake(), "multi", 142) == 58
print("real-shape parse OK")
