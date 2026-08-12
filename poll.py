#!/usr/bin/env python3
"""Single GBFS poll for GitHub Actions (git-scraping pattern).

Each workflow run calls this once: it fetches the current vehicle positions
from Rome's free-floating operators and writes one compact snapshot per
operator. The workflow then commits the new files back to the repo.

Lite: only available (rideable) vehicles, minimal columns.
Deps: requests, pandas, pyarrow.
"""
import datetime as dt
from pathlib import Path
import requests
import pandas as pd

OPERATORS = {
    "bird":    "https://mds.bird.co/gbfs/v2/public/rome/gbfs.json",
    "dott":    "https://gbfs.api.ridedott.com/public/v2/rome/gbfs.json",
    "cooltra": "https://maas.zeus.cooltra.com/gbfs/rome/3.0/en/gbfs.json",
}
SNAP_DIR = Path(__file__).parent / "snapshots"
HEADERS = {"User-Agent": "roma-bikeshare-research/1.0 (academic)"}


def get(url):
    r = requests.get(url, timeout=25, headers=HEADERS)
    r.raise_for_status()
    return r.json()


def feed_url(gbfs):
    d = gbfs["data"]
    feeds = d["feeds"] if "feeds" in d else d[next(iter(d))]["feeds"]
    by = {f["name"]: f["url"] for f in feeds}
    for n in ("free_bike_status", "vehicle_status"):
        if n in by:
            return by[n]
    return None


def vehicles(feed):
    items = feed["data"].get("bikes") or feed["data"].get("vehicles") or []
    out = []
    for v in items:
        if v.get("is_disabled") or v.get("is_reserved"):
            continue
        out.append({"vehicle_id": v.get("bike_id") or v.get("vehicle_id"),
                    "lat": v.get("lat"), "lon": v.get("lon")})
    return out


def main():
    ts = dt.datetime.now(dt.timezone.utc)
    stamp = ts.strftime("%Y%m%dT%H%M%SZ")
    day = ts.strftime("%Y-%m-%d")
    for op, url in OPERATORS.items():
        try:
            fu = feed_url(get(url))
            if not fu:
                continue
            rows = vehicles(get(fu))
            if not rows:
                continue
            df = pd.DataFrame(rows)
            df["ts"] = ts
            d = SNAP_DIR / op / day
            d.mkdir(parents=True, exist_ok=True)
            df.to_parquet(d / f"{stamp}.parquet", index=False)
            print(f"{op}: {len(df)} vehicles")
        except Exception as e:
            print(f"{op}: ERROR {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
