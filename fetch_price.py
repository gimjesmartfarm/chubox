import os
import json
import urllib.request
from datetime import datetime, timedelta, timezone

# 서비스키는 코드에 하드코딩하지 않고 GitHub Secret(환경변수)에서 읽습니다.
SERVICE_KEY = os.environ["KAT_SERVICE_KEY"]
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
            "unit": top.get("unit_nm", ""),
            "marketName": top.get("whsl_mrkt_nm", ""),
            "itemName": top.get("corp_gds_item_nm", ""),
            "variety": top.get("corp_gds_vrty_nm", ""),
            "updatedAt": now_iso,
        }
        break

    if result is None:
        result = {
            "date": today.isoformat(),
            "maxPrice": None,
            "updatedAt": now_iso,
        }

    with open("price.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("저장 완료:", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
