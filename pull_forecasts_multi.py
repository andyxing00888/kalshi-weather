"""Day-ahead forecast highs per city from several NWP models (Open-Meteo previous-runs).

Writes data/forecasts_multi.csv: series, date, one fc_<model> column per model.
Usage: python3 pull_forecasts_multi.py START END   (YYYY-MM-DD)
"""
import csv, json, os, sys, time, urllib.parse, urllib.request
from pull_forecasts import CITIES, DATA

MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_seamless", "ukmo_seamless"]


def fetch(lat, lon, tz, start, end):
    q = dict(latitude=lat, longitude=lon, start_date=start, end_date=end, timezone=tz,
             hourly="temperature_2m_previous_day1", models=",".join(MODELS),
             temperature_unit="fahrenheit")
    url = "https://previous-runs-api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q)
    for a in range(5):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.load(r)
        except Exception as e:
            err = e; time.sleep(3 * (a + 1))
    raise RuntimeError(err)


def main():
    start, end = sys.argv[1], sys.argv[2]
    rows = []
    for s, (lat, lon, tz) in CITIES.items():
        h = fetch(lat, lon, tz, start, end)["hourly"]
        day = {m: {} for m in MODELS}
        for m in MODELS:
            for t, v in zip(h["time"], h["temperature_2m_previous_day1_" + m]):
                if v is not None:
                    day[m].setdefault(t[:10], []).append(v)
        for d in sorted({d for m in MODELS for d in day[m]}):
            r = dict(series=s, date=d)
            for m in MODELS:
                vs = day[m].get(d, [])
                r["fc_" + m] = round(max(vs), 1) if len(vs) >= 20 else ""
            rows.append(r)
        print(s, len(rows), flush=True)
    with open(os.path.join(DATA, "forecasts_multi.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["series", "date"] + ["fc_" + m for m in MODELS])
        w.writeheader(); w.writerows(rows)
    print("wrote", len(rows))


if __name__ == "__main__":
    main()
