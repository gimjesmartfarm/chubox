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

# 지역별 도매시장 (비교 그래프용) — 두 시장인 지역은 높은 가격 채택
REGION_MARKETS = {
    "서울": ["110001", "110008"],
    "인천": ["230001", "230003"],
    "대구": ["220001"],
    "대전": ["250001", "250003"],
    "부산": ["210009", "210001"],
    "광주": ["240001", "240004"],
    "전주": ["350101"],
    "익산": ["350301"],
}


def build_region_url(mrkt_cd: str, date_str: str) -> str:
    # 지역 비교용: corp_cd, gds_sclsf_cd 조건 없이 부추(중분류) 전체 조회
    return (
        f"{BASE}?serviceKey={SERVICE_KEY}"
        "&numOfRows=1000"
        f"&cond[whsl_mrkt_cd::EQ]={mrkt_cd}"
        "&cond[gds_lclsf_cd::EQ]=10"
        "&cond[gds_mclsf_cd::EQ]=10"
        f"&cond[trd_clcln_ymd::EQ]={date_str}"
        "&returnType=JSON"
    )


def fetch_region_max(codes, date_str, delay=0.15):
    """지역(시장코드 묶음)의 4kg 단위 최고가. 4kg 항목 + 수량 10 이상만 사용."""
    best = None
    for code in codes:
        try:
            req = urllib.request.Request(
                build_region_url(code, date_str), headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                items = extract_items(json.loads(resp.read().decode("utf-8")))
        except Exception as e:
            print(f"[지역 {code} {date_str}] 호출 실패: {e}")
            continue
        for x in items:
            try:
                uq = float(x.get("unit_qty") or 0)
                qty = float(x.get("qty") or 0)
                prc = float(x.get("scsbd_prc") or 0)
            except ValueError:
                continue
            # 4kg 단위 + 수량 10 이상만 후보로
            if uq != 4 or qty < 10 or prc <= 0:
                continue
            if best is None or prc > best:
                best = prc
        time.sleep(delay)
    return int(best) if best is not None else None


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
            candidates = []
            for x in items:
                try:
                    uq = float(x.get("unit_qty") or 0)
                    qty = float(x.get("qty") or 0)
                    prc = float(x.get("scsbd_prc") or 0)
                except ValueError:
                    continue
                if uq != 4 or qty < 10 or prc <= 0:
                    continue
                candidates.append(prc)
            if candidates:
                history.append({"date": date_str, "maxPrice": int(max(candidates))})
        time.sleep(delay)  # 너무 빠른 연속 호출 방지
    history.reverse()  # 과거 -> 최신 순
    return history


def make_briefing(history, today_entry):
    if not GEMINI_API_KEY or not history:
        return ""

    prompt = (
        "너는 부추 시세를 연구하는 연구원이야.\n"
        f"부추 도매 최고가(원) 추이(과거→오늘): {json.dumps(history, ensure_ascii=False)}\n"
        f"오늘({today_entry['date']}) 최고가는 {today_entry['maxPrice']}원.\n"
        "이 추이를 바탕으로 최근 시세 흐름(오름세/내림세/안정세)만 구매자에게 친근하게 알려주는 한국어 2문장으로 문구를 써줘.\n"
        "하십시오체보다는 해요체가 좋아.\n"
        "규칙: 구체적인 가격이나 비율, 숫자는 문장에 쓰지 말 것, 과장·이모지 금지, 문구만 출력."
    )

    # 모델 폴백 순서: 3.5-flash → 3-flash → 3.1-flash-lite
    MODELS = ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.1-flash-lite"]
    MAX_ATTEMPTS = 3  # 초기 1회 + 재시도 2회
    BASE_DELAY = 5  # 5 → 10초

    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
        )

        for attempt in range(MAX_ATTEMPTS):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                print(f"브리핑 생성 성공 ({model})")
                return text
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 503) and attempt < MAX_ATTEMPTS - 1:
                    wait = BASE_DELAY * (2**attempt)  # 5 → 10
                    print(
                        f"[{model}] {e.code} - {wait}초 후 재시도 ({attempt+1}/{MAX_ATTEMPTS-1})"
                    )
                    time.sleep(wait)
                else:
                    print(f"[{model}] 실패: {e}")
                    break  # 다음 모델로
            except Exception as e:
                if attempt < MAX_ATTEMPTS - 1:
                    wait = BASE_DELAY * (2**attempt)
                    print(
                        f"[{model}] 일시 오류({e}) - {wait}초 후 재시도 ({attempt+1}/{MAX_ATTEMPTS-1})"
                    )
                    time.sleep(wait)
                else:
                    print(f"[{model}] 실패: {e}")
                    break  # 다음 모델로

    print("브리핑 생성 실패: 모든 모델 소진")
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

        # 4kg 단위 + 수량 10 이상인 항목만 후보로
        candidates = []
        for x in items:
            try:
                uq = float(x.get("unit_qty") or 0)
                qty = float(x.get("qty") or 0)
                prc = float(x.get("scsbd_prc") or 0)
            except ValueError:
                continue
            if uq != 4 or qty < 10 or prc <= 0:
                continue
            candidates.append(x)

        if not candidates:
            print(f"[{date_str}] 4kg·수량10이상 항목 없음, 건너뜀")
            continue

        top = max(candidates, key=lambda x: float(x.get("scsbd_prc", 0)))
        result = {
            "date": date_str,
            "maxPrice": int(float(top["scsbd_prc"])),
            "unitQty": int(float(top.get("unit_qty") or 0)),
            "unit": top.get("unit_nm", ""),
            "marketName": top.get("whsl_mrkt_nm", ""),
            "itemName": top.get("corp_gds_item_nm", ""),
            "variety": top.get("corp_gds_vrty_nm", ""),
            "auctionAt": top.get("scsbd_dt", ""),
            "updatedAt": now_iso,
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

    # ── 지역별 최고가(4kg 환산, 비교 그래프용) ─────────────────────────
    try:
        with open("price.json", "r", encoding="utf-8") as f:
            regions = json.load(f).get("regions", {})
    except (FileNotFoundError, json.JSONDecodeError):
        regions = {}

    today_str = today.isoformat()
    for name, codes in REGION_MARKETS.items():
        if regions.get(name, {}).get("date") == today_str:
            continue  # 오늘 값 이미 확보 → 재호출 안 함
        price = fetch_region_max(codes, today_str)
        if price is not None:
            regions[name] = {"date": today_str, "maxPrice4kg": price}
            print(f"[지역 {name}] {price}원 (4kg 환산)")
        # 오늘 데이터 없으면(휴무) 이전 값 그대로 유지

    # 7일 넘게 갱신 안 된 지역은 제거 (너무 오래된 값 표시 방지)
    cutoff = (today - timedelta(days=7)).isoformat()
    regions = {k: v for k, v in regions.items() if v.get("date", "") >= cutoff}

    result["regions"] = regions
    # ──────────────────────────────────────────────────────────────────

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
