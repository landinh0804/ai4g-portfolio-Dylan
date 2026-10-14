# Bahn-Puls: live passenger sentiment for Deutsche Bahn (Bluesky)

Hackathon, Term 1 Week 6 · SDG 9 (Industry, Innovation and Infrastructure) · pair project

**Live dashboard: <https://pulse-deutsche-bahn.streamlit.app/>**

## 1. The problem
**Why now:** Deutsche Bahn's reliability is at a historic low. In 2025 only 60.1% of
long-distance trains arrived less than six minutes late, the worst value ever recorded (74.4%
in 2015) ([ORF](https://orf.at/stories/3416167/)). In September 2026 the figure was 52.4%, and
the CEO's 2026 target of 60% is out of reach
([DB](https://www.deutschebahn.com/de/konzern/konzernprofil/zahlen_fakten/puenktlichkeitswerte-6878476),
[Wirtschaftsticker](https://wirtschaftsticker.com/2026/10/puenktlichkeit-der-fernzuege-verharrt-auf-niedrigem-niveau/)).
DB attributes this to an unprecedented construction programme, including the full closure of
Hannover-Berlin since October 2026 ([Dr. Web](https://www.drweb.de/bahn-puenktlichkeit-september-2026-fernverkehr/)),
and to infrastructure faults. Regional trains fare far better (88.2%). With trust this low,
communication matters: passengers who are warned early about a closure or a replacement bus are
frustrated less than those who find out on the platform.

Passengers voice delays, crowding, app failures and construction chaos on social media long
before these show up in complaint statistics. A regional customer-communication team decides
every morning which issue gets proactive communication, today mostly by gut feeling. Bahn-Puls
turns the public stream into one signal: **which topic's negative sentiment is rising above its
own recent baseline, and which posts are behind it?**

**Example from our data** (final snapshot of 14 Oct, 803 personal posts): 212 posts were about delays
and cancellations, and Model 2 rated 55% of them negative, against 39% across all personal posts.
Construction posts (67) came out at only 33% negative, mostly neutral announcements of closures
and replacement buses. That is the kind of difference a morning team can act on: delays first,
and construction notices are information people need rather than a source of anger.

## 2. The stream and Bluesky's terms of use
- **Source:** Bluesky search (`app.bsky.feed.searchPosts`, `sort=latest`) with 29 German queries
  ([config.yaml](config.yaml)). Reddit was out of scope (API access needs approval).
- **Viability:** a 3-day test run (9 to 12 Oct) found ~250 relevant posts per day after filtering,
  enough for the 300-item requirement within 48 h.
- **Access:** search works anonymously via `api.bsky.app` (`public.api.bsky.app` returns 403).
  The collector logs in with an app password (repository secrets) when available.
- **Terms:** read on 2026-10-12 at [Bluesky Developer Guidelines](https://bsky.network/docs/developer-guidelines/).
  They forbid spam (automated or bulk interactions such as follows, likes, replies or messages),
  require services to delete content a user has asked to have deleted, and ask for security
  measures that protect user data. Our collector is **read-only**: it searches public posts and
  never posts, likes, follows or messages anyone, so the spam rule is not touched. It stores no
  author data (see Ethics) and makes about 30 to 60 requests per 10 minutes. The page names no
  numeric rate limit, so we kept the rate low. The deletion rule is the one we only partly meet
  (see Ethics).

## 3. The user and the decision
**User:** a regional DB customer-communication team, or a passenger association (Pro Bahn).
**Decision:** every morning, which issue gets proactive communication today.
**Shown:** per topic, the share of negative passenger posts against that topic's 7-day baseline,
the number of posts behind every point, and the posts themselves.

## 4. SDG 9 rationale
SDG 9.1 asks for "quality, reliable, sustainable and resilient infrastructure … with a focus on
affordable and equitable access for all". Rail is the backbone of low-carbon mobility, and its
perceived reliability decides whether people keep using it. Bahn-Puls gives operators a cheap,
continuous, passenger-centred feedback channel: what delays and disruptions mean to the people
affected, next to punctuality statistics.
Targets: [SDG 9.1](https://sdgs.un.org/goals/goal9) (quality, reliable, resilient
infrastructure) is the main one. 9.4 (upgrading infrastructure to make it sustainable) is a
secondary fit, because rail is the low-carbon option that people only keep using if it works.

## 5. Models and evaluation
| | Model 1 | Model 2 |
|---|---|---|
| | `oliverguhr/german-sentiment-bert` | `cardiffnlp/twitter-xlm-roberta-base-sentiment` |
| Training data | 1.8 M German reviews, tweets, Facebook, Wikipedia | 198 M tweets; sentiment fine-tuned in 8 languages incl. German |
| Licence | MIT | not stated on the Hub (code repo Apache-2.0) |

Both run locally on CPU via `transformers` at pinned revisions; no chat-model API. Details and
concerns: [docs/model_cards.md](docs/model_cards.md).

**Evaluation** on 50 hand-labelled posts from the test run, stratified by topic and
news/personal. The labeller saw the text only, not the model outputs
([eval/results.md](eval/results.md)):

| | agreement | Cohen's κ |
|---|---|---|
| Model 1 | 50% (25/50) | 0.11 |
| Model 2 | 54% (27/50) | 0.18 |
| SentiWS word list (baseline) | 54% (27/50) | 0.25 |

Both transformers are only slightly better than chance on this stream, and the simple word list
is as good as they are. With 50 posts a difference of a few posts is noise, so we don't claim one
system is better. The most common error is reading neutral posts as negative (Model 1: 12 of 23
neutral posts), which inflates the negative share. Model 2 is closer (48% predicted negative vs
46% by hand), so it is the dashboard default. 9 of the 50 posts (18%) were not about rail at all.
Read the dashboard as a trend indicator, not a measurement.

**Three failures, explained** (all in [eval/results.md](eval/results.md)):
1. **Service notices read as neutral.** A replacement-bus notice for line RE30 was labelled
   negative by us, but both models said neutral (confidence 1.00 and 0.93). The text is a plain
   announcement with no emotional words; the bad news is in the situation, not the wording.
2. **Sarcasm and jokes.** A post that mimics a ticket inspector ("Wie kommen Sie bitte darauf,
   dass ich keine Fahrkarte habe?") was neutral for us, but both models said negative (0.94 and
   0.86). Model 1's preprocessing also strips emojis, which removes a sarcasm signal.
3. **Sentiment about something else.** An angry post about a Bundestag vote was rated negative
   by both models and the word list (0.97 and 0.89), but we labelled it neutral because its tone
   is not about the railway. That is query noise: the models score the tone of the whole post,
   not its attitude towards the Bahn.

A smaller case: a joyful post about reaching Linz easily by train was labelled neutral by us but
positive by all three systems. We think the human label was too strict, so our own labels are
not a perfect gold standard either.

**What we would do next:** filter off-topic posts before scoring, add a rule or a third model for
service notices, and label more than 50 posts.

## 6. Architecture
```
GitHub Actions (.github/workflows/bahn-puls-collect.yml)
  one run = ~5.5 h loop:  every 10 min → python -m pulse.collect → publish pulse.db
  then dispatches its own successor (hourly cron only restarts a broken chain)

python -m pulse.collect  (one cycle)
  1. searchPosts per query, paging until the stored per-query watermark (newest indexedAt)
  2. filters, in memory: empty, <4 words, crossposted RTs, bots (self-label, name pattern,
     repeated templates, posting rate), rail context for ambiguous queries, backdated posts
  3. derive: id = sha256(URI), kind = news|personal (linked domain), topics (keyword regexes)
  4. INSERT OR IGNORE → idempotent;  5. classify unlabelled rows with both models
  6. log the run in `runs` (start, end, counts, errors)

dashboard.py  (Streamlit, read-only) ← pulse.db from the `bahn-puls-data` branch
```
**Why it looks like this:**
- *GitHub's cron is not the clock.* In the test run it fired only every 3 to 10 h, so each run
  loops internally and starts the next one itself.
- *Store first, classify second:* a model failure never loses posts.
- *Data on its own branch, force-pushed as one commit:* no merge conflicts with code and no
  history bloat. A guard refuses to publish if the item count shrinks.
- *Watermark on `indexedAt`:* `createdAt` is client-set (imported posts claim 2020).

## 7. How to run
```bash
cd "Term 1/Week 6/hackathon"
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
cp .env.example .env                                # optional Bluesky app password

python -m pulse.collect             # one cycle (first run downloads ~1.5 GB of models)
python -m pulse.evaluate sample     # 50 stratified posts -> eval/to_label.csv
python -m pulse.evaluate            # labelled CSV -> eval/results.md, eval/test_table.csv
streamlit run dashboard.py          # fetches the live DB automatically
```
**One collector for both submissions.** The collector runs on GitHub Actions in
[flxr8/ai4g-portfolio-felix-reichle](https://github.com/flxr8/ai4g-portfolio-felix-reichle/actions)
and keeps running during grading. Copies of this project in a team member's repo read that
repo's live data (`live_db_url` in `config.yaml`); the workflow is skipped there, so there is only
one dataset. `data/pulse.db` is the committed final snapshot (14 Oct: 885 posts, 303 runs, 50.6 hours of operation); the dashboard falls back to it if the live
data can't be downloaded. The `runs` table in the database is the proof of continuous operation. The hosted dashboard
uses [deploy/bahn-puls/streamlit_app.py](../../../deploy/bahn-puls/streamlit_app.py), because
Streamlit Cloud can't install requirements from a path containing spaces.

## 8. Dashboard
Live at <https://pulse-deutsche-bahn.streamlit.app/> (refreshes from the collector every 10 minutes),
or locally with `streamlit run dashboard.py`.
- **Topics against their baseline:** latest negative share per topic vs its baseline, with
  status ▲ above / ● around / ▼ below / ◌ too few posts / ◌ no baseline yet.
- **One chart per topic:** negative share per day (or hour, last 48 h), baseline dashed, `n=`
  next to every daily point. Points with fewer than 10 posts are hollow grey.
- **Topics:** delays & cancellations, app & tickets, construction & replacement buses, on-board
  experience, other. Crowding and service were merged into "on-board experience" because each
  got only ~6 personal posts a day, so their daily points never reached the 10-post minimum.
  *Strikes* is dormant (~0 posts a day) and appears only when there are strike posts, which is
  exactly when it matters. Topics are recomputed from `config.yaml` on every run, so stored tags
  always match the current keyword lists.
- **Toggles:** daily/hourly, personal/news/both (personal by default), Model 1/Model 2.
- **Posts behind a point:** pick a day and topic for time, text, label, confidence and link.
- **Baseline:** pooled negative share over the previous 7 days, excluding the current period
  (a spike must not hide in its own baseline). It needs ≥ 10 earlier posts, otherwise it's blank.
- **Limitation:** no English translation. The open local model (opus-mt-de-en) needs the
  `sentencepiece` package, outside our agreed dependencies.

## 9. Ethics
- **Data minimisation:** only text, timestamps and derived fields, as the brief requires. No
  handles, DIDs, names or profile data. Author info is used in memory to detect bots, then
  discarded. The item id is a sha256 hash of the post URI, which can't be reversed to an author.
- **No post URLs (decided 13 Oct).** A Bluesky URL contains the author's DID
  (`bsky.app/profile/did:plc:…`), so storing it would break the brief's "no DIDs" rule. The
  collector stores none; databases from before that date are migrated on the next run (column
  dropped, file vacuumed so the old values are really gone), and the URLs were removed from the
  labelled sample. The dashboard still lets readers open the posts behind a point: it shows their
  full text. Post texts can themselves contain links that people wrote (e.g. to another post);
  we keep the text as written.
- **What we publish:** the full database (texts, timestamps, labels), committed when the project
  is final, so every number can be re-checked. While collection runs, the live copy is on the
  public `bahn-puls-data` branch; it should be deleted once collection stops after grading.
- **Deletions:** Bluesky's guidelines require services to delete content that users have asked
  to have deleted. We don't re-check whether stored posts were deleted, so we only partly meet
  this (acceptable for a one-week dataset, not for long-term use). Anyone who asks us to remove a
  post can have it deleted from the database.
- **Not representative:** Bluesky users skew young, urban and online, and people post when things
  go wrong.

## 10. What this must NOT be used for
- Judging or disciplining individual staff.
- Claiming a problem is solved because people stopped posting about it.
- Profiling or contacting individual passengers.
- Ranking lines or regions on a handful of posts.
- Replacing punctuality data or proper customer surveys.

## 11. Team and who did what
Pair project: Felix Reichle (GitHub `flxr8`) and Lan (Dylan) Dinh Duy (group 12).
- **Felix:** the collector and its filters, the GitHub Actions scheduler, the Streamlit dashboard
  and its hosting, the evaluation code, the model cards and the first version of the README.
- **Dylan:** a second, independent collection run on a laptop (section 12), checks of the data and
  the sentiment results, the reading of Bluesky's terms, the SDG 9 targets, the results and
  failure analysis text in this README, and the slides.
- **Shared:** Felix proposed Bluesky after Reddit refused API access, and we agreed that one data
  source is enough. The 50 hand labels in `eval/` were written without seeing the model outputs.
- **AI assistance:** an AI coding assistant (Claude) helped with code, data checks and drafting
  text. The brief allows this; sentiment is scored only by the two pre-trained models above, never by a chat model.

## 12. Independent collection run on a second machine
GitHub's scheduler fired only twice in the first hours of the test run, so Dylan also ran the
same collector (the version from 9 October, before it was merged into one `collect.py`) on his
laptop with the Windows Task Scheduler, every 10 minutes, with his own Bluesky app password.
This run is **separate from the shared dataset**: the dashboard and the numbers in sections 1 to 9
use the shared collector's `data/pulse.db`. It is kept in [`dylan_run/`](dylan_run/) as extra
evidence that the pipeline ran continuously for the required time.

| | |
|---|---|
| Period | 2026-10-10 00:29 to 2026-10-12 02:28 (Berlin time), 50 hours |
| Runs | 301, all successful, none missed |
| Posts | 739 (669 personal, 70 news); the first run back-filled 315, then about 10 per hour |
| Model 1 (german-sentiment-bert) | 338 negative (45.7%), 385 neutral (52.1%), 16 positive (2.2%) |
| Model 2 (twitter-xlm-roberta) | 319 negative (43.2%), 313 neutral (42.4%), 107 positive (14.5%) |
| Agreement between the two models | 60.2% |

Files: `dylan_items.csv` (the posts with labels and scores, **without post URLs**, in line with the
ethics decision above) and `dylan_runs.log` (the collector's own log, one line per cycle and
one per run). Errors in the log are one-off network timeouts on a single search term.
The mix of sentiment is similar to the shared dataset: mostly negative or neutral, with few positive posts.
