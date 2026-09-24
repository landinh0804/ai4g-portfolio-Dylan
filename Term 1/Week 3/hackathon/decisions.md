# Design decisions

The rubric awards points for work you can explain and defend, not for work you intended. This file
records the choices that are least obvious from reading the code, so either of us can answer for them
without having to reconstruct the reasoning.

The rest of the documentation: [README.md](../README.md) for what the tool does and how to run it,
[ETHICS.md](../ETHICS.md) for the risks, [samples/README.md](../samples/README.md) for what the
test bundles contain, and [docs/llm_integration.md](llm_integration.md) for how the code calls the
model.

---

### Gemini rather than Claude or OpenAI

Allowed by the brief. The free tier is generous enough for a week of iteration, and the structured
output support is strong enough to hold every LLM boundary to a schema. All API access is behind one
class (`llm/client.py`), so swapping providers means replacing one file, not rewriting the pipeline.
Models are pinned (`gemini-3.8-flash`) rather than using a `-latest` alias, so an upstream model
change cannot quietly alter what the tool tells a worker.

### Streamlit rather than a CLI alone or a full web stack

The user group reads on a phone, so a terminal demo would undercut the user story. A full
FastAPI/HTML stack would have given more layout control and more to break during a live demo. The
core pipeline is importable Python with no UI dependency, and both `app.py` and `cli.py` are thin
wrappers over `pipeline.analyse`, so the interface choice is reversible and the CLI is what the
secondary user (a caseworker triaging a stack) would actually want.

### Text and PDF only, images refused rather than degraded

The honest reason is time. The important part is the failure mode: an image upload raises
`UnsupportedFormat` with a message the user sees, and a PDF with under 200 characters of extractable
text is treated the same way. The alternative, running the pipeline over an almost-empty extraction,
would produce "we did not find these problems", which is the single worst output this tool can
give someone whose contract it could not actually read.

### Flags, not verdicts, in the extraction schema

The model is asked *"does a clause say X?"*, never *"is X allowed?"*. The flag list in `models.py` is
phrased as factual questions for this reason. It keeps the legal reasoning in
`s4_legal_checks.py` where it can be tested, reviewed by a non-programmer via the JSON, and corrected
when the law changes, none of which is possible if the verdict is formed inside a prompt.

### The rules are data, not code

`rules/legal_rules.json` holds the trigger conditions as well as the text. A change to a ceiling is a
one-line diff a teammate can review without reading Python, and the `verified` flag gives us a way to
ship a rule that is implemented but not yet checked, rather than choosing between shipping it
unmarked and not shipping it at all.

### Grounding threshold at 0.90, not 1.0

Exact-match-only would reject real quotes over PDF line-break hyphenation and whitespace noise, which
would push us toward loosening the check under demo pressure. 0.90 after normalisation survives
extraction noise while still rejecting paraphrases, and there is a test for exactly that case
(`test_paraphrase_does_not_pass_the_threshold`). The number is in `config.py`, not scattered.

### The confidence gate runs before composition, not after

Composing first and then hiding the result would still have paid for the call and would leave a
well-written wrong answer in memory next to the warning. Refusing earlier is cheaper and harder to
get wrong. Deterministic findings are still shown when gated, because a rule check that fired on a
verified quote does not become less true when a different document is unreadable; what is withheld is
the *summary* (the timeline and the questions), which depends on the bundle hanging together.

### Deterministic findings are reconciled after composition

The composition step needs to rewrite findings in the user's language, which means handing them to
the model, which means the model could alter them. `s5_compose._reconcile_findings` keeps the model's
wording and restores category, severity, quotes and rule id from the original; reinstates any
deterministic finding the model dropped; and discards any `DET-` id the code never issued. So the
worst a bad composition call can do is phrase a finding poorly. Three tests cover these three cases.

### Quotes stay in the source language

The explanation is translated; the quoted clause is not. This is what lets the user show the clause to
someone else, and it means that even where our output language quality is weakest, the evidence is
exact. It is also the reason the grounding check works at all: a translated quote could never be
matched against the source.

### Contacts are fixed data, ordered in code

Never model-generated. Confidential advice is always listed before enforcement, and the ordering is
enforced in `get_contacts` rather than requested in a prompt, because the ordering is a safety
property for a user whose employer controls their housing. Every entry answers "will your employer
find out?" explicitly, including the uncomfortable answer for the Labour Authority.

### `py` vs `python` on Windows

This was developed on Windows, where the `python` alias may route to the Microsoft Store stub. The
README uses `python` inside an activated virtual environment, which works everywhere. If you hit the
Store stub outside a venv, use `py` instead.

### stdout is forced to UTF-8 in the CLI

Not cosmetic. The Windows console defaults to cp1252, and this tool's whole purpose is writing
Polish, Romanian and Bulgarian. Without `_force_utf8_output`, printing a report in the user's own
language raises `UnicodeEncodeError` after the API call has already been paid for.

### The "talk to a person" line sits above the findings, not in the footer

A footer disclaimer is read, if at all, after the reader has formed their view. The point of this line
is that the list they are about to read is incomplete, so it has to arrive before the list. Same
reasoning for the take-away sheet, where a printed page of quoted clauses under a heading looks even
more like a verdict than the screen does. It also means the tool now routes to a human in both
directions: the confidence gate covers *we are unsure*, and this covers *we are sure*, which was the
unguarded case.

### Sample bundles carry their document language in the directory name

`bundle_e_en_tied_housing` rather than `bundle_e_tied_housing`. Until the English bundles existed,
every planted clause in the repository was Dutch, so a missed rule had two explanations that could not
be told apart: the pipeline did not recognise the structure, or the model did not read the language.
Two languages with the same structures planted in both makes that answerable, and putting the language
in the name is what stops the next person adding a bundle without deciding which side of that they are
testing. A test enforces the convention.

### The user is asked to redact, and the tool explains why it can ask

Asking somebody in a hurry to edit their contract before uploading it costs them time and adds a step
where they can give up. It is worth it because the request is honest: no rule in
`rules/legal_rules.json` reads a name, a date of birth, a BSN or an address, so a stripped contract
produces exactly the same findings. The alternative, doing it in code, is the better answer and is
not built; it is harder than it looks, because step 3 needs the *company* names to establish that the
employer and the landlord are one operation, so a redaction pass has to remove the worker's identity
while keeping theirs.

### The Gemini disclaimer is repeated in five places on purpose

On the page with the button, in the sidebar, before the CLI's first call, in `--check-setup`, and beside
the key in `.env.example`. Repetition in documentation is usually a smell; here it is the requirement.
A user whose central fear is that information about them travels needs to read that it will at the
moment they decide, not in a README they will never open, and the one place it was written before this
was the place nobody reads.

### The deduction ceiling is reckoned per hour worked, not against a 36- or 40-hour week

This was carried as an open question: reading WML art. 8 turned up a 36-hour reckoning, and the checks
assumed 40. Settled on 2026-09-22, and the answer is neither. Since
1 January 2024 the statutory minimum is an amount **per hour worked** (WML art. 8(1)(a)), and BMLMV
art. 2a(1)(a) caps the housing deduction at 25% of *the minimum wage applying to the worker for that
payment term*, an amount that moves with the hours actually worked. The 36-hour figure belongs to
the derivation of the *referentiemaandloon*, a monthly reference amount, and is not a basis for what
an individual worker is owed: adopting it would have set the ceiling about 10% below what the law
allows a worker on a 40-hour week, and this tool telling someone a lawful deduction is unlawful is
the same category of error as missing an unlawful one.

So `check_deduction_ceiling` now states the ceiling as a rate, `EUR 3.75 for every hour you work` at
the 2026 figures, and the monthly comparison is that rate written out over a week. The reference
value was renamed from `expected_full_time_hours_per_week` to
`assumed_hours_per_week_when_none_stated`, which is all it ever was: the fallback that makes a weekly
rent and an hourly wage comparable when the contract guarantees no hours. It stays `verified: false`,
because it is an assumption and no source can confirm it.

The finding also says that the ceiling falls in a short week while a fixed rent does not. That is not
decoration: it is the mechanism in the *EenVandaag* case cited in the README, where a fixed weekly rent
was deducted whether or not the person had worked a full week, and it is invisible in a monthly figure.

### Local runs are reported as degraded, and that is measured, not assumed

The tool can read documents with a model running on the machine (`--provider ollama`, or the sidebar),
which is the only complete answer to the privacy risk in ETHICS.md: nothing leaves the laptop. Every
local run is nonetheless reported as a degraded run, with confidence scaled down and the model named
in the report, and the question was whether that default could be lifted for at least one model.

It cannot, on this evidence. `scripts/evaluate.py` scores a real run against the ground truth in
`samples/expectations.json`: which rule ids a correct run must produce per bundle, which it must not,
and how the gate should behave. Measured on 2026-09-19:

| Run | Planted rules found | False positives | Grounding drops | Wall clock |
|---|---|---|---|---|
| `gemma3:12b`, local, all four bundles | **3 of 14** | 0 | 0 | 150s total (74s for bundle A) |
| `gemini-3.8-flash`, bundles A and B | **12 of 13** on bundle A | 0 | 0 | 248s for bundle A |

**The failure is in step 2, not in the rule layer.** The same rules fired on the hosted run from the
same documents. `gemma3:12b` did not extract the flags the rules key on, so `NL-ID-RETENTION`,
`RS-TIED-HOUSING`, `RS-NO-HOURS-NO-OTHER-WORK`, `RS-OPEN-ENDED-DEDUCTION`, `ET-EXPENSE-SWAP` and five
more never had anything to fire against. Bundle A also came back **gated** at 0.64 confidence: the local
run refused to summarise the one bundle the tool exists for. The degraded-confidence default is doing
exactly what it was written to do, and nothing goes into `CTF_OLLAMA_TRUSTED` on this evidence.

Speed is not the argument either way: roughly 75 seconds locally for a three-document bundle against
250 hosted, but the hosted figure was measured while every Gemini model was returning 503 and the client
was failing over repeatedly, so it is a bad day rather than a typical one. Accuracy is the argument.

One result is still unexplained, and it is a limitation rather than a decision: on the hosted run
`bundle_b_nl_clean`, one clean contract and the control, came back gated at 0.10 confidence, where the
local run scored it 0.76 and did not gate. `compute_overall_confidence` takes the *minimum* of the
stated confidences, and a single-document bundle gives the cross-reference step nothing to reason
about, so an honest low `reasoning_confidence` there can drag the whole report under the gate on its
own. If that is the mechanism, the tool refuses to read a clean single contract precisely when the model
is honest, which is a bad failure for the control case. Recording `reasoning_confidence` in the
`evaluate.py` output and re-running bundle B would settle it. Said plainly here, because a demo that
runs bundle B may hit it.

One model was measured, not the approach. A larger local model may well do better, and the honest claim
is the narrow one.
