import os
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

# 서비스키는 코드에 하드코딩하지 않고 GitHub Secret(환경변수)에서 읽습니다.
SERVICE_KEY = os.environ["KAT_SERVICE_KEY"]
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")  # 없으면 브리핑 생략
BASE = "https://apis.data.go.kr/B552845/katRealTime2/trades2"
KST = timezone(timedelta(hours=9))
MAX_LOOKBACK_DAYS = 14  # 경매가 없는 날이면 최대 14일 전까지 거슬러 올라가며 탐색


def build_url(date_str: str) -> str:
    # serviceKey는 동작이 확인된 형태 그대로 사용 (인코딩하지 않음)
    return (
        f"{BASE}?serviceKey={SERVICE_KEY}"
        "&numOfRows=1000"
        "&cond[whsl_mrkt_cd::EQ]=350301"
        "&cond[corp_cd::EQ]=35030101"
        "&cond[gds_lclsf_cd::EQ]=10"
        "&cond[gds_mclsf_cd::EQ]=10"
        "&cond[gds_sclsf_cd::EQ]=01"
        f"&cond[trd_clcln_ymd::EQ]={date_str}"
        "&returnType=JSON"
    )


def fetch(date_str: str) -> dict:
    req = urllib.request.Request(
        build_url(date_str), headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_items(data: dict) -> list:
    items = (
        data.get("response", {})
        .get("body", {})
        .get("items", {})
    )
    if not isinstance(items, dict):
        return []
    item = items.get("item", [])
    if isinstance(item, dict):  # 결과가 1건이면 list가 아닌 dict로 올 수 있음
        item = [item]
    return item or []


def build_history(today, days=7, max_lookback=30, delay=0.2):
    """경매가 있었던 최근 days일치 {date, maxPrice}를 과거로 거슬러 수집 (최초 1회용)."""
    history = []
    for back in range(0, max_lookback + 1):
        if len(history) >= days:
            break
        date_str = (today - timedelta(days=back)).isoformat()
        try:
            items = extract_items(fetch(date_str))
        except Exception as e:
            print(f"[history {date_str}] 호출 실패: {e}")
            continue
        if items:
            top = max(items, key=lambda x: float(x.get("scsbd_prc", 0)))
            history.append({"date": date_str, "maxPrice": int(float(top["scsbd_prc"]))})
        time.sleep(delay)  # 너무 빠른 연속 호출 방지
    history.reverse()  # 과거 -> 최신 순
    return history


def make_briefing(history, today_entry):
    """history(과거~오늘)를 근거로 1~2문장 한국어 시세 브리핑 생성. 가격은 언급하지 않음."""
    if not GEMINI_API_KEY or not history:
        return ""

    prompt = (
        "너는 부추 시세를 연구하는 연구원이야.\n"
        f"부추 도매 최고가(원) 추이(과거→오늘): {json.dumps(history, ensure_ascii=False)}\n"
        f"오늘({today_entry['date']}) 최고가는 {today_entry['maxPrice']}원.\n"
        "이 추이를 바탕으로 최근 시세 흐름(오름세/내림세/안정세)만 구매자에게 친근하게 알려주는 1~2문장 한국어 문구를 써줘.\n"
        "하십시오체보다는 해요체가 좋아.\n"
        "필요하면 앞에 번호를 붙이고 문장마다 줄바꿈을해서 보여줘도 좋아.\n"
        "규칙: 구체적인 가격이나 비율, 숫자는 문장에 쓰지 말 것, 과장·이모지 금지, 문구만 출력."
    )

    MODEL = "gemini-3.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}]
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except Exception as e:
        print(f"브리핑 생성 실패: {e}")
        return ""


def main():
    today = datetime.now(KST).date()
    now_iso = datetime.now(KST).isoformat(timespec="seconds")
    result = None

    for back in range(0, MAX_LOOKBACK_DAYS + 1):
        date_str = (today - timedelta(days=back)).isoformat()
        try:
            data = fetch(date_str)
        except Exception as e:
            print(f"[{date_str}] 호출 실패: {e}")
            continue

        items = extract_items(data)
        print(f"[{date_str}] 건수: {len(items)}")
        if not items:
            continue

        top = max(items, key=lambda x: float(x.get("scsbd_prc", 0)))
        result = {
            "date": date_str,
            "maxPrice": int(float(top["scsbd_prc"])),  # '.' 이하 버림
            "unitQty": int(float(top.get("unit_qty") or 0)),  # 단위물량 (예: 4)
            "unit": top.get("unit_nm", ""),                   # 단위명 (예: kg)
            "marketName": top.get("whsl_mrkt_nm", ""),
            "itemName": top.get("corp_gds_item_nm", ""),
            "variety": top.get("corp_gds_vrty_nm", ""),
            "auctionAt": top.get("scsbd_dt", ""),  # 최고가 항목의 낙찰일시
            "updatedAt": now_iso,                  # 데이터를 가져온(스크립트 실행) 시각
        }
        break

    if result is None:
        result = {
            "date": today.isoformat(),
            "maxPrice": None,
            "updatedAt": now_iso,
        }

    # ── history: 비어있으면 과거치로 백필, 이후엔 오늘치만 추가 ──────────
    try:
        with open("price.json", "r", encoding="utf-8") as f:
            history = json.load(f).get("history", [])
    except (FileNotFoundError, json.JSONDecodeError):
        history = []

    if not history:
        # 최초 1회: 과거 경매일 7일치 백필
        history = build_history(today)
    elif result.get("maxPrice") is not None:
        # 이후: 오늘 도매가만 추가(같은 날 재실행이면 덮어쓰기), 최근 7일 유지
        entry = {"date": result["date"], "maxPrice": result["maxPrice"]}
        if history[-1].get("date") != result["date"]:
            history.append(entry)
        else:
            history[-1] = entry
        history = history[-7:]

    result["history"] = history

    # ── 브리핑: 오늘 도매가가 있고, 오늘자 브리핑이 아직 없을 때만 생성 ──
    prev_briefing = ""
    prev_briefing_date = ""
    try:
        with open("price.json", "r", encoding="utf-8") as f:
            _prev = json.load(f)
        prev_briefing = _prev.get("briefing", "")
        prev_briefing_date = _prev.get("briefingDate", "")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    if result.get("maxPrice") is not None and prev_briefing_date != result["date"]:
        text = make_briefing(
            history, {"date": result["date"], "maxPrice": result["maxPrice"]}
        )
        clean = " ".join(text.split())
        has_hangul = any("가" <= ch <= "힣" for ch in clean)
        if clean and len(clean) >= 10 and has_hangul:
            result["briefing"] = clean
            result["briefingDate"] = result["date"]
        else:
            result["briefing"] = prev_briefing  # 불량/실패 시 이전 문구 유지
            result["briefingDate"] = prev_briefing_date
    else:
        result["briefing"] = prev_briefing  # 이미 오늘자 있으면 재사용
        result["briefingDate"] = prev_briefing_date
    # ──────────────────────────────────────────────────────────────────

    with open("price.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("저장 완료:", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
