"""Pull day-ahead forecast highs per city from Open-Meteo previous-runs API.

Writes data/forecasts.csv: series, date (local), fc_high_f (forecast issued the
previous day, max of hourly temps over the local calendar day).
Usage: python3 pull_forecasts.py START END   (YYYY-MM-DD)
"""
import csv, json, os, sys, urllib.parse, urllib.request, time

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# series -> (lat, lon, tz) at the settlement station
CITIES = {
    "KXHIGHNY":   (40.779, -73.969, "America/New_York"),
    "KXHIGHCHI":  (41.786, -87.752, "America/Chicago"),
    "KXHIGHMIA":  (25.789, -80.316, "America/New_York"),
    "KXHIGHAUS":  (30.183, -97.680, "America/Chicago"),
    "KXHIGHLAX":  (33.938, -118.389, "America/Los_Angeles"),
    "KXHIGHDEN":  (39.847, -104.656, "America/Denver"),
    "KXHIGHPHIL": (39.872, -75.241, "America/New_York"),
}

def fetch(lat, lon, tz, start, end):
    q = dict(latitude=lat, longitude=lon, start_date=start, end_date=end, timezone=tz,
             hourly="temperature_2m_previous_day1", temperature_unit="fahrenheit")
    url = "https://previous-runs-api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q)
    for a in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            err = e; time.sleep(3 * (a + 1))
    raise RuntimeError(err)

def main():
    start, end = sys.argv[1], sys.argv[2]
    rows = []
    for s, (lat, lon, tz) in CITIES.items():
        h = fetch(lat, lon, tz, start, end)["hourly"]
        day = {}
        for t, v in zip(h["time"], h["temperature_2m_previous_day1"]):
            if v is not None:
                day.setdefault(t[:10], []).append(v)
        for d, vs in sorted(day.items()):
            if len(vs) >= 20:
                rows.append(dict(series=s, date=d, fc_high_f=round(max(vs), 1)))
        print(s, len(day), flush=True)
    with open(os.path.join(DATA, "forecasts.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["series", "date", "fc_high_f"])
        w.writeheader(); w.writerows(rows)
    print("wrote", len(rows))

if __name__ == "__main__":
    main()
