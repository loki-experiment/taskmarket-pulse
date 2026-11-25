#!/usr/bin/env python3
"""Fetch public Taskmarket market data and write site/data.json.

Read-only. Stdlib only. No key, no wallet, no browser.

Every number in the dashboard is fetched here from the public API and cached
once per build, which is the pattern the bounty brief requires (the API sends
no CORS headers, so a browser cannot call it directly).

Usage:  python3 fetch.py [--out site/data.json] [--tasks-per-chain 500]
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.taskmarket.dev"
CHAINS = {"4217": "Tempo", "8453": "Base"}
RANGES = ("7d", "30d", "90d", "all")
UA = "taskmarket-pulse/1.0 (+https://github.com/loki-experiment/taskmarket-pulse)"


def get(path, params=None, tries=3, timeout=30):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # transient 429/5xx/timeout
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("GET %s failed: %s" % (url, last))


def iso_week(ts):
    try:
        d = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None
    y, w, _ = d.isocalendar()
    return "%04d-W%02d" % (y, w)


def poster_stats(chain_id, budget):
    """Distinct task posters per ISO week, from the public task list."""
    seen, posters, sampled, cursor = set(), {}, 0, None
    while sampled < budget:
        params = {"chainId": chain_id, "limit": 100, "sort": "newest"}
        if cursor:
            params["cursor"] = cursor
        page = get("/api/tasks", params)
        rows = page.get("tasks") or []
        if not rows:
            break
        for t in rows:
            tid = t.get("id")
            if not tid or tid in seen:
                continue
            seen.add(tid)
            sampled += 1
            wk = iso_week(t.get("createdAt"))
            if not wk:
                continue
            posters.setdefault(wk, set()).add((t.get("requester") or "").lower())
        cursor = page.get("nextCursor")
        if not page.get("hasMore") or not cursor:
            break
    weeks = sorted(posters)[-10:]
    return {
        "sampledTasks": sampled,
        "weeks": [{"week": w, "posters": len(posters[w])} for w in weeks],
    }


def open_tasks(chain_id, max_pages=4):
    """Open tasks counted from the list endpoint (stats.breakdowns is all-time records)."""
    rows, cursor, pages = [], None, 0
    while pages < max_pages:
        params = {"chainId": chain_id, "status": "open", "limit": 100, "sort": "newest"}
        if cursor:
            params["cursor"] = cursor
        page = get("/api/tasks", params)
        rows.extend(page.get("tasks") or [])
        pages += 1
        cursor = page.get("nextCursor")
        if not page.get("hasMore") or not cursor:
            break
    by_mode, reward = {}, 0
    for t in rows:
        m = t.get("mode") or "other"
        by_mode[m] = by_mode.get(m, 0) + 1
        try:
            reward += int(t.get("reward") or 0)
        except (TypeError, ValueError):
            pass
    return {"count": len(rows), "rewardRaw": str(reward), "byMode": by_mode, "truncated": bool(cursor)}


def chain_block(chain_id):
    out = {"name": CHAINS[chain_id], "chainId": int(chain_id)}
    out["stats"] = get("/api/market/stats", {"chainId": chain_id})
    out["breakdowns"] = get("/api/stats/breakdowns", {"chainId": chain_id})
    out["open"] = open_tasks(chain_id)

    series = {}
    for rng in RANGES:
        bucket = "week" if rng == "all" else "day"
        series[rng] = get(
            "/api/stats/platform-time-series",
            {"chainId": chain_id, "range": rng, "bucket": bucket},
        )
    out["series"] = series

    out["heat"] = {
        "hourOfWeek": get(
            "/api/stats/activity-heatmap",
            {"chainId": chain_id, "range": "30d", "dimension": "hourOfWeek"},
        ),
        "mode": get(
            "/api/stats/activity-heatmap",
            {"chainId": chain_id, "range": "7d", "dimension": "mode"},
        ),
    }
    feed = get("/api/stats/activity-feed", {"chainId": chain_id, "limit": 50})
    out["feed"] = feed.get("items") or []
    out["posters"] = poster_stats(chain_id, 1500)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "site", "data.json"))
    args = ap.parse_args()

    started = dt.datetime.now(dt.timezone.utc)
    data = {
        "generated_at": started.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": API,
        "chains": {cid: chain_block(cid) for cid in CHAINS},
        "methods": [
            "GET /api/market/stats?chainId=…",
            "GET /api/stats/breakdowns?chainId=…",
            "GET /api/stats/platform-time-series?chainId=…&range=7d|30d|90d|all&bucket=day|week",
            "GET /api/stats/activity-heatmap?chainId=…&range=30d&dimension=hourOfWeek",
            "GET /api/stats/activity-heatmap?chainId=…&range=7d&dimension=mode",
            "GET /api/stats/activity-feed?chainId=…&limit=60",
            "GET /api/tasks?chainId=…&limit=100&sort=newest (paged, ≤500 per chain, for distinct posters per week)",
        ],
        "refresh_minutes": 60,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    took = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
    size = os.path.getsize(args.out)
    print("wrote %s (%.1f KB) in %.1fs at %s" % (args.out, size / 1024.0, took, data["generated_at"]))
    for cid in data["chains"]:
        b = data["chains"][cid]
        print("  chain %s: feed=%d series=%s posters_weeks=%d" % (
            cid, len(b["feed"]), "/".join(str(len(b["series"][r])) for r in RANGES), len(b["posters"]["weeks"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
