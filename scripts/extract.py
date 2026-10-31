#!/usr/bin/env python3
"""
京王バス GTFS(-JP) zip から、貝取周辺の各方向の発車時刻を抽出して
data/timetable.json を生成するスクリプト。

使い方:
  python3 scripts/extract.py keio_bus.zip                 # 通常実行
  python3 scripts/extract.py keio_bus.zip --list-stops 貝取  # 停留所名の確認
"""
import csv, io, json, sys, zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# station: 画面の見出しになる駅。role: out=家から駅へ / home=駅から家へ
# exclude: 系統名にこの文字列を含む便を除外する（貝取北センターの東西線は貝取北公園通りのカードで見るため）
# via    : 乗り継ぎ案内。origin→via の便と、via→dest の便（only の系統に限る）を max_wait 分以内で接続して 1 本にまとめる
DIRECTIONS = [
    {"id": "kaidori_park_to_nagayama",   "origin": "貝取北公園通り", "dest": "永山駅",       "station": "永山駅",       "role": "out"},
    {"id": "kaidori_center_to_nagayama", "origin": "貝取北センター", "dest": "永山駅",       "station": "永山駅",       "role": "out", "exclude": ["東西線"]},
    {"id": "minami_kaidori_to_nagayama", "origin": "南貝取",         "dest": "永山駅",       "station": "永山駅",       "role": "out"},
    {"id": "nagayama_to_kaidori_park",   "origin": "永山駅",         "dest": "貝取北公園通り", "station": "永山駅",       "role": "home"},
    {"id": "nagayama_to_kaidori_center", "origin": "永山駅",         "dest": "貝取北センター", "station": "永山駅",       "role": "home", "exclude": ["東西線"]},
    {"id": "nagayama_to_minami_kaidori", "origin": "永山駅",         "dest": "南貝取",       "station": "永山駅",       "role": "home"},
    {"id": "kaidori_park_to_tamacenter", "origin": "貝取北公園通り", "dest": "多摩センター駅", "station": "多摩センター駅", "role": "out"},
    {"id": "kaidori_center_to_tamacenter","origin": "貝取北センター", "dest": "多摩センター駅", "station": "多摩センター駅", "role": "out", "exclude": ["東西線"]},
    {"id": "tamacenter_to_kaidori_park", "origin": "多摩センター駅", "dest": "貝取北公園通り", "station": "多摩センター駅", "role": "home"},
    {"id": "tamacenter_to_kaidori_center","origin": "多摩センター駅", "dest": "貝取北センター", "station": "多摩センター駅", "role": "home", "exclude": ["東西線"]},
    {"id": "kaidori_center_to_seiseki",  "origin": "貝取北センター", "dest": "聖蹟桜ヶ丘駅", "station": "聖蹟桜ヶ丘駅", "role": "out"},
    {"id": "minami_kaidori_to_seiseki",  "origin": "南貝取",         "dest": "聖蹟桜ヶ丘駅", "station": "聖蹟桜ヶ丘駅", "role": "out"},
    {"id": "kaidori_to_seiseki",         "origin": "貝取",           "dest": "聖蹟桜ヶ丘駅", "station": "聖蹟桜ヶ丘駅", "role": "out"},
    {"id": "seiseki_to_kaidori_center",  "origin": "聖蹟桜ヶ丘駅",   "dest": "貝取北センター", "station": "聖蹟桜ヶ丘駅", "role": "home"},
    {"id": "seiseki_to_minami_kaidori",  "origin": "聖蹟桜ヶ丘駅",   "dest": "南貝取",       "station": "聖蹟桜ヶ丘駅", "role": "home"},
    {"id": "seiseki_to_kaidori",         "origin": "聖蹟桜ヶ丘駅",   "dest": "貝取",         "station": "聖蹟桜ヶ丘駅", "role": "home"},
    # 唐木田駅
    {"id": "kaidori_elem_to_karakida",   "origin": "貝取小学校",     "dest": "唐木田駅",     "station": "唐木田駅",     "role": "out"},
    {"id": "kaidori_park_to_karakida_via_tc", "origin": "貝取北公園通り", "dest": "唐木田駅", "station": "唐木田駅", "role": "out",
     "via": "多摩センター駅", "max_wait": 30, "only": ["東西線"], "label": "多摩センター乗継"},
    {"id": "karakida_to_kaidori_elem",   "origin": "唐木田駅",       "dest": "貝取小学校",   "station": "唐木田駅",     "role": "home"},
]

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "timetable.json"

def normalize(name):
    return name.replace("ケ", "ヶ").replace("（", "(").replace("）", ")").replace(" ", "").replace("　", "")

def read_table(zf, name):
    try: raw = zf.read(name)
    except KeyError: return []
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

def hhmmss_to_minutes(t):
    h, m, *_ = t.split(":"); return int(h) * 60 + int(m)

def main():
    if len(sys.argv) < 2: print(__doc__); return 1
    zip_path = Path(sys.argv[1])
    with zipfile.ZipFile(zip_path) as zf:
        stops = read_table(zf, "stops.txt"); routes = read_table(zf, "routes.txt")
        trips = read_table(zf, "trips.txt"); stop_times = read_table(zf, "stop_times.txt")
        calendar = read_table(zf, "calendar.txt"); calendar_dates = read_table(zf, "calendar_dates.txt")
        feed_info = read_table(zf, "feed_info.txt"); agency = read_table(zf, "agency.txt")

    if "--list-stops" in sys.argv:
        idx = sys.argv.index("--list-stops")
        key = normalize(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else ""
        for s in stops:
            if key in normalize(s["stop_name"]):
                print(f"  {s['stop_id']:>12}  {s['stop_name']}  (location_type={s.get('location_type','')})")
        return 0

    def stop_ids_for(name):
        key = normalize(name)
        ids = {s["stop_id"] for s in stops if normalize(s["stop_name"]) == key and s.get("location_type", "") in ("", "0")}
        if not ids: print(f"警告: 停留所 '{name}' が見つかりません。")
        return ids

    route_by_id = {r["route_id"]: r for r in routes}
    trip_by_id = {t["trip_id"]: t for t in trips}
    platform_by_stop = {s["stop_id"]: (s.get("platform_code") or "").lstrip("0") or s.get("platform_code", "") for s in stops}
    stops_by_trip = defaultdict(list)
    for st in stop_times: stops_by_trip[st["trip_id"]].append(st)
    for seq in stops_by_trip.values(): seq.sort(key=lambda x: int(x["stop_sequence"]))

    def collect(origin, dest, exclude=(), only=()):
        """origin の後に dest を通る便を集める。循環路線の遠回り（最短の 2.5 倍超）は除外。"""
        origin_ids, dest_ids = stop_ids_for(origin), stop_ids_for(dest)
        found = []
        for trip_id, seq in stops_by_trip.items():
            origin_row = next((r for r in seq if r["stop_id"] in origin_ids), None)
            if origin_row is None: continue
            o_seq = int(origin_row["stop_sequence"])
            dest_row = next((r for r in seq if r["stop_id"] in dest_ids and int(r["stop_sequence"]) > o_seq), None)
            if dest_row is None: continue
            trip = trip_by_id.get(trip_id, {}); route = route_by_id.get(trip.get("route_id", ""), {})
            dep = origin_row.get("departure_time") or origin_row.get("arrival_time")
            arr = dest_row.get("arrival_time") or dest_row.get("departure_time")
            if not dep or not arr: continue
            route_name = (route.get("route_short_name") or route.get("route_long_name") or "").replace("多摩市ミニバス ", "")
            route_name = route_name.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            if any(x in route_name for x in exclude): continue
            if only and not any(x in route_name for x in only): continue
            found.append({"s": trip.get("service_id", ""), "t": hhmmss_to_minutes(dep),
                          "d": hhmmss_to_minutes(arr) - hhmmss_to_minutes(dep), "r": route_name,
                          "h": trip.get("trip_headsign", ""), "p": platform_by_stop.get(origin_row["stop_id"], "")})
        dropped = 0
        if found:
            fastest = min(t["d"] for t in found)
            kept = [t for t in found if t["d"] <= fastest * 2.5]; dropped = len(found) - len(kept); found = kept
        return found, dropped

    used_services, out_directions = set(), []
    for d in DIRECTIONS:
        if d.get("via"):
            leg1, _ = collect(d["origin"], d["via"], d.get("exclude", ()))
            leg2, _ = collect(d["via"], d["dest"], (), d.get("only", ()))
            found = []
            for a in leg1:
                arr1 = a["t"] + a["d"]
                cands = sorted((b for b in leg2 if b["s"] == a["s"] and arr1 + 2 <= b["t"] <= arr1 + d["max_wait"]), key=lambda b: b["t"])
                if not cands: continue
                b = cands[0]
                found.append({"s": a["s"], "t": a["t"], "d": (b["t"] + b["d"]) - a["t"], "r": a["r"], "h": d.get("label", ""), "p": a["p"],
                              "v": {"n": d["via"].replace("駅", ""), "a": arr1, "t": b["t"], "r": b["r"], "p": b["p"]}})
            dropped = 0
        else:
            found, dropped = collect(d["origin"], d["dest"], d.get("exclude", ()))
        for t in found: used_services.add(t["s"])
        found.sort(key=lambda x: (x["s"], x["t"]))
        print(f"{d['origin']} → {d['dest']}" + (f"（{d['via']}乗継）" if d.get("via") else "") + f": {len(found)} 便" + (f"（遠回り {dropped} 便を除外）" if dropped else ""))
        out_directions.append({k: v for k, v in d.items()} | {"trips": found})

    services = {}
    for c in calendar:
        if c["service_id"] not in used_services: continue
        services[c["service_id"]] = {"days": [int(c[k]) for k in ("monday","tuesday","wednesday","thursday","friday","saturday","sunday")],
                                     "start": c["start_date"], "end": c["end_date"], "add": [], "remove": []}
    for cd in calendar_dates:
        sid = cd["service_id"]
        if sid not in used_services: continue
        services.setdefault(sid, {"days": [0]*7, "start": "00000000", "end": "99999999", "add": [], "remove": []})
        (services[sid]["add"] if cd["exception_type"] == "1" else services[sid]["remove"]).append(cd["date"])

    valid_until = feed_info[0].get("feed_end_date", "") if feed_info else ""
    if not valid_until and services: valid_until = max(s["end"] for s in services.values())
    result = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
              "source": (agency[0].get("agency_name") if agency else "") or "京王バス GTFS (ODPT)",
              "feed_version": feed_info[0].get("feed_version", "") if feed_info else "",
              "valid_until": valid_until, "sample": False, "services": services, "directions": out_directions}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"書き出し: {OUTPUT} ({OUTPUT.stat().st_size:,} bytes, 有効期限 {valid_until})")
    empty = [d["id"] for d in out_directions if not d["trips"]]
    if empty: print("注意: 便が 0 の方向があります →", ", ".join(empty))
    return 0

if __name__ == "__main__": sys.exit(main())
