"""One collection cycle: fetch -> filter -> store -> classify, then exit.

    python -m pulse.collect

Safe to rerun at any time: items are keyed by sha256(post URI) and inserted
with INSERT OR IGNORE. Posts are stored before they are classified, so a model
failure never loses data; unlabelled rows are picked up by the next run.
Every run is logged in `runs`, which is what proves continuous operation.

Privacy (brief: "store only text, time and derived fields; no handles, DIDs"):
author data (handle, display name, labels) is only looked at in memory to spot
bots, and no post URL is stored, because Bluesky URLs contain the author's DID.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml
from atproto import Client
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "data" / "pulse.db"
log = logging.getLogger("pulse")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,          -- sha256 of the at:// URI (not reversible to the author)
    created_at TEXT NOT NULL,     -- UTC, when posted
    fetched_at TEXT NOT NULL,     -- UTC, when collected
    text TEXT NOT NULL,
    lang TEXT,                    -- Bluesky `langs`, comma-separated
    query TEXT NOT NULL,
    kind TEXT NOT NULL,           -- news | personal
    topics TEXT NOT NULL,         -- JSON list
    m1_label TEXT, m1_score REAL, -- NULL = not classified yet
    m2_label TEXT, m2_score REAL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start TEXT NOT NULL, end TEXT,
    items_fetched INTEGER DEFAULT 0, items_new INTEGER DEFAULT 0,
    errors TEXT DEFAULT '[]', ok INTEGER DEFAULT 0
);
-- Newest indexedAt seen per query. Search results are ordered by indexedAt,
-- so paging stops once we reach it (createdAt is client-set and unreliable).
CREATE TABLE IF NOT EXISTS query_state (query TEXT PRIMARY KEY, newest_indexed TEXT NOT NULL);
"""

URL_RE = re.compile(r"https?://\S+|\b[\w-]+(\.[\w-]+)+/\S*")
WORD_RE = re.compile(r"[^\W\d_]{2,}")  # 2+ letters, so emoji/numbers/links don't count


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_config() -> dict:
    return yaml.safe_load((PROJECT_DIR / "config.yaml").read_text(encoding="utf-8"))


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.executescript(SCHEMA)
    # Migration: databases from before 13 Oct stored post URLs (with the
    # author's DID). Drop the column, then VACUUM so the old values are really
    # gone from the file and not just marked as free pages.
    if "url" in {r[1] for r in conn.execute("PRAGMA table_info(items)")}:
        conn.execute("ALTER TABLE items DROP COLUMN url")
        conn.commit()
        conn.execute("VACUUM")
    return conn


# ------------------------------------------------------------------ fetching
def make_client() -> Client:
    # Search works anonymously via api.bsky.app (public.api.bsky.app returns
    # 403), but datacenter IPs are the first to get blocked, so log in with an
    # app password when one is configured.
    handle, password = os.getenv("BSKY_HANDLE"), os.getenv("BSKY_APP_PASSWORD")
    if handle and password:
        try:
            client = Client()
            client.login(handle, password, fetch_bsky_profile=False)
            return client
        except Exception as e:  # noqa: BLE001 - fall back rather than fail the run
            log.warning("login failed (%s), using anonymous search", type(e).__name__)
    return Client(base_url="https://api.bsky.app/xrpc")


def search_new(client: Client, query: str, watermark: str | None, cfg: dict) -> tuple[list[dict], str | None]:
    """Page through sort=latest results until we reach the watermark (or the
    backfill limit on a query's first run). Returns (posts, newest indexedAt)."""
    cutoff = parse_ts(watermark) if watermark else datetime.now(timezone.utc) - timedelta(hours=cfg["backfill_hours"])
    posts, newest, cursor = [], watermark, None
    for _ in range(cfg["max_pages_per_query"]):
        params = {"q": query, "sort": "latest", "limit": 100} | ({"cursor": cursor} if cursor else {})
        data = client.app.bsky.feed.search_posts(params=params).model_dump(mode="json", by_alias=True, exclude_none=True)
        reached_old = False
        for p in data.get("posts", []):
            if newest is None or parse_ts(p["indexedAt"]) > parse_ts(newest):
                newest = p["indexedAt"]
            if parse_ts(p["indexedAt"]) <= cutoff:
                reached_old = True  # keep scanning this page: order isn't strictly guaranteed
            else:
                posts.append(p)
        cursor = data.get("cursor")
        if reached_old or not cursor:
            break
        time.sleep(0.3)  # be polite to the API
    return posts, newest


# ----------------------------------------------------------------- filtering
class Filters:
    def __init__(self, cfg: dict):
        f = cfg["filters"]
        self.f = f
        self.bot_name = re.compile("|".join(f["bot_name_patterns"]), re.I)
        self.rail = re.compile("|".join(cfg["rail_context"]), re.I)
        self.news = cfg["news_domains"]
        self.topics = {k: re.compile("|".join(r"\b" + w for w in t["keywords"]), re.I)
                       for k, t in cfg["topics"].items() if t["keywords"]}

    @staticmethod
    def template(text: str) -> str:
        """Text with links, hashtags and numbers removed: identical templates
        with changing times or train numbers are status bots."""
        t = re.sub(r"#\w+|[\d:.,+\-]+", "", URL_RE.sub("", text.lower()))
        t = " ".join(t.split())
        return t if len(t) >= 15 else ""

    def bot_authors(self, posts: list[dict], recent_templates: Counter) -> set[str]:
        """Author DIDs that look automated. Lives only for this run."""
        bots, by_author, templates, tpl_authors = set(), defaultdict(list), Counter(recent_templates), defaultdict(set)
        for p in posts:
            a = p["author"]
            by_author[a["did"]].append(parse_ts(p["indexedAt"]))
            if any("bot" in lab.get("val", "").lower() for lab in a.get("labels") or []) \
                    or self.bot_name.search(f'{a.get("handle", "")} {a.get("displayName") or ""}'):
                bots.add(a["did"])
            if tpl := self.template(p["record"].get("text", "")):
                templates[tpl] += 1
                tpl_authors[tpl].add(a["did"])
        for tpl, n in templates.items():
            if n >= self.f["template_repeat_threshold"]:
                bots |= tpl_authors[tpl]
        for did, times in by_author.items():
            hours = max((max(times) - min(times)).total_seconds() / 3600, 1.0)
            if len(times) / hours > self.f["max_posts_per_author_per_hour"]:
                bots.add(did)
        return bots

    def drop_reason(self, p: dict, needs_context: bool) -> str | None:
        text = (p["record"].get("text") or "").strip()
        if not text:
            return "empty"
        # searchPosts never returns reposts (separate records), but crossposted RTs exist.
        if text.startswith("RT @"):
            return "repost"
        if len(WORD_RE.findall(URL_RE.sub(" ", re.sub(r"@[\w.\-]+", " ", text)))) < self.f["min_words"]:
            return "too_short"
        if needs_context and not self.rail.search(text):
            return "no_rail_context"
        if (parse_ts(p["indexedAt"]) - parse_ts(p["record"].get("createdAt", p["indexedAt"]))).days > self.f["max_backdate_days"]:
            return "backdated"
        return None

    def topics_for(self, text: str) -> str:
        return json.dumps([k for k, rx in self.topics.items() if rx.search(text)] or ["other"])

    def to_item(self, p: dict, query: str, fetched_at: str) -> dict:
        rec, text = p["record"], p["record"]["text"].strip()
        links = [feat["uri"] for fc in rec.get("facets") or [] for feat in fc.get("features") or [] if feat.get("uri")]
        embed = rec.get("embed") or {}
        links += [e["external"]["uri"] for e in (embed, embed.get("media") or {}) if e.get("external", {}).get("uri")]
        hosts = {(urlparse(u).hostname or "").lower().removeprefix("www.") for u in links}
        is_news = any(h == d or h.endswith("." + d) for h in hosts for d in self.news)
        return {
            "id": hashlib.sha256(p["uri"].encode()).hexdigest(),
            "created_at": parse_ts(rec.get("createdAt") or p["indexedAt"]).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fetched_at": fetched_at,
            "text": text,
            "lang": ",".join(rec.get("langs") or []) or None,
            "query": query,
            "kind": "news" if is_news else "personal",
            "topics": self.topics_for(text),
        }


def retag(conn: sqlite3.Connection, cfg: dict) -> None:
    """Recompute every item's topics from the current config.yaml, so stored
    tags never lag behind edited keyword lists or merged topics. A regex pass
    over a few thousand short texts takes well under a second."""
    filters = Filters(cfg)
    changed = [(t, i) for i, text, old in conn.execute("SELECT id, text, topics FROM items")
               if (t := filters.topics_for(text)) != old]
    if changed:
        with conn:
            conn.executemany("UPDATE items SET topics = ? WHERE id = ?", changed)
        log.info("retagged %d items", len(changed))


def fetch_and_store(conn: sqlite3.Connection, cfg: dict, errors: list[str]) -> tuple[int, int, bool]:
    client, filters, fetched_at = make_client(), Filters(cfg), utcnow()
    watermarks = dict(conn.execute("SELECT query, newest_indexed FROM query_state"))
    found: dict[str, tuple[dict, str, bool]] = {}  # uri -> (post, query, needs_context)
    new_marks, fetched, ok_queries = {}, 0, 0
    for q, needs_ctx in [(q, False) for q in cfg["queries"]] + [(q, True) for q in cfg["context_queries"]]:
        try:
            posts, newest = search_new(client, q, watermarks.get(q), cfg["fetch"])
        except Exception as e:  # noqa: BLE001 - one bad query must not stop the rest
            errors.append(f"query {q!r}: {type(e).__name__}: {str(e)[:150]}")
            continue
        ok_queries += 1
        fetched += len(posts)
        if newest:
            new_marks[q] = newest
        for p in posts:
            # Unambiguous queries come first, so a post they found keeps needs_context=False.
            found.setdefault(p["uri"], (p, q, needs_ctx))
    if not ok_queries:
        return fetched, 0, False

    recent = Counter(Filters.template(t) for (t,) in conn.execute(
        "SELECT text FROM items WHERE fetched_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-3 days')"))
    recent.pop("", None)
    bots = filters.bot_authors([p for p, _, _ in found.values()], recent)
    items, dropped = [], Counter()
    for p, q, needs_ctx in found.values():
        if p["author"]["did"] in bots:
            reason = "bot"
        elif Filters.template(p["record"].get("text", "")) in recent:
            reason = "duplicate"
        else:
            reason = filters.drop_reason(p, needs_ctx)
        if reason:
            dropped[reason] += 1
        else:
            items.append(filters.to_item(p, q, fetched_at))
    del found, bots  # author data ends here

    with conn:  # items and watermarks are saved together or not at all
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO items (id, created_at, fetched_at, text, lang, query, kind, topics) "
            "VALUES (:id, :created_at, :fetched_at, :text, :lang, :query, :kind, :topics)", items)
        new = conn.total_changes - before
        conn.executemany(
            "INSERT INTO query_state VALUES (?, ?) ON CONFLICT(query) DO UPDATE SET newest_indexed = excluded.newest_indexed",
            new_marks.items())
    log.info("fetched=%d new=%d dropped=%s", fetched, new, dict(dropped))
    return fetched, new, True


# ----------------------------------------------------------------- sentiment
def preprocess_germansentiment(text: str) -> str:
    """Re-implementation of germansentiment's clean_text (MIT): the model card
    says inputs must be cleaned exactly like the training data."""
    text = re.sub(r"@\S+", "", re.sub(r"https*\S+", "", text.replace("\n", " ")))
    for d, w in zip("0123456789", ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun"]):
        text = text.replace(d, " " + w)
    return " ".join(re.sub(r"[^A-Za-züöäÖÜÄß ]", "", text).split()).lower()


def preprocess_cardiff(text: str) -> str:
    """From the cardiffnlp model card: mentions -> @user, links -> http."""
    return " ".join("@user" if t.startswith("@") and len(t) > 1 else "http" if t.startswith("http") else t
                    for t in text.split(" "))


def classify(texts: list[str], spec: dict, batch_size: int = 16) -> list[tuple[str, float]]:
    """Run one pinned Hugging Face model locally on CPU; labels normalised to
    negative / neutral / positive with the softmax probability as score."""
    import torch  # imported lazily so fetching works even if torch is broken
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(spec["tokenizer"], revision=spec["tokenizer_revision"])
    model = AutoModelForSequenceClassification.from_pretrained(
        spec["name"], revision=spec["revision"], use_safetensors=spec["use_safetensors"]).eval()
    canon = {i: next(c for c in ("negative", "neutral", "positive") if l.lower().startswith(c[:3]))
             for i, l in model.config.id2label.items()}
    prep = {"germansentiment": preprocess_germansentiment, "cardiff": preprocess_cardiff}[spec["preprocess"]]
    out = []
    for i in range(0, len(texts), batch_size):
        enc = tok([prep(t) for t in texts[i:i + batch_size]], padding=True, truncation=True,
                  max_length=512, return_tensors="pt")
        with torch.inference_mode():
            score, idx = torch.softmax(model(**enc).logits, dim=-1).max(dim=-1)
        out += [(canon[j], round(s, 4)) for j, s in zip(idx.tolist(), score.tolist())]
    return out


def classify_pending(conn: sqlite3.Connection, cfg: dict, errors: list[str]) -> None:
    for key in ("m1", "m2"):
        rows = conn.execute(f"SELECT id, text FROM items WHERE {key}_label IS NULL LIMIT 600").fetchall()
        if not rows:
            continue
        try:
            preds = classify([t for _, t in rows], cfg["models"][key])
        except Exception as e:  # noqa: BLE001 - items stay, next run retries
            errors.append(f"{key}: {type(e).__name__}: {str(e)[:150]}")
            continue
        with conn:
            conn.executemany(f"UPDATE items SET {key}_label = ?, {key}_score = ? WHERE id = ?",
                             [(lab, s, i) for (lab, s), (i, _) in zip(preds, rows)])


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("httpx", "httpx2", "httpcore", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    load_dotenv(PROJECT_DIR / ".env")
    cfg, conn = load_config(), connect()
    # Logged before any work, finished in `finally`: even a crash leaves a trace.
    run_id = conn.execute("INSERT INTO runs(start) VALUES (?)", (utcnow(),)).lastrowid
    conn.commit()
    errors, fetched, new, ok = [], 0, 0, False
    try:
        fetched, new, ok = fetch_and_store(conn, cfg, errors)
        retag(conn, cfg)
        if not ok:
            errors.append("all queries failed")
        classify_pending(conn, cfg, errors)
    except Exception as e:  # noqa: BLE001
        errors.append(f"crash: {type(e).__name__}: {str(e)[:200]}")
        log.exception("run crashed")
        ok = False
    finally:
        conn.execute("UPDATE runs SET end=?, items_fetched=?, items_new=?, errors=?, ok=? WHERE id=?",
                     (utcnow(), fetched, new, json.dumps(errors, ensure_ascii=False), int(ok), run_id))
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        conn.close()
    log.info("run %d ok=%s new=%d total=%d errors=%s", run_id, ok, new, total, errors)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
