# Contract Trap Finder

**AI for Good, Hackathon 3: Equal Access · SDG 10, Reduced Inequalities (targets 10.3 and 10.7)**

Team: *Lucas Jansze (23052236) & Dinh Duy Lan (23174242)*

A Python tool that reads the whole bundle of documents a labour migrant is asked to sign
(employment contract, housing agreement, deduction authorisation, transport, insurance) and tells
them, **before they commit**, what in it is unlawful, what is lawful but shifts every risk onto
them, and where they are being offered less than a Dutch colleague doing the same work is entitled
to.

## Presentation and demo

| | Link | Where it is in the portfolio |
|---|---|---|
| **Presentation** | *To be added* | `ai4g-portfolio-LucasJansze/Term 1/Week 3/presentation/` |
| **Demo video** | *To be added* | `ai4g-portfolio-LucasJansze/Term 1/Week 3/presentation/` |

The hackathon files themselves are in `ai4g-portfolio-LucasJansze/Term 1/Week 2/hackathon/`.

---

## The rest of the documentation

This README is the way in: what the problem is, who the tool is for, how it works and how to run it.
Four other documents carry the parts that do not belong in it, and each is linked again from the section
it belongs to.

| Document | What it is, and when you want it |
|---|---|
| **[ETHICS.md](ETHICS.md)** | The ethical reflection: eight risks specific to this prototype and what the code does about each. |
| **[docs/llm_integration.md](docs/llm_integration.md)** | How the Python code calls the model, handles its answers, uses the system prompts and keeps state. |
| **[docs/decisions.md](docs/decisions.md)** | The least obvious design choices, and why we made them. |
| **[samples/README.md](samples/README.md)** | The six invented document bundles: what is planted in each, and which rule should catch it. |

And the files in the code worth opening first, in order of interest rather than of dependency:

- **[`src/contract_trap_finder/safety.py`](src/contract_trap_finder/safety.py)**: the five guardrails. If you read one file, read this one.
- **[The three system prompts](src/contract_trap_finder/llm/prompts/)**: [`structure.md`](src/contract_trap_finder/llm/prompts/structure.md), [`cross_reference.md`](src/contract_trap_finder/llm/prompts/cross_reference.md) and [`compose.md`](src/contract_trap_finder/llm/prompts/compose.md), one per step that uses the model.
- **[`src/contract_trap_finder/llm/client.py`](src/contract_trap_finder/llm/client.py)**: the only code that calls the Gemini API, and what it does with the answer.
- **[`src/contract_trap_finder/rules/legal_rules.json`](src/contract_trap_finder/rules/legal_rules.json)**: the 14 legal rules as data, each with its article, its `verified` flag and a `verified_by` line recording what was read.
- **[`src/contract_trap_finder/rules/contacts.json`](src/contract_trap_finder/rules/contacts.json)**: the organisations the tool routes people to. Never model-generated.
- **[`samples/expectations.json`](samples/expectations.json)**: the ground truth `scripts/evaluate.py` scores a real run against.
- **[`.env.example`](.env.example)**: every setting, with the reasoning attached to each one.

The full file-by-file map is under [Repository layout](#repository-layout).

---

## The problem

Labour migrants recruited to work in the Netherlands are handed several documents at once: an
employment contract with an agency, a housing agreement, an authorisation for deductions from
wages, and often transport and insurance. The bundle is presented at a recruitment office days
before departure, or on the day of arrival. It is frequently in Dutch, it is signed in minutes, and
the worker often keeps no copy.

Three kinds of problem hide inside that bundle, and none is visible to the person signing it:

1. **Terms that are simply unlawful.** A fee charged to the worker for arranging the job,
   deductions above the legal ceiling, a clause penalising them for later taking a job directly with
   the company they are sent to. These are void, but a clause does not stop working just because it
   is void. It works until somebody challenges it, and nobody challenges what they cannot read.
2. **Terms that are lawful but place every risk on one side.** No guaranteed hours combined with a
   ban on other work; a contract that ends the day the assignment ends; a travel advance repaid by
   deduction; housing, transport and insurance all supplied by the employer and all lost at the same
   moment. A Dutch colleague who quits loses income. A worker in this position loses income, home,
   transport and insurance on the same day.
3. **Terms below what the law already promises them.** Dutch law entitles agency workers to the
   same pay as the hiring company's own staff doing the same work. Most of the people we are
   building for do not know this right exists.

The common thread is not cruelty but **asymmetry of information**. Every one of these terms is
written by a party who knows exactly what it means, and signed by a party who does not.

### How big this is

**The population.** CBS puts the number of labour migrants in the Netherlands at roughly **960,000**:
in its *Belevingen* survey for 2025, just under **7% of adults** described themselves as a labour
migrant, *"naar schatting 960 duizend arbeidsmigranten"* in CBS's own words ([CBS, *Opvattingen
over arbeidsmigranten*, published 8 June 2026, ch.
2](https://www.cbs.nl/nl-nl/longread/diversen/2026/opvattingen-over-arbeidsmigranten/2-hoeveel-arbeidsmigranten-telt-nederland-)).
CBS also says plainly that the count depends on the definition, and the spread is worth quoting
rather than hiding: restricting its StatLine tables to people resident five years or less gives
**406,000** working immigrants at the end of 2023, of whom **402,000** were employees, while the
*Migrantenmonitor* on the same restriction gives **720,000** in paid employment.

**The group this tool is built for is the agency worker, and it is nearly half of them.** Of the
**683,000** labour and knowledge migrants who worked in the Netherlands at some point in 2024 (about
**80% of them from EU or EFTA countries**), **just over 315,000, a little under half, worked as agency
workers**; 88% of those (277,000) through members of the two branch associations ([SEO Economisch
Onderzoek, Bussink, Ruit & 't Hart, *Arbeidsmigranten in de uitzendsector*, March
2026](https://www.seo.nl/wp-content/uploads/2026/04/2026-41-Arbeidsmigranten-in-de-uitzendsector.-Onderzoek-naar-omvang-en-kenmerken.pdf),
pp. 2 and 8–9). Worth saying who paid for it: the study was commissioned by **ABU and NBBU**, the
agency sector's own branch organisations. We cite it because it is the most precise count available and
because its definition is stated openly (18 to 67, no Dutch nationality, working within three months
of arrival), but a figure about the agency sector, published for the agency sector, deserves the
attribution in the same sentence.

**The structure we are looking for is the normal one, not the exception.** The Aanjaagteam Bescherming
Arbeidsmigranten (the Roemer commission) devoted recommendation **4.4.B** of *Geen tweederangsburgers*
(30 October 2020, p. 44) to exactly it: *"Waar een integraal contract voor arbeid en wonen als service
richting de arbeidsmigrant kan worden gezien, wordt de arbeidsmigrant hierdoor ook afhankelijk van de
werkgever. Daarom adviseert het Aanjaagteam te streven naar ontkoppeling van arbeidscontracten en
huurcontracten."* Six years on it is not law but policy in the other direction: on 30 October 2025 the
minister dropped her predecessor's plan to phase the wage deduction out. FNV's response names the
mechanism this tool looks for, *"Arbeidsmigranten blijven **dubbel afhankelijk** van hun werkgever –
als baas én huisbaas"*, and makes the equality argument directly, that the rule applies in practice
only to labour migrants ([FNV, 30 October
2025](https://www.fnv.nl/nieuwsbericht/algemeen-nieuws/2025/10/minister-houdt-pervers-verdienmodel-over-rug-arbei)).
Research published this year cuts away the assumption the arrangement rests on: that these are people
passing through. *"Meer dan de helft blijft langdurig. Dan moet je denken aan minstens zes jaar, maar
vaak nog langer"*, and their housing stays insecure: shared or informally rented, and *"dat verbetert
met de jaren lang niet altijd"* ([UvA / PBL, D. Loomans, 2 February
2026](https://www.uva.nl/content/nieuws/persberichten/2026/02/langdurig-verblijf-onzekere-huisvesting-de-realiteit-van-eu-arbeidsmigranten.html)).
The same research contains a finding that runs against the easy version of our own argument, so we say
it here: Loomans finds housing insecurity is **not** significantly more common among migrants placed by
agencies than among those who are not, and concludes it is a structural problem of the labour and
housing markets rather than one the agencies alone create. That does not weaken the case for this tool.
The bundle it reads is still where the tying is written down, and the deduction ceiling is still broken
in individual contracts. But it does mean the tool addresses one mechanism, not the whole problem.

**A concrete case, with the arithmetic our check does.** Joost van Woelderen of Bewonersbelangen
Arbeidsmigratie, which helps migrants with housing complaints and receives reports of this weekly,
told *EenVandaag* that he sees payslips with **a fixed weekly rent deducted even when the person works
fewer hours, which pushes the deduction above 25%**. A woman working through an agency in a
distribution centre gives the numbers: *"Ik betaal 125 euro per week voor mijn kamer, ongeacht hoeveel
uur ik werk... Soms krijg ik maar 19 of 20 uur werk en dan blijft er bijna niets over"* ([EenVandaag,
26 November
2025](https://eenvandaag.avrotros.nl/artikelen/arbeidsmigranten-moeten-vaak-meer-dan-kwart-van-loon-inleveren-voor-huisvesting-maar-dat-mag-niet-blijft-niets-over-162048)).

Run that through the rule. In a 40-hour week the ceiling is 25% of 40 × EUR 14.99, about **EUR 150**,
and EUR 125 of rent sits under it. In one of her 19-hour weeks the ceiling is 25% of 19 × EUR 14.99, or
**EUR 71**, and the same unchanged rent is **nearly double what the law allows**. The rent does not
move with the hours; the ceiling does. That is why `check_deduction_ceiling` states the ceiling as a
rate per hour worked and says out loud that a short week widens the gap, and
`tests/test_legal_checks.py` runs her figures as a test.

That ceiling is real and checkable (Besluit minimumloon en minimumvakantiebijslag art. 2a(1)(a),
verified against the statute and recorded in
[`rules/legal_rules.json`](src/contract_trap_finder/rules/legal_rules.json)), and **a worker holding
the contract cannot check it**, because doing so means knowing the rule exists, knowing this year's
minimum wage, and doing the arithmetic on a document in Dutch. That is the gap this tool closes, and
`NL-WML-13-DEDUCTION-CEILING` is the check that closes it.

**And complaining afterwards is not the same as knowing beforehand, because complaining costs the
bed.** The same worker: *"Iedereen weet dat het niet klopt, maar niemand zegt iets. Als je klaagt, word
je naar een slechtere woning gestuurd of verlies je je bed."* And on why it is not noticed in the first
place: *"We spreken de taal niet goed, we kennen de wetten niet. Je denkt dat het normaal is, maar het
is niet normaal om zo weinig over te houden van je werk."* That is this project's premise in a
sentence, said by somebody it is for. Enforcement after the fact asks a person to risk their housing on
a complaint; the tool is aimed at the fifteen minutes before the signature, which is the one moment the
choice is still free.

## Why this is SDG 10

The Dutch labour market already contains a written equal-treatment norm for agency workers, and a
body of law limiting what can be taken from their wages. **The inequality is not that the rules are
missing. It is that one group of workers can check whether the rules are being followed and another
group cannot.** That gap in verification is what this tool closes, and it is why this is an SDG 10
project rather than a general consumer-protection tool.

| Target | How this project sits inside it |
|---|---|
| **10.3** (primary) | The discriminatory practice we address is not the absence of the equal-pay rule but the absence of any way for the worker to check it, and a contract bundle built on the assumption that they never will. |
| **10.7** (primary) | The operative word is *safe*. Recruitment debt, fees charged to the worker, and a job whose end also ends the housing, transport and insurance all make labour mobility unsafe. The tool makes them visible before the person commits. |
| 10.4 | Deductions and wage-for-expenses arrangements cut take-home pay below the advertised rate and lower the basis for pension, sick pay and benefits. The tool quantifies both. |
| 10.2 | These bundled structures are offered to migrant workers and not to their Dutch colleagues on the same shift. The difference in treatment follows origin, not the work. |

**Who benefits if it works:** the worker, who learns what they are committing to at the one moment
they still have a choice; caseworkers at unions and migrant-support organisations, who can triage a
stack of contracts in minutes; and compliant agencies, who stop being undercut by operators using
these terms.

**What it does not do:** it enforces nothing, changes no contract and creates no housing. It removes
an information asymmetry, which is necessary for the worker to act but not by itself sufficient.

## Who it is for

**Primary user.** A person roughly 20–45, recruited from another EU member state through an
intermediary for agency work in Dutch logistics, food processing, horticulture or agriculture, who
has just been handed a bundle of documents including employer-arranged accommodation. They read on a
phone, often on mobile data. They have minutes at a recruitment desk, or one evening before
departure. Their reading language is most likely Polish, Romanian or Bulgarian while the contract is
in Dutch. They have low trust in institutions and a well-founded fear of retaliation: the company
that employs them also controls where they sleep.

**Secondary user.** Caseworkers and volunteers at trade unions and migrant-support organisations,
who see these bundles repeatedly and need a fast, consistent first read. Unlike the primary user
they *can* verify the output, so the tool is built to serve both.

**Explicitly not our users.** Employers and agencies: we assess documents rather than people, but we
treat an agency using this to sanitise its contracts as a risk, not a market. Workers on direct Dutch
contracts with Dutch-language support, and high-earning international staff with employer-provided
legal advice: both already have what this substitutes for. Asylum seekers and undocumented workers:
a different legal regime and data risks we cannot handle responsibly in a one-week prototype.

## Why this solution fits the problem

The worker quoted above names both halves of the problem in one sentence: *"We spreken de taal niet
goed, we kennen de wetten niet."* They cannot read the contract, and they do not know which rules
apply to it. The tool is built around those two gaps and around the conditions the user is in when it
matters, so each part of it answers something specific:

| The problem, or the user's situation | What the tool does about it |
|---|---|
| **Unlawful terms** stay in force until someone challenges them, and nobody challenges what they cannot read | Step 4 checks the extracted terms against [14 legal rules](src/contract_trap_finder/rules/legal_rules.json), each tied to its article. Plain Python, no model, so the answer is either right or visibly unverified. |
| **Risk-shifting terms** are spread across separate documents: housing in one, the ending of the job in another | Step 3 has the model read the documents *together*, and step 5 turns what it finds into a dated exit scenario: if the work stops, what else stops, and when. |
| **Pay below the equal-treatment norm**, under a right most of these workers do not know exists | Two rules look for this directly: the equal-pay right for agency workers (Waadi art. 8), and part of the pay labelled as expenses, which lowers the wage that minimum pay and holiday allowance are reckoned on. The finding tells the worker the right exists and what to ask to check it. |
| The contract is **in Dutch** and the reader reads Polish, Romanian or Bulgarian | The report is written in seven languages, while every quote stays in the contract's own wording. The take-away sheet puts each question in both languages side by side. |
| **Minutes at a recruitment desk, on a phone** | A web page with one button, findings sorted by severity, and a timeline instead of a legal summary. |
| **Complaining costs the bed** | Questions worded so they can be asked in writing without reading as a challenge; confidential advice listed before enforcement, with whether the employer will find out; no account, and a local mode where nothing leaves the machine. |
| The user **cannot check the output** | Every finding quotes its clause, anything without a quote is deleted, and a report the tool is unsure of is replaced by a referral to a named organisation. |

This is also why the design is a mix. The model does the reading that only a language model can do
(indirect wording, several languages, links between documents), and plain code does the checking that
has to be right. Why a leaflet, a checklist or a rule engine alone would not do the same job is set out
under [Why a simpler alternative would not work](#why-a-simpler-alternative-would-not-work).

---

## How it works

Five steps. **Which steps use the model, and which deliberately do not, is the central design
decision of this project.**

| Step | What happens | LLM? |
|---|---|---|
| **1. Ingest** | Pasted text and PDFs are read into plain text. No fixed format or complete set is assumed. | No |
| **2. Structure** | Each document becomes typed JSON: parties, clauses, amounts, dates, notice periods, deductions, termination conditions. **Every field must carry the exact clause text it came from, or it is discarded.** | **Yes** |
| **3. Cross-reference** | The reasoning step. Are the employer, landlord, transport provider and insurer the same company? Does the end of one contract trigger the end of another? Which obligations bind only one side? | **Yes** |
| **4. Legal checks** | Deterministic lookups against published rules: deduction ceilings, the prohibition on fees charged to the worker, the ban on clauses obstructing direct employment. **These answers must be correct, not plausible, so the model is kept out of them entirely.** | No |
| **5. Compose** | Findings are sorted by category and severity and written into the four outputs below, in the user's language. | **Yes** |

### Why an LLM is necessary

- **Half the findings are relationships between documents.** Clause 4 of the housing annex only
  matters because of clause 3.2 of the employment contract. No keyword search or template matcher can
  detect a dependency between two files it has no schema for.
- **The wording is deliberately indirect.** Contracts say *"de accommodatie wordt ter beschikking
  gesteld in verband met de terbeschikkingstelling"*, not *"you will be homeless if you quit"*.
  Recognising those as the same statement is semantic work.
- **The input is unstructured and multilingual.** Several languages, no two agencies using the same
  template.
- **Entity resolution is fuzzy.** Establishing that the agency and the housing company are one
  operation requires reasoning over messy text, not a lookup.

And why the model is kept out of step 4: the ceilings, prohibitions and register checks must be
right, not plausible. **The model interprets; the lookups make the output true.**

### Why a simpler alternative would not work

- A leaflet already explains that tied housing and recruitment fees are bad. It cannot answer the
  only question the user has: *does my contract do this?*
- A checklist assumes the user can read the contract well enough to tick the boxes. If they could,
  they would not need the tool.
- A lawyer is the right answer and an unavailable one. There is no lawyer at the recruitment desk at
  8am, and advice in a second language costs more than a week's wages.
- A rule engine alone would catch clumsy contracts and miss careful ones, and the careful ones cause
  the harm at scale.

### The output

Four things, deliberately not a list of clauses. A clause list is not something a worried person at
a recruitment desk can act on.

1. **Findings**, sorted: unlawful first, then risky, then below the equal-treatment norm. Each quotes
   the clause it came from and says in one sentence what it means in practice.
2. **The exit scenario**, a dated timeline rather than a legal summary: *"your contract ends the same day
   (clause 3.2), you must leave the accommodation within 3 days (housing annex, clause 7), your
   insurance stops at the end of the month (clause 11)."*
3. **Safe questions to ask in writing**, such as *"If I move to a different job later, can I stay in the
   accommodation?"* rather than *"Why does clause 7 tie my housing to this job?"* Given in both
   languages, with a push to ask by message. The aim is a written record, not the answer. The tool
   also explains what a refusal to answer in writing tells them.
4. **Who to contact, and what happens if you do**: confidential advice first, enforcement bodies
   second and only by the user's own choice. For each: what they will actually do, whether the
   employer is likely to find out, and how long it takes. A phone number on its own would be
   irresponsible.

Above all four, whenever anything was found: **a line saying to talk to a person about it.** Not a
footer disclaimer; it is the first thing above the findings, in the user's own language, because a
report full of correctly quoted clauses is the one most likely to be read as the end of the matter
rather than the start of a conversation.

### How the Python code uses the model

The full walkthrough, with line references, is in **[docs/llm_integration.md](docs/llm_integration.md)**.
The short version:

**One method makes every call.** Steps 2, 3 and 5 each call `client.generate_json(...)` with a system
prompt, a user prompt, a Pydantic class describing the answer, and a temperature. Only
[`llm/client.py`](src/contract_trap_finder/llm/client.py) talks to the API, using Google's
`google-genai` SDK. Simplified, for step 2:

```python
config = types.GenerateContentConfig(
    temperature=temperature,                      # 0.0 extraction, 0.1 reasoning, 0.3 writing
    response_mime_type="application/json",
    response_json_schema=schema_for(schema_model),  # generated from the Pydantic class
    system_instruction=load_prompt("structure"),    # a Markdown file, see below
)
response = client.models.generate_content(model="gemini-3.8-flash", contents=prompt, config=config)
document = StructuredDocument.model_validate_json(response.text)
```

**Handling the response.** The answer must parse into the Pydantic class, or the call raises
`LLMInvalidOutput` (after one attempt to close the brackets of a cut-off answer). A valid answer then
goes through `safety.py`, which checks every quote in it against the original documents and deletes
anything it cannot find. If a call fails outright, the step it belongs to degrades the report rather
than crashing it. A spent daily quota switches to another API key; an overloaded model switches to the
next model in the list; the report names the model that actually answered.

**System prompts.** Each step that uses the model has its own system prompt, kept as a Markdown file
and loaded by `load_prompt()`:

| Prompt | Step | What it asks for |
|---|---|---|
| [`structure.md`](src/contract_trap_finder/llm/prompts/structure.md) | 2 · Structure | Parties, money terms, hours, termination conditions and 15 factual flags from one document, each with an exact quote |
| [`cross_reference.md`](src/contract_trap_finder/llm/prompts/cross_reference.md) | 3 · Cross-reference | The same company in different roles, one ending that triggers another, one-sided obligations, contradictions |
| [`compose.md`](src/contract_trap_finder/llm/prompts/compose.md) | 5 · Compose | The findings, exit timeline and safe questions in the user's language, without advice, verdicts or invented quotes |

The system prompt carries the rules, which are the same on every run. The user prompt, built in
Python by each step, carries only this run's data between `BEGIN` and `END` markers.

**Sessions.** The model keeps no conversation. Every call is a single, independent request, and the
state between steps is held in Python: each step returns a typed object, and the next step puts what
it needs into its own prompt as JSON. That is deliberate. Only data that has passed the quote check
moves forward, so a clause deleted after step 2 cannot come back in step 5. What the app does keep is
per browser tab, in Streamlit's `st.session_state`: the uploaded documents and the finished report, in
memory only, gone when the tab closes.

---

## What happens when the AI gets it wrong

This is the part we would most want to be asked about. All five rules are enforced in code, in
[`src/contract_trap_finder/safety.py`](src/contract_trap_finder/safety.py), not just requested in a
prompt.

| Rule | How it is enforced |
|---|---|
| **No finding without a quote** | Every quote the model returns is checked back against the original document text (`verify_quote`). Anything that cannot be found is deleted, along with the field it belongs to. A paraphrase fails this check as surely as a fabrication. |
| **No safe verdict, ever** | Absence of findings is reported as *"we did not find these problems in these documents"*, never as *"this contract is fine"*. False reassurance here costs somebody their home. |
| **Missing-document detection** | If the contract deducts rent but no housing agreement was uploaded, the tool says so. Many workers do not realise they signed three separate things, so naming the gap is itself useful output. |
| **A confidence gate** | Below threshold, or where documents contradict each other, the tool refuses to summarise and routes to a named human organisation. The gate runs *before* the composition call, so there is never a fluent wrong answer sitting next to the warning. |
| **No instruction to act** | It never says *"do not sign"* or *"quit"*. It reports what is there and who to ask. The decision stays with the person who has to live with it. |
| **Every finding routes to a person** | When the tool *does* find something, the report says above the findings that a computer did this reading, that it misses things, and that one of the listed organisations should go through the documents with the user (`safety.TALK_TO_A_HUMAN`, in all seven languages). The confidence gate covers the case where we are unsure; this covers the case where we are sure, which is the one a user is most likely to mistake for the whole truth. |

Two further properties worth knowing:

- **The model cannot overturn a legal check.** Deterministic findings are sent into step 5 with
  `DET-` ids and reconciled against the originals afterwards: the model's *wording* is kept, and the
  category, severity, quotes and rule id are restored from the code's version. A finding the model
  drops is put back; a `DET-` id the code never issued is discarded. The worst a bad composition call
  can do is phrase a finding poorly.
- **Failures degrade rather than crash.** One unreadable document does not cost the user the other
  three. A failed cross-reference step still leaves the per-document findings. A failed composition
  step returns the findings in English rather than nothing.

These behaviours are covered by tests: see `tests/test_pipeline.py`, which includes a model that
invents a clause, a model that tries to delete a legal finding, and a model that returns a verdict
the code never issued.

---

## Running it

**Requirements:** Python 3.11+ and a Gemini API key ([free key from Google AI
Studio](https://aistudio.google.com/apikey)), or, instead of the key,
[Ollama](https://ollama.com) and a model on your own machine. See
[Running it on your own machine](#running-it-on-your-own-machine).

> ### Before you import a document: take the personal details out
>
> **Delete or black out the worker's name, date of birth, BSN, address, and the name of the employer
> or agency before you add a document to this tool.** Replace them with `[removed]` if you want to
> keep the layout intact.
>
> This is not a formality. **None of the analysis uses them.** Every rule in
> `rules/legal_rules.json` is about a clause, an amount, a date or a notice period; the cross-document
> step needs to know that the employer and the landlord are *the same company*, which their
> registration numbers and addresses already say without anybody's name attached. A contract with the
> name cut out produces the same findings as one with it left in.
>
> And with the default provider, anything you leave in the text travels: see
> [the disclaimer below](#where-your-documents-go). Every bundle in `samples/` has had these fields
> removed, so they also show what a stripped document looks like.

### The short way

Clone or download the repository and **double-click `run_local.bat`** (on macOS or Linux, run
`./run_local.sh`). It creates the virtual environment, installs the requirements, and opens the app
in your browser. The first start takes a few minutes for the install; every start after that is
immediate.

It never activates the environment; it calls `.venv\Scripts\python.exe` by path, which is what
activation exists to arrange, so the `py` trap described below cannot happen. If you have no API key
yet it still starts: choose **On this computer (Ollama)** in the sidebar.

### The long way, step by step

```bash
git clone <this repo>
cd Hackathon_3
python -m venv .venv
```

**Activate the environment. This step is not optional.** On Windows PowerShell:

```bash
.venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

> **Windows note:** once activated, use `python`, **not** `py`. The `py` launcher always runs your
> system Python and ignores the virtual environment, so every command below will fail with
> `ModuleNotFoundError`. Your prompt shows `(.venv)` when the environment is active. If you forget,
> the entry points detect it and tell you what to do rather than showing a traceback.

Install and configure:

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Then open `.env` and set `GEMINI_API_KEY=...`. Check everything is wired up:

```bash
python cli.py --check-setup
```

### The web app (what the demo shows)

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. Choose a language, add documents (upload `.txt`/`.pdf` or paste
text, or load one of the example bundles), and press **Check these documents**.

### The command line

```bash
python cli.py samples/bundle_a_nl_tied_housing/01_uitzendovereenkomst.txt samples/bundle_a_nl_tied_housing/02_huisvestingsbijlage.txt samples/bundle_a_nl_tied_housing/03_machtiging_inhoudingen.txt --language pl --verbose
```

Add `--json` for the full structured report, `-o report.txt` to write to a file.

Both interfaces narrate the run as it happens, on stderr so `--json` and `-o` keep producing clean
output on stdout. A step opens, reports which document it is on, and closes with what it actually
produced:

```
  ... Reading 3 documents
      2 of 3: 02_huisvestingsbijlage.txt (2,130 characters)
  • extraction: asking qwen3:8b for StructuredDocument (~2,895 tokens of prompt, 16,384 token window)
  • qwen3:8b answered in 8.4s (2,895 tokens in / 440 out, 52 tok/s)
  • 02_huisvestingsbijlage.txt: read as housing_agreement, 3 money term(s), 1 flag(s)
  ✓ Reading 3 documents (24.1s)
```

The counts are the point. A model that returns valid but empty JSON produces a run that completes
normally and a report that is quietly thin. "3 of 3 read, 0 money terms" is what makes that visible
while it is happening rather than afterwards. The same transcript appears in the web app's status
panel, and collapses to a one-line summary when the run finishes.

`-v` prints raw log records instead, with logger names, and `-q` turns progress off entirely.

### Running it on your own machine

Both entry points can read the documents with a model running locally instead of the Gemini API.
Pick **On this computer (Ollama)** in the web app's sidebar, or pass `--provider ollama` on the
command line. Nothing is sent over the internet in that mode, which is the only honest answer to
"where do my documents go", and is worth having for a user who has been told that asking questions
about their contract will cost them the job and the room that comes with it.

It is also how to develop this tool without spending metered requests. The free Gemini tier meters
about twenty requests per key per model per day and one bundle costs several, so a day of prompt
tuning runs out of quota well before it runs out of ideas.

```bash
ollama pull qwen3:8b
```

```bash
python cli.py --check-setup --provider ollama
```

```bash
python cli.py samples/bundle_a_nl_tied_housing/*.txt --provider ollama --language en
```

#### Which model for which computer

Any model Ollama can run appears in the dropdown, so the question is what *your* machine can hold.
The rule of thumb is the one that matters: **the weights have to fit in memory the accelerator can
reach, and the context window costs more on top.** A 16k window on a 8B model is roughly another
1–2 GB, so leave headroom rather than matching the download size exactly.

Sizes below are the download at the default 4-bit quantisation, rounded. Check the current figure on
[ollama.com/library](https://ollama.com/library) before pulling, because tags get requantised.

| Your machine | Start with | ≈ download | What to expect |
|---|---|---|---|
| **No dedicated GPU** (laptop, integrated graphics, 8–16 GB RAM) | `qwen3:4b` | 2.5 GB | It runs, on the CPU, at a few tokens a second. A three-document bundle is minutes per step, not seconds. Good enough to see the pipeline work end to end; not good enough to trust a reading. Lower `CTF_OLLAMA_NUM_CTX` to `8192` if it swaps. |
| **6–8 GB VRAM** (RTX 3050/3060 laptop, RTX 4060) | `qwen3:8b` at 8k–16k context, or `gemma3:4b` | 5 GB / 3.3 GB | `qwen3:8b` fits at 4-bit with a modest window. If Ollama starts spilling into system RAM (see below), drop the context or move to the 4B. |
| **12 GB VRAM** (RTX 3060 12 GB, RTX 4070) | `qwen3:8b`, then try `gemma3:12b` | 5 GB / 8 GB | The setup this project was developed against. `gemma3:12b` is the better reader of Dutch and Polish and is the one to try when extraction is missing clauses. |
| **16–24 GB VRAM** (RTX 4080/4090, RTX 3090, A4000+) | `qwen3:14b` | 9 GB | The best of these at the two reasoning steps, with room for a 32k window. Above 24 GB, a larger model such as `gemma3:27b` (≈17 GB) fits, though it is untested here, and everything below about accuracy still applies. |
| **Apple Silicon** (M1/M2/M3/M4, unified memory) | 16 GB: `qwen3:8b` · 24 GB+: `qwen3:14b` | 5 GB / 9 GB | Unified memory means the usable budget is roughly total RAM minus what macOS and your other apps hold, so treat a 16 GB Mac as an 8–10 GB card. Metal is used automatically; no configuration. |
| **Anything smaller, or a work laptop you cannot install on** | n/a | n/a | Use the hosted provider and strip the personal details out of the documents first, or borrow a machine. A model too small to read a contract is worse than no local option, because its answers look the same as a good one's. |

A mixed setup is worth knowing about when the machine can hold a large model but not run it for
everything: `CTF_OLLAMA_MODEL=qwen3:8b` with `CTF_OLLAMA_MODEL_REASONING=qwen3:14b` uses the small
model to pull fields out of each document and the larger one for the two steps that actually reason.

**What to turn down when it does not fit.** `CTF_OLLAMA_NUM_CTX` (the window, default 16384) is the
first thing to lower and the one that costs the most memory; `CTF_MAX_CHARS_PER_DOC` caps how much of
a long document is sent at all; `CTF_OLLAMA_KEEP_ALIVE` decides whether the weights stay loaded
between the pipeline's five steps, which is the difference between one load and five on a machine
that is tight. All of them are in [`.env.example`](.env.example) with the reasoning attached.

**The honest part, and it applies to every row above.** The one local model measured against the
sample bundles, `gemma3:12b` on the 12 GB row, found **3 of 14** planted rules, against 12 of 13
for the hosted model on the bundle it was run on. Smaller models are worse than that, not better. The
rows are about what will *run*; none of them is a claim about what reads a contract well enough to
rely on, which is why every local run is reported as a degraded run and why `CTF_OLLAMA_TRUSTED` is
empty.

**Three things that will bite you.**

1. **Reports come out as lower confidence, deliberately.** A local run is treated exactly like a run
   that fell back to a `-lite` Gemini model: confidence is scaled by `CTF_DEGRADED_FACTOR` and the
   report names the model that wrote it. That is not a bug to work around: no local model has been
   checked against the sample bundles yet, and until one has, saying so is the honest position. Once
   you have checked one, name it in `CTF_OLLAMA_TRUSTED` and it stops being flagged.
2. **Context, not speed, is the limit.** Ollama does not reject a prompt that overruns the context
   window; it silently drops the front of it, which here is the contract. The client sizes every
   request and refuses rather than send a half-read document, so if you see that refusal, raise
   `CTF_OLLAMA_MAX_CTX` or lower `CTF_MAX_CHARS_PER_DOC`.
3. **Check it is actually on the GPU.** The progress output reports tokens per second for every
   call, taken from Ollama's own counters, and the two cases are an order of magnitude apart: a
   model in VRAM answers in the tens of tokens per second, one that has spilled into system memory
   in the low single digits. `ollama ps` confirms which happened. A very new card can need a recent
   Ollama build before it is used at all. If a load time is reported on *every* call rather than the
   first, the model is being evicted between steps: raise `CTF_OLLAMA_KEEP_ALIVE`.

### Where your documents go

> **Disclaimer: with the default provider, your documents are sent to Google.**
>
> Pressing **Check these documents**, or running `cli.py` without `--provider ollama`, sends the full
> text of every document you added over the internet to **Google's Gemini API** (`gemini-3.8-flash` by
> default), where it is read by a model Google runs. That includes any name, address, date of birth or
> BSN still in the text.
>
> What we can promise, because it is in the code: this tool keeps nothing. No account, no login, no
> personal details requested, documents held in memory for the session only, nothing written to disk
> except a report you ask for with `-o`, no document text or API key in any log line, Streamlit telemetry off in
> [`.streamlit/config.toml`](.streamlit/config.toml).
>
> **What we cannot promise is anything at all about what happens at Google's end.** We have not
> reviewed the data-retention terms of the API tier we use, we have no contract with Google covering
> this data, and a free developer tier is not a tier anyone should assume is private. Treat the text
> as having left your control the moment the call is made.
>
> Two ways to act on that, and the tool states both where the choice is made: strip the identifying
> fields out first ([see above](#running-it)), and for documents that must not leave the machine at
> all, pick **On this computer (Ollama)** in the sidebar or pass `--provider ollama`. The interface
> says this on the page with the button, the CLI prints it before the first call, `--check-setup`
> reports it, and [`.env.example`](.env.example) says it next to the key itself. A disclaimer only
> counts where the person is at the moment they decide.

Both modes run the interface on your own machine. The difference between them is what the three
model steps do with the text, and it is the only difference that matters here:

| Pipeline step | What it does | Hosted mode (Gemini) | Local mode (Ollama) |
|---|---|---|---|
| 1 · Ingest | Reads `.txt` and `.pdf` into memory | nothing leaves the machine | nothing leaves the machine |
| 2 · Structure | Each document becomes typed JSON | **the full text of the document** | nothing leaves the machine |
| 3 · Cross-reference | Finds links between the documents | **party names, registration numbers, addresses, money terms, and the quotes behind them** | nothing leaves the machine |
| 4 · Legal checks | Matches extractions against `rules/legal_rules.json` | nothing leaves the machine; no model is called | nothing leaves the machine |
| 5 · Compose | Writes the report in the user's language | **that same extraction, plus the findings the code established and their quotes** | nothing leaves the machine |

The right-hand column is meant literally: the local backend talks to Ollama on `localhost`, and a
run with the network disconnected produces the same report.

**The gap, stated plainly.** In hosted mode the text of somebody's employment contract reaches a
third party under terms we have not read. Asking the user to remove their own identifying details
before uploading is a real mitigation and an incomplete one: it depends on them doing it, and the
clauses themselves can still identify a small employer. A production version would strip those fields
in code before the call rather than asking. See [Risk 7 in ETHICS.md](ETHICS.md). Local mode answers
this risk rather than reassuring anyone about it, and it is not free: the accuracy cost is the first
of the three notes above.

### The sheet you can take with you

Every other output of this tool ends on a screen. The conversation it is meant to enable happens
afterwards, with a recruiter, a caseworker or an inspector, and in Dutch.

So the report also downloads as a **.docx sheet that is bilingual by construction**: every question
appears in the worker's language and in Dutch, side by side, and every clause is quoted exactly as
the contract words it. Someone who speaks no Dutch can put the page in front of a Dutch speaker and
point at a line.

In the web app it is the primary download button. From the command line:

```bash
python cli.py samples/bundle_a_nl_tied_housing/*.txt --language pl --takeaway
```

Add a path to choose the filename. No model is called to build it: `SafeQuestion` already carries
`question_in_employer_language` from step 5, and the quotes are already in the original language, so
nothing on a page designed to be handed to an employer is a sentence the pipeline has not already
grounded. A gated run leads with the refusal rather than burying it, and an unverified rule keeps
its caveat.

The fixed headings on the sheet (not the questions or findings, which come from the documents)
were translated for this tool and have only been checked for English and Dutch. The sheet says so on
itself in the other five languages.

### Measuring it against the sample bundles

```bash
python scripts/evaluate.py --provider ollama --model qwen3:8b
```

[samples/expectations.json](samples/expectations.json) records, for each bundle, which rule ids a
correct run must produce, which it must not, and how the gate should behave. `scripts/evaluate.py`
runs the real pipeline and scores it, reporting planted rules found, false positives, grounding
drops, confidence and wall-clock time per bundle. It exits non-zero on any failure, so it can be
wired into CI unchanged.

**What a score here proves, and what it does not.** The bundles were written by us, so a perfect
score means the pipeline finds what we planted in documents shaped the way it expects. It is a
regression signal and an upper bound on real-world recall, never a claim about accuracy on a real
contract, which we cannot make without labelled real contracts we do not have. See
[ETHICS.md](ETHICS.md), risk 1.

One bundle costs several model calls and the free Gemini tier meters about twenty requests per key
per model per day, so a full run against `--provider gemini` can exhaust a key. Against Ollama it
costs nothing but time.

### Seeing the output without an API key

```bash
python scripts/demo_offline.py
```

Runs the entire pipeline against a hard-coded stub instead of the model: no key, no network, no
cost. Useful for checking the output format and for seeing the grounding check discard an invented
finding on every run. It is **not** evidence that the tool works; the extraction is faked.

### Tests

```bash
python -m pytest
```

No API key needed, and nothing in them touches the network or needs Ollama installed.

---

## Repository layout

```
app.py                     Streamlit interface (the demo)
cli.py                     Command line entry point
run_local.bat              Double-click launcher for Windows: set up, then start
run_local.sh               The same, for macOS and Linux
src/contract_trap_finder/
  config.py                Models, thresholds, languages: everything tunable
  progress.py              What a run says about itself while it runs
  models.py                Pydantic schemas for every LLM boundary
  safety.py                The five guardrails. The most important file here.
  takeaway.py              The bilingual .docx sheet the worker takes away
  pipeline.py              Orchestration, and the confidence gate
  llm/
    __init__.py            build_client(): picks the backend, and the prompt loader
    client.py              The only code that calls Gemini; schema translation, retries
    ollama_client.py       The same contract, against a model on this machine
    errors.py              The failures both backends raise
    prompts/*.md           System prompts, as files rather than string literals
  steps/
    s1_ingest.py           text + PDF  (no LLM)
    s2_structure.py        document -> typed JSON  (LLM)
    s3_cross_reference.py  relationships between documents  (LLM)
    s4_legal_checks.py     ceilings, prohibitions, arithmetic  (no LLM)
    s5_compose.py          the four outputs, in the user's language  (LLM)
  rules/
    legal_rules.json       The legal rules as data, each with a verified flag
    contacts.json          Organisations to contact. Never model-generated.
samples/                   Six invented document bundles, four Dutch and two English
  README.md                What is planted in each bundle and which rule should fire
  expectations.json        What a correct run produces for each, used by evaluate.py
scripts/demo_offline.py    Full pipeline run with a stubbed model
scripts/evaluate.py        Scores a real run against samples/expectations.json
tests/                     No API key needed, and no network
docs/llm_integration.md    How the code calls the model, handles its answers, and uses the prompts
docs/decisions.md          Why the tool is built the way it is
.env.example               Every setting, with the reasoning attached
ETHICS.md                  The required ethical reflection
```

## Ethical reflection

**The biggest risk is false reassurance.** Our users cannot check the output, which is why the tool
exists, so a clause the tool misses is a clause they will sign believing a system looked and found it
fine. On the sample bundles the hosted model found **12 of 13** planted clauses in the tied-housing
bundle, and a local 12B model only **3 of 14** across the four Dutch bundles. We wrote those bundles
ourselves, so even the better figure is an upper bound, not a measure of accuracy on real contracts.
What limits the risk: a quiet result is never reported as a clean contract, missing documents are
named, an unsure run is replaced by a referral to a named organisation, and a report that does find
something says above the findings that a person should go through the documents with the user.

The full reflection, with seven further risks specific to this prototype (among them invented clauses,
retaliation against the user, unequal quality across languages, and documents sent to Google), is in
**[ETHICS.md](ETHICS.md)**.

## What we learned

### Lucas Jansze

I learned to get much more out of an LLM API, and out of its free tier in particular. Our pinned
model, `gemini-3.8-flash`, was often not responding at all, which was a big problem for a tool that
has to answer when a worker needs it. So I built the client to fail over from better models to
weaker ones when a model is overloaded, and to rotate between API keys when one has used up its
daily quota. That way the free tier went a lot further, and a run still finished on a bad day.

### Dinh Duy Lan

I discovered that a machine-learning system needs to be trustworthy, transparent, and validated
against actual data in order to be useful. Although the AI in our Contract Trap Finder is capable of
deciphering complex and multilingual contract language, legal conclusions are based on established
guidelines, and each conclusion must be connected to a precise passage from the document.
