#!/usr/bin/env python3
"""Weekly processing of accumulated Rome GBFS snapshots -> demand tables."""
import datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd
import h3

SNAP = Path("snapshots")
OUT = Path("processed")
RES = 9  # ~170 m hexagons


def cell(lat, lon):
    return h3.latlng_to_cell(lat, lon, RES)


def available_set(df):
    if "is_disabled" in df.columns and "is_reserved" in df.columns:
        df = df[(~df["is_disabled"].fillna(False)) & (~df["is_reserved"].fillna(False))]
    sub = df.dropna(subset=["vehicle_id", "lat", "lon"])
    return dict(zip(sub["vehicle_id"], zip(sub["lat"], sub["lon"])))


def reconstruct():
    ops = [p.name for p in SNAP.iterdir() if p.is_dir()] if SNAP.exists() else []
    ends, n_snaps = [], 0
    for op in ops:
        files = sorted((SNAP / op).rglob("*.parquet"))
        n_snaps += len(files)
        prev = None
        for f in files:
            try:
                df = pd.read_parquet(f)
            except Exception:
                continue
            if df.empty:
                continue
            ts = pd.to_datetime(df["ts"].iloc[0], utc=True)
            cur = available_set(df)
            if prev is not None:
                for vid in cur.keys() - prev.keys():          # became available = trip END
                    la, lo = cur[vid]
                    ends.append((ts, la, lo, op))
            prev = cur
    return ends, n_snaps, ops


def main():
    OUT.mkdir(exist_ok=True)
    ends, n_snaps, ops = reconstruct()
    if not ends:
        (OUT / "summary.txt").write_text(
            f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC — "
            f"snapshots read: {n_snaps}; not enough yet to reconstruct trips (need >= 2).\n"
        )
        print("nothing to process yet")
        return

    e = pd.DataFrame(ends, columns=["ts", "lat", "lon", "operator"])
    e["h3"] = [cell(la, lo) for la, lo in zip(e["lat"], e["lon"])]
    e["hour"] = e["ts"].dt.hour
    e["weekday"] = e["ts"].dt.dayofweek

    tot = e.groupby("h3").size().reset_index(name="end_count")
    cents = {c: h3.cell_to_latlng(c) for c in tot["h3"]}
    tot["cell_lat"] = tot["h3"].map(lambda c: cents[c][0])
    tot["cell_lon"] = tot["h3"].map(lambda c: cents[c][1])
    tot.to_parquet(OUT / f"roma_demand_res{RES}.parquet", index=False)

    hourly = e.groupby(["h3", "hour", "weekday"]).size().reset_index(name="end_count")
    hourly.to_parquet(OUT / f"roma_demand_hourly_res{RES}.parquet", index=False)

    summary = (
        f"Rome GBFS demand — processed {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC\n"
        f"operators      : {', '.join(ops)}\n"
        f"snapshots read : {n_snaps}\n"
        f"time span      : {e['ts'].min()}  ->  {e['ts'].max()}\n"
        f"trip-ends      : {len(e):,}\n"
        f"H3 cells (res {RES}): {tot['h3'].nunique():,}\n"
    )
    (OUT / "summary.txt").write_text(summary)
    print(summary)


if __name__ == "__main__":
    main()
