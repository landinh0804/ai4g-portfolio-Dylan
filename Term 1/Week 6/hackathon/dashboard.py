"""Bahn-Puls dashboard (read-only): streamlit run dashboard.py

Downloads the live database (config: live_db_url) when the local copy is
missing or older than 10 minutes, so a hosted copy stays current; falls back
to the local/committed data/pulse.db if the download fails.
No free-text input: charts and tables only.
"""
from __future__ import annotations

import json
import math
import sqlite3
import time
import urllib.request
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml
from plotly.subplots import make_subplots

TZ, MIN_N, SERIES, NEUTRAL = "Europe/Berlin", 10, "#2a78d6", "#8a8984"  # grey = "don't over-read this"
MODELS = {"m2": "Model 2 · twitter-xlm-roberta", "m1": "Model 1 · german-sentiment-bert"}

# Not imported from pulse.collect: that would pull atproto/torch into the
# hosted dashboard, which only needs to read the database.
HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "data" / "pulse.db"
st.set_page_config(page_title="Bahn-Puls", page_icon="🚆", layout="wide")
cfg = yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))
TOPICS = {"all": "All topics"} | {k: v["label"] for k, v in cfg["topics"].items()}

st.title("Bahn-Puls · rail passenger sentiment on Bluesky")
st.warning(f"**Not a representative survey.** Bluesky users skew young, urban and very online, and people "
           f"post more when things go wrong. Compare each topic with its own baseline, not absolute levels. "
           f"Points from fewer than {MIN_N} posts are greyed out and unreliable.", icon="⚠️")


@st.cache_data(ttl=600)
def load(_stamp: int) -> pd.DataFrame:
    if not DB_PATH.exists() or time.time() - DB_PATH.stat().st_mtime > 600:
        try:
            DB_PATH.parent.mkdir(exist_ok=True)
            tmp = DB_PATH.with_suffix(".download")
            urllib.request.urlretrieve(cfg["live_db_url"], tmp)
            tmp.replace(DB_PATH)
        except Exception:  # noqa: BLE001 - fall back to the copy we have
            if not DB_PATH.exists():
                raise
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql("SELECT * FROM items", conn)
    df["created_at"] = pd.to_datetime(df.created_at, utc=True).dt.tz_convert(TZ)
    df["topics"] = df.topics.map(json.loads)
    return df


def shares(df: pd.DataFrame, model: str, freq: str) -> pd.DataFrame:
    """Negative share per topic and period, plus a baseline: the pooled share
    over the previous 7 days, EXCLUDING the period itself (a spike must not
    hide itself in its own baseline). Pooled = sum(neg)/sum(n), so a 2-post day
    doesn't weigh like a 200-post day. Baselines on < MIN_N posts are blank."""
    d = df[df[f"{model}_label"].notna()].assign(period=lambda x: x.created_at.dt.floor(freq),
                                                neg=lambda x: x[f"{model}_label"] == "negative")
    rows = pd.concat([d.assign(topic="all"), d.explode("topics").rename(columns={"topics": "topic"})])
    rows = rows[rows.topic.isin(TOPICS)]  # ignore tags from an older config until the collector re-tags
    periods = pd.date_range(d.period.min(), d.period.max(), freq=freq)
    window = 7 if freq == "D" else 168
    out = []
    for topic, g in rows.groupby("topic"):
        a = g.groupby("period").agg(n=("id", "size"), neg=("neg", "sum")).reindex(periods, fill_value=0)
        prev_n, prev_neg = (a[c].shift(1).rolling(window, min_periods=1).sum() for c in ("n", "neg"))
        a["share"] = a.neg / a.n.where(a.n > 0)
        a["baseline"] = prev_neg / prev_n.where(prev_n >= MIN_N)
        out.append(a.assign(topic=topic).rename_axis("period").reset_index())
    return pd.concat(out)


items = load(int(time.time() // 600))
c1, c2, c3 = st.columns([1, 1.3, 2])
freq = {"Daily": "D", "Hourly": "h"}[c1.radio("Time step", ["Daily", "Hourly"], horizontal=True)]
kind = c2.radio("Posts", ["Personal", "News", "Both"], horizontal=True,
                help="News posts report events and read as negative even when neutral in tone, so they are off by default.")
model = c3.radio("Sentiment model", list(MODELS), format_func=MODELS.get, horizontal=True)
sel = items if kind == "Both" else items[items.kind == kind.lower()]
if freq == "h":
    sel = sel[sel.created_at >= sel.created_at.max() - pd.Timedelta(hours=48)]  # keep hourly readable
s = shares(sel, model, freq)
fmt = "%a %d %b" if freq == "D" else "%a %d %b %H:00"

# The morning question: which topic is above its own baseline right now?
latest = s[(s.period == s.period.max()) & (s.topic != "all")].copy()
latest["change"] = (latest.share - latest.baseline) * 100
latest["status"] = latest.apply(lambda r: "◌ too few posts" if r.n < MIN_N else "◌ no baseline yet" if pd.isna(r.baseline)
                                else "▲ above baseline" if r.change >= 10 else "▼ below baseline" if r.change <= -10
                                else "● around baseline", axis=1)
st.subheader(f"Topics against their baseline · {s.period.max():{fmt}}")
st.dataframe(latest.sort_values("change", ascending=False).assign(topic=lambda x: x.topic.map(TOPICS))
             [["topic", "status", "share", "baseline", "change", "n"]]
             .rename(columns={"topic": "Topic", "status": "Status", "share": "Negative share", "baseline": "Baseline",
                              "change": "Change (points)", "n": "Posts"}),
             hide_index=True, width="stretch",
             column_config={"Negative share": st.column_config.NumberColumn(format="percent"),
                            "Baseline": st.column_config.NumberColumn(format="percent"),
                            "Change (points)": st.column_config.NumberColumn(format="%+.0f")})

# Small multiples: one panel per topic on a shared 0-100 % axis.
topics = ["all"] + [t for t in cfg["topics"] if t in set(s.topic)]
rows = math.ceil(len(topics) / 3)
fig = make_subplots(rows=rows, cols=3, subplot_titles=[TOPICS[t] for t in topics], shared_xaxes=True, vertical_spacing=0.12)
labels = freq == "D"  # 48 hourly labels per panel are unreadable; counts are in the hover there
for i, t in enumerate(topics):
    d, pos = s[s.topic == t], dict(row=i // 3 + 1, col=i % 3 + 1)
    hover = "%{x|" + fmt + "}<br>Negative: %{y:.0%} of %{customdata} posts<extra></extra>"
    fig.add_trace(go.Scatter(x=d.period, y=d.share, mode="lines", line=dict(color=SERIES, width=2), hoverinfo="skip", showlegend=False), **pos)
    for p, name, marker in [(d[d.n >= MIN_N], "Negative share", dict(color=SERIES, size=8)),
                            (d[(d.n > 0) & (d.n < MIN_N)], f"Fewer than {MIN_N} posts",
                             dict(color="rgba(0,0,0,0)", size=8, line=dict(color=NEUTRAL, width=2)))]:
        fig.add_trace(go.Scatter(x=p.period, y=p.share, mode="markers+text" if labels else "markers", marker=marker,
                                 text=[f"n={n}" for n in p.n], textposition="top center", textfont=dict(size=10, color=NEUTRAL),
                                 customdata=p.n, hovertemplate=hover, name=name, legendgroup=name, showlegend=i == 0), **pos)
    fig.add_trace(go.Scatter(x=d.period, y=d.baseline, mode="lines", line=dict(color=NEUTRAL, width=2, dash="dash"),
                             hoverinfo="skip", name="Baseline (previous 7 days)", legendgroup="b", showlegend=i == 0), **pos)
fig.update_yaxes(range=[0, 1.12], tickformat=".0%", tickvals=[0, .25, .5, .75, 1], gridcolor="rgba(128,128,128,.15)")
fig.update_xaxes(showgrid=False)
fig.update_layout(height=260 * rows + 60, margin=dict(l=10, r=10, t=60, b=10), legend=dict(orientation="h", y=1.04, yanchor="bottom"))
st.subheader("Negative share per topic")
st.plotly_chart(fig, width="stretch")

# Drill-down: the posts behind a point.
st.subheader("Posts behind a point")
d1, d2 = st.columns(2)
day = d1.selectbox("Day", sorted(sel.created_at.dt.floor("D").unique(), reverse=True), format_func=lambda d: f"{d:%a %d %b}")
topic = d2.selectbox("Topic", list(TOPICS), format_func=TOPICS.get)
posts = sel[(sel.created_at.dt.floor("D") == day) & (sel.topics.map(lambda ts: topic == "all" or topic in ts))].sort_values("created_at")
st.caption(f"{len(posts)} posts · {(posts[f'{model}_label'] == 'negative').sum()} negative · times in Berlin time")
st.dataframe(pd.DataFrame({"Time": posts.created_at.dt.strftime("%H:%M"), "Text (original German)": posts.text,
                           "Label": posts[f"{model}_label"], "Confidence": posts[f"{model}_score"]}),
             hide_index=True, width="stretch",
             column_config={"Confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
st.caption("No translation: the open local de→en model needs the `sentencepiece` package, outside our agreed dependencies. "
           "Do not use this to judge individual staff, to rank lines on a handful of posts, or to claim a problem is "
           "solved because posting stopped.")
