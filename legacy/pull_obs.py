"""Hourly ASOS temperature observations per settlement station from Iowa Environmental Mesonet.

Writes data/obs.csv: series, valid_utc, tmpf.
Usage: python3 -m legacy.pull_obs START END   (YYYY-MM-DD, inclusive)
"""
import csv, os, sys, time, urllib.request
from legacy.pull_forecasts import DATA

STATIONS = {"KXHIGHNY": "NYC", "KXHIGHCHI": "MDW", "KXHIGHMIA": "MIA", "KXHIGHAUS": "AUS",
            "KXHIGHLAX": "LAX", "KXHIGHDEN": "DEN", "KXHIGHPHIL": "PHL"}


def main():
    (y1, m1, d1), (y2, m2, d2) = (map(int, a.split("-")) for a in sys.argv[1:3])
    q = "&".join(f"station={s}" for s in STATIONS.values())
    url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?" + q +
           f"&data=tmpf&year1={y1}&month1={m1}&day1={d1}&year2={y2}&month2={m2}&day2={d2}"
           "&tz=Etc/UTC&format=onlycomma&latlon=no&missing=empty&direct=no"
           "&report_type=3&report_type=4")
    for a in range(5):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                lines = r.read().decode().splitlines()
            break
        except Exception as e:
            err = e; time.sleep(5 * (a + 1))
    else:
        raise RuntimeError(err)
    series = {v: k for k, v in STATIONS.items()}
    rows = [dict(series=series[st], valid_utc=t, tmpf=v)
            for st, t, v in csv.reader(lines[1:]) if v]
    with open(os.path.join(DATA, "obs.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["series", "valid_utc", "tmpf"])
        w.writeheader(); w.writerows(rows)
    print("wrote", len(rows))


if __name__ == "__main__":
    main()
