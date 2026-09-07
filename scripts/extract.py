#!/usr/bin/env python3
"""
京王バス GTFS(-JP) zip から、貝取周辺 8 方向の発車時刻を抽出して
data/timetable.json を生成するスクリプト。

使い方:
  python3 scripts/extract.py keio_bus.zip                 # 通常実行
  python3 scripts/extract.py keio_bus.zip --list-stops 貝取  # 停留所名の確認

出力 JSON は GTFS の考え方をそのまま持ち込んでいる:
  services   : service_id ごとの運行曜日・期間・例外日（calendar / calendar_dates）
  directions : 8 方向それぞれの便一覧（service_id, 出発時刻, 系統, 行先）
アプリ側は「今日どの service_id が有効か」を計算してから便を絞り込む。
これで祝日・年末年始などの特別ダイヤも GTFS 通りに再現できる。
"""

import csv
import io
import json
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 抽出したい 8 方向。origin / dest は停留所名（完全一致）で照合する。
# 「ケ」「ヶ」の揺れは normalize() で吸収する。
# ---------------------------------------------------------------------------
DIRECTIONS = [
    # station: 画面の見出しになる駅。role: out=家から駅へ / home=駅から家へ
    {"id": "kaidori_park_to_nagayama",   "origin": "貝取北公園通り", "dest": "永山駅",       "station": "永山駅",       "role": "out"},
    {"id": "kaidori_center_to_nagayama", "origin": "貝取北センター", "dest": "永山駅",       "station": "永山駅",       "role": "out"},
    {"id": "nagayama_to_kaidori_park",   "origin": "永山駅",         "dest": "貝取北公園通り", "station": "永山駅",       "role": "home"},
    {"id": "nagayama_to_kaidori_center", "origin": "永山駅",         "dest": "貝取北センター", "station": "永山駅",       "role": "home"},
    {"id": "kaidori_park_to_tamacenter", "origin": "貝取北公園通り", "dest": "多摩センター駅", "station": "多摩センター駅", "role": "out"},
    {"id": "kaidori_center_to_tamacenter","origin": "貝取北センター", "dest": "多摩センター駅", "station": "多摩センター駅", "role": "out"},
    {"id": "tamacenter_to_kaidori_park", "origin": "多摩センター駅", "dest": "貝取北公園通り", "station": "多摩センター駅", "role": "home"},
    {"id": "tamacenter_to_kaidori_center","origin": "多摩センター駅", "dest": "貝取北センター", "station": "多摩センター駅", "role": "home"},
    {"id": "kaidori_center_to_seiseki",  "origin": "貝取北センター", "dest": "聖蹟桜ヶ丘駅", "station": "聖蹟桜ヶ丘駅", "role": "out"},
    {"id": "kaidori_to_seiseki",         "origin": "貝取",           "dest": "聖蹟桜ヶ丘駅", "station": "聖蹟桜ヶ丘駅", "role": "out"},
    {"id": "seiseki_to_kaidori_center",  "origin": "聖蹟桜ヶ丘駅",   "dest": "貝取北センター", "station": "聖蹟桜ヶ丘駅", "role": "home"},
    {"id": "minami_kaidori_to_seiseki",  "origin": "南貝取",         "dest": "聖蹟桜ヶ丘駅", "station": "聖蹟桜ヶ丘駅", "role": "out"},
    {"id": "seiseki_to_minami_kaidori",  "origin": "聖蹟桜ヶ丘駅",   "dest": "南貝取",       "station": "聖蹟桜ヶ丘駅", "role": "home"},
    {"id": "seiseki_to_kaidori",         "origin": "聖蹟桜ヶ丘駅",   "dest": "貝取",         "station": "聖蹟桜ヶ丘駅", "role": "home"},
]

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "timetable.json"


def normalize(name: str) -> str:
    """停留所名の表記揺れを吸収する。"""
    return (
        name.replace("ケ", "ヶ")
        .replace("（", "(").replace("）", ")")
        .replace(" ", "").replace("　", "")
    )


def read_table(zf: zipfile.ZipFile, name: str) -> list[dict]:
    """zip 内の CSV を辞書のリストとして読む。無ければ空リスト。"""
    # GTFS-JP は BOM 付き UTF-8 のことが多いので utf-8-sig で読む
    try:
        raw = zf.read(name)
    except KeyError:
        return []
    text = raw.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def hhmmss_to_minutes(t: str) -> int:
    """'25:10:00' のような 24 時超え表記もそのまま分に変換する。"""
    h, m, *_ = t.split(":")
    return int(h) * 60 + int(m)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    zip_path = Path(sys.argv[1])
    if not zip_path.exists():
        print(f"zip が見つかりません: {zip_path}")
        return 1

    with zipfile.ZipFile(zip_path) as zf:
        stops = read_table(zf, "stops.txt")
        routes = read_table(zf, "routes.txt")
        trips = read_table(zf, "trips.txt")
        stop_times = read_table(zf, "stop_times.txt")
        calendar = read_table(zf, "calendar.txt")
        calendar_dates = read_table(zf, "calendar_dates.txt")
        feed_info = read_table(zf, "feed_info.txt")
        agency = read_table(zf, "agency.txt")

    # --- 停留所名の確認モード ------------------------------------------------
    if "--list-stops" in sys.argv:
        idx = sys.argv.index("--list-stops")
        keyword = normalize(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else ""
        print(f"'{keyword}' を含む停留所:")
        for s in stops:
            if keyword in normalize(s["stop_name"]):
                print(f"  {s['stop_id']:>12}  {s['stop_name']}  (location_type={s.get('location_type','')})")
        return 0

    # --- 停留所名 → stop_id 群 ------------------------------------------------
    # 同名の乗り場（0979_01, 0979_02 …）が複数あるので、名前が一致するものを全部拾う。
    # 「多摩センター駅西口」のような別停留所を拾わないよう、完全一致で照合する。
    # location_type=1 (親駅) は stop_times に出てこないので除外。
    def stop_ids_for(name: str) -> set[str]:
        key = normalize(name)
        ids = {
            s["stop_id"] for s in stops
            if normalize(s["stop_name"]) == key and s.get("location_type", "") in ("", "0")
        }
        if not ids:
            print(f"警告: 停留所 '{name}' が見つかりません。--list-stops で名前を確認してください。")
        return ids

    route_by_id = {r["route_id"]: r for r in routes}
    platform_by_stop = {s["stop_id"]: (s.get("platform_code") or "").lstrip("0") or s.get("platform_code", "") for s in stops}
    trip_by_id = {t["trip_id"]: t for t in trips}

    # trip_id → その便の停車列（stop_sequence 順）
    stops_by_trip: dict[str, list[dict]] = defaultdict(list)
    for st in stop_times:
        stops_by_trip[st["trip_id"]].append(st)
    for seq in stops_by_trip.values():
        seq.sort(key=lambda x: int(x["stop_sequence"]))

    # --- 8 方向の便を抽出 -----------------------------------------------------
    used_services: set[str] = set()
    out_directions = []

    for d in DIRECTIONS:
        origin_ids = stop_ids_for(d["origin"])
        dest_ids = stop_ids_for(d["dest"])
        found = []

        for trip_id, seq in stops_by_trip.items():
            # 出発停留所と到着停留所が、この順番で含まれている便だけ拾う
            origin_row = next((r for r in seq if r["stop_id"] in origin_ids), None)
            if origin_row is None:
                continue
            o_seq = int(origin_row["stop_sequence"])
            dest_row = next((r for r in seq if r["stop_id"] in dest_ids and int(r["stop_sequence"]) > o_seq), None)
            if dest_row is None:
                continue

            trip = trip_by_id.get(trip_id, {})
            route = route_by_id.get(trip.get("route_id", ""), {})
            dep = origin_row.get("departure_time") or origin_row.get("arrival_time")
            arr = dest_row.get("arrival_time") or dest_row.get("departure_time")
            if not dep or not arr:
                continue

            route_name = route.get("route_short_name") or route.get("route_long_name") or ""
            route_name = route_name.replace("多摩市ミニバス ", "")   # バッジ表示用に短くする
            route_name = route_name.translate(str.maketrans("０１２３４５６７８９", "0123456789"))  # 全角数字→半角

            found.append({
                "s": trip.get("service_id", ""),               # service_id
                "t": hhmmss_to_minutes(dep),                    # 出発時刻（分）
                "d": hhmmss_to_minutes(arr) - hhmmss_to_minutes(dep),  # 所要時間（分）
                "r": route_name,                                # 系統
                "h": trip.get("trip_headsign", ""),             # 行先
                "p": platform_by_stop.get(origin_row["stop_id"], ""),  # 出発停留所の乗り場番号
            })

        # 循環路線の「遠回り」を除く。
        # 例: 東西線（右循環）は貝取北公園通り→永山駅→…→多摩センター駅と一周してから着くので 78 分かかる。
        # 方向ごとの最短所要時間の 2.5 倍を超える便は、実用上その方向の便ではないとみなして落とす。
        if found:
            fastest = min(t["d"] for t in found)
            kept = [t for t in found if t["d"] <= fastest * 2.5]
            dropped = len(found) - len(kept)
            found = kept
        else:
            dropped = 0

        for t in found:
            used_services.add(t["s"])

        found.sort(key=lambda x: (x["s"], x["t"]))
        print(f"{d['origin']} → {d['dest']}: {len(found)} 便" + (f"（遠回り {dropped} 便を除外）" if dropped else ""))
        out_directions.append({**d, "trips": found})

    # --- 使われている service_id の暦だけを出力 --------------------------------
    services: dict[str, dict] = {}
    for c in calendar:
        if c["service_id"] not in used_services:
            continue
        services[c["service_id"]] = {
            "days": [int(c[k]) for k in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")],
            "start": c["start_date"],
            "end": c["end_date"],
            "add": [],
            "remove": [],
        }
    for cd in calendar_dates:
        sid = cd["service_id"]
        if sid not in used_services:
            continue
        # calendar.txt に無く calendar_dates だけで定義される service も許容する
        services.setdefault(sid, {"days": [0] * 7, "start": "00000000", "end": "99999999", "add": [], "remove": []})
        if cd["exception_type"] == "1":
            services[sid]["add"].append(cd["date"])
        else:
            services[sid]["remove"].append(cd["date"])

    # --- データの有効期限 -----------------------------------------------------
    valid_until = ""
    if feed_info and feed_info[0].get("feed_end_date"):
        valid_until = feed_info[0]["feed_end_date"]
    elif services:
        valid_until = max(s["end"] for s in services.values())

    result = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": (agency[0].get("agency_name") if agency else "") or "京王バス GTFS (ODPT)",
        "feed_version": feed_info[0].get("feed_version", "") if feed_info else "",
        "valid_until": valid_until,          # YYYYMMDD
        "sample": False,
        "services": services,
        "directions": out_directions,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"書き出し: {OUTPUT} ({OUTPUT.stat().st_size:,} bytes, 有効期限 {valid_until})")

    empty = [d["id"] for d in out_directions if not d["trips"]]
    if empty:
        print("注意: 便が 0 の方向があります →", ", ".join(empty))
        print("      多摩市ミニバス等が別データの場合は、その GTFS を追加で処理してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
