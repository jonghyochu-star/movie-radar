"""Audience-response signals for Movie Radar 1.9.

This module deliberately avoids lifetime-average views (views / age).
Shorts often grow hard for a limited feed window and then plateau, so we keep:
- age-adjusted current-view floors for newly discovered videos,
- cumulative proof for older winners,
- actual deltas from repeated observations when available.
"""
from __future__ import annotations
from datetime import datetime, timezone

FLOORS = (
    (12, 200_000),
    (24, 500_000),
    (48, 1_000_000),
    (72, 2_000_000),
    (120, 3_000_000),
    (168, 5_000_000),
)
CUMULATIVE_PROVEN = 5_000_000
MEGA_PROVEN = 10_000_000
DELTA_WINDOWS = {
    "h12": {"target": 12, "minimum": 6, "maximum": 18, "threshold": 200_000},
    "h24": {"target": 24, "minimum": 18, "maximum": 36, "threshold": 500_000},
    "d7": {"target": 168, "minimum": 120, "maximum": 216, "threshold": 2_000_000},
}
TRACK_LIMIT = 150
TRACK_DAYS = 100
MAX_SNAPSHOTS = 10

def _dt(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None

def iso(value):
    value=_dt(value)
    return value.isoformat(timespec="seconds").replace("+00:00","Z") if value else None

def age_hours(published_at, now):
    p=_dt(published_at);n=_dt(now)
    if not p or not n:return None
    return max(0.0,(n-p).total_seconds()/3600)

def floor_views(age):
    if age is None:return CUMULATIVE_PROVEN
    for max_hours,views in FLOORS:
        if age<=max_hours:return views
    return CUMULATIVE_PROVEN

def normalize_snapshots(rows):
    out=[]
    for row in rows or []:
        if not isinstance(row,dict):continue
        at=iso(row.get("at"));views=row.get("views")
        if not at or isinstance(views,bool) or not isinstance(views,int) or views<0:continue
        item={"at":at,"views":views}
        if item not in out:out.append(item)
    out.sort(key=lambda x:x["at"])
    return out[-MAX_SNAPSHOTS:]

def _delta_for(snapshots, now, current_views, spec):
    n=_dt(now)
    if not n or not isinstance(current_views,int):return None
    candidates=[]
    for row in normalize_snapshots(snapshots):
        at=_dt(row["at"])
        elapsed=(n-at).total_seconds()/3600 if at else -1
        if spec["minimum"]<=elapsed<=spec["maximum"]:
            candidates.append((abs(elapsed-spec["target"]),elapsed,row))
    if not candidates:return None
    _,elapsed,row=min(candidates,key=lambda x:x[0])
    delta=max(0,current_views-row["views"])
    return {
        "views":delta,
        "hours":round(elapsed,1),
        "perHour":round(delta/elapsed,1) if elapsed>0 else None,
        "fromViews":row["views"],
        "threshold":spec["threshold"],
        "strong":delta>=spec["threshold"],
    }

def audience_metrics(published_at, current_views, snapshots, now):
    age=age_hours(published_at,now)
    views=current_views if isinstance(current_views,int) and current_views>=0 else 0
    floor=floor_views(age)
    deltas={k:_delta_for(snapshots,now,views,spec) for k,spec in DELTA_WINDOWS.items()}
    measured=[x for x in deltas.values() if x]
    surging=any(x.get("strong") for x in measured)
    fast_strong=views>=floor
    proven=views>=CUMULATIVE_PROVEN
    mega=views>=MEGA_PROVEN
    validated=surging or fast_strong or proven
    if surging:status="surging"
    elif mega:status="mega"
    elif proven:status="proven"
    elif fast_strong:status="strong"
    else:status="watch"
    evidence=[]
    if surging:evidence.append("actual_delta")
    if fast_strong:evidence.append("age_floor")
    if proven:evidence.append("cumulative_5m")
    if mega:evidence.append("cumulative_10m")
    return {
        "status":status,
        "validated":validated,
        "surging":surging,
        "fastStrong":fast_strong,
        "cumulativeProven":proven,
        "mega":mega,
        "ageHours":round(age,1) if age is not None else None,
        "floorViews":floor,
        "currentViews":views,
        "deltas":deltas,
        "evidence":evidence,
        "method":"age-floor+cumulative+observed-delta-v1",
        "lifetimeAverageUsed":False,
    }

def audience_rank(video):
    a=(video or {}).get("audience") or {}
    status=a.get("status")
    return {"surging":0,"mega":1,"proven":2,"strong":3,"watch":4}.get(status,5)

def normalize_tracking(raw):
    out={}
    if not isinstance(raw,dict):return out
    for vid,row in raw.items():
        if not isinstance(vid,str) or not isinstance(row,dict):continue
        item={
            "publishedAt":iso(row.get("publishedAt")),
            "snapshots":normalize_snapshots(row.get("snapshots")),
            "screenGate":[x for x in row.get("screenGate",[]) if x in {"movie","tv","metadata","direct"}],
            "discoveryRoutes":[x for x in row.get("discoveryRoutes",[]) if isinstance(x,str)][:6],
            "discoveryLabels":[str(x)[:80] for x in row.get("discoveryLabels",[]) if isinstance(x,str)][:6],
            "sourceKinds":[x for x in row.get("sourceKinds",[]) if isinstance(x,str)][:6],
            "promotedAt":iso(row.get("promotedAt")),
            "lastSeenAt":iso(row.get("lastSeenAt")),
        }
        if item["publishedAt"] or item["snapshots"]:out[vid]=item
    return out

def add_observation(tracking, vid, published_at, views, now, meta=None):
    if not isinstance(vid,str) or not isinstance(views,int) or views<0:return
    row=tracking.setdefault(vid,{"publishedAt":iso(published_at),"snapshots":[]})
    row["publishedAt"]=row.get("publishedAt") or iso(published_at)
    snaps=normalize_snapshots(row.get("snapshots"))
    at=iso(now)
    if at:
        if snaps and snaps[-1]["at"]==at:snaps[-1]["views"]=views
        else:snaps.append({"at":at,"views":views})
    row["snapshots"]=normalize_snapshots(snaps)
    row["lastSeenAt"]=at
    if isinstance(meta,dict):
        for key in ["screenGate","discoveryRoutes","discoveryLabels","sourceKinds"]:
            if isinstance(meta.get(key),list):row[key]=meta[key][:6]

def prune_tracking(tracking, now, limit=TRACK_LIMIT, track_days=TRACK_DAYS):
    n=_dt(now)
    rows=[]
    for vid,row in normalize_tracking(tracking).items():
        p=_dt(row.get("publishedAt"))
        if p and n and (n-p).total_seconds()>track_days*86400 and row.get("promotedAt"):
            continue
        last=_dt(row.get("lastSeenAt")) or p
        rows.append((last or datetime.min.replace(tzinfo=timezone.utc),vid,row))
    rows.sort(key=lambda x:x[0],reverse=True)
    return {vid:row for _,vid,row in rows[:max(1,int(limit))]}
