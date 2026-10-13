"""Compare both models (and a word-list baseline) against hand labels.

    python -m pulse.evaluate sample   # 50 stratified posts -> eval/to_label.csv
    python -m pulse.evaluate          # eval/to_label.csv -> eval/results.md, eval/test_table.csv

Labelling: fill `human_label` (negative / neutral / positive) and optionally
`off_topic` (yes) in any spreadsheet. The CSV has no model outputs, so they
can't anchor the labeller. Evaluation runs both models on the labelled texts
itself, so it doesn't depend on which database the sample came from.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
import urllib.request
import zipfile

import pandas as pd

from .collect import DB_PATH, PROJECT_DIR, classify, load_config

EVAL_DIR = PROJECT_DIR / "eval"
LABELS = ["negative", "neutral", "positive"]
SYSTEMS = {"m1": "Model 1 (german-sentiment-bert)", "m2": "Model 2 (twitter-xlm-roberta)",
           "b0": "Baseline (SentiWS word list)"}


def sample(n: int = 50, seed: int = 42) -> None:
    """Round-robin over (topic, kind) strata, so rare strata like strike/news
    are represented instead of the sample being all personal/other."""
    df = pd.read_sql("SELECT id, created_at, kind, topics, lang, text FROM items", sqlite3.connect(DB_PATH))
    df["stratum"] = df.topics.map(lambda t: next((x for x in json.loads(t) if x != "other"), "other")) + "/" + df.kind
    pools = {s: g.sample(frac=1, random_state=seed).index.tolist() for s, g in df.groupby("stratum")}
    picked = []
    while len(picked) < min(n, len(df)):
        for s in sorted(pools):
            if pools[s] and len(picked) < n:
                picked.append(pools[s].pop())
    out = df.loc[picked].drop(columns="stratum").sort_values("created_at").assign(human_label="", off_topic="")
    out.to_csv(EVAL_DIR / "to_label.csv", index=False, encoding="utf-8-sig")  # BOM: Excel shows umlauts
    print(f"Wrote {len(out)} posts to eval/to_label.csv")


def sentiws_labels(texts: pd.Series) -> list[tuple[str, float]]:
    """SentiWS v2.0 (Remus et al., LREC 2010; CC BY-NC-SA 3.0). Downloaded on
    demand, not redistributed. Sum of word weights, negation flips the next 3
    words; thresholds fixed at +-0.1 before looking at our labels."""
    cache = EVAL_DIR / "sentiws"
    if not (cache / "SentiWS_v2.0_Negative.txt").exists():
        cache.mkdir(exist_ok=True)
        data = urllib.request.urlopen("https://downloads.wortschatz-leipzig.de/etc/SentiWS/SentiWS_v2.0.zip", timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                (cache / name.rsplit("/", 1)[-1]).write_bytes(z.read(name))
    lex = {}
    for f in ("Positive", "Negative"):
        for line in (cache / f"SentiWS_v2.0_{f}.txt").read_text(encoding="utf-8").splitlines():
            word, weight, *forms = line.split("\t")
            for form in [word.split("|")[0]] + (forms[0].split(",") if forms and forms[0] else []):
                lex[form.lower()] = float(weight)
    out = []
    for text in texts:
        total, flip = 0.0, 0
        for tok in re.findall(r"[a-zäöüß]+", text.lower()):
            if tok in {"nicht", "kein", "keine", "keinen", "keinem", "keiner", "nie", "niemals", "ohne"}:
                flip = 3
                continue
            total += -lex.get(tok, 0.0) if flip else lex.get(tok, 0.0)
            flip = max(flip - 1, 0)
        out.append(("positive" if total >= 0.1 else "negative" if total <= -0.1 else "neutral", round(total, 3)))
    return out


def kappa(df: pd.DataFrame, key: str) -> float:
    """Cohen's kappa: agreement corrected for chance. Raw agreement flatters a
    system that mostly predicts the common classes."""
    po = (df[f"{key}_label"] == df.human_label).mean()
    pe = sum((df.human_label == l).mean() * (df[f"{key}_label"] == l).mean() for l in LABELS)
    return (po - pe) / (1 - pe)


def acc(df: pd.DataFrame, key: str) -> str:
    hits = (df[f"{key}_label"] == df.human_label).sum()
    return f"{hits / len(df):.0%} ({hits}/{len(df)})" if len(df) else "n/a"


def evaluate() -> None:
    # sep=None sniffs ',' vs ';' (German Excel saves with semicolons).
    df = pd.read_csv(EVAL_DIR / "to_label.csv", dtype=str, encoding="utf-8-sig", sep=None, engine="python").fillna("")
    df["human_label"] = df.human_label.str.strip().str.lower()
    df = df[df.human_label.isin(LABELS)].copy()
    if df.empty:
        sys.exit("No labelled rows in eval/to_label.csv")
    cfg = load_config()
    for key in ("m1", "m2"):
        df[f"{key}_label"], df[f"{key}_score"] = zip(*classify(df.text.tolist(), cfg["models"][key]))
    df["b0_label"], df["b0_score"] = zip(*sentiws_labels(df.text))

    personal, news = df[df.kind == "personal"], df[df.kind == "news"]
    md = ["# Evaluation: models vs. human labels", "",
          f"{len(df)} hand-labelled posts ({len(personal)} personal, {len(news)} news). "
          "The labeller saw the text only, not the model outputs.", "",
          "| | agreement | Cohen's κ | personal | news |", "|---|---|---|---|---|"]
    md += [f"| {name} | {acc(df, k)} | {kappa(df, k):.2f} | {acc(personal, k)} | {acc(news, k)} |" for k, name in SYSTEMS.items()]
    md += [f"| Model 1 vs Model 2 | {(df.m1_label == df.m2_label).mean():.0%} | | | |", "",
           "κ: 0 = chance level, 1 = perfect. With 50 posts, differences of a few posts are noise.", "",
           "Human labels: " + ", ".join(f"{l} {(df.human_label == l).sum()}" for l in LABELS) +
           f". Not about rail: {(df.off_topic.str.lower() == 'yes').sum()}/{len(df)}.", ""]
    for k, name in SYSTEMS.items():
        cm = pd.crosstab(pd.Categorical(df.human_label, LABELS), pd.Categorical(df[f"{k}_label"], LABELS), dropna=False)
        md += [f"## Confusion matrix: {name}", "", "| human ↓ / predicted → | " + " | ".join(LABELS) + " |",
               "|---|---|---|---|"] + [f"| **{h}** | " + " | ".join(str(cm.loc[h, p]) for p in LABELS) + " |" for h in LABELS] + [""]
    dis = df[(df.m1_label != df.human_label) | (df.m2_label != df.human_label)]
    md += [f"## Disagreements ({len(dis)} posts where a model differs from the human)", "",
           "| kind | human | M1 | M2 | SentiWS | text |", "|---|---|---|---|---|---|"]
    md += [f"| {r.kind} | {r.human_label} | {r.m1_label} ({r.m1_score:.2f}) | {r.m2_label} ({r.m2_score:.2f}) | "
           f"{r.b0_label} ({r.b0_score:.2f}) | {r.text.replace(chr(10), ' ').replace('|', '/')[:200]} |" for r in dis.itertuples()]
    (EVAL_DIR / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    cols = ["id", "kind", "topics", "lang", "text", "human_label", "off_topic"] + [f"{k}_{x}" for k in SYSTEMS for x in ("label", "score")]
    df[cols].to_csv(EVAL_DIR / "test_table.csv", index=False, encoding="utf-8-sig")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(md[:12]))


if __name__ == "__main__":
    sample() if sys.argv[1:] == ["sample"] else evaluate()
