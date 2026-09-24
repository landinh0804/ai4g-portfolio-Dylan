# How the Python code talks to the model

This document is for a reader who wants to follow one request from the moment a worker presses
**Check these documents** to the moment a validated answer is used in the report. It covers three
questions: how the code calls the Gemini API and handles what comes back, how the system prompts are
used, and what "session" means in this tool.

The rest of the documentation: [README.md](../README.md) for what the tool does and how to run it,
[docs/decisions.md](decisions.md) for why it is built this way, and [ETHICS.md](../ETHICS.md) for the
risks.

---

## The short version

The model is called from **three places** in the pipeline: once per document in step 2, then once
in step 3 and once in step 5, so a three-document bundle costs five calls. Every one of those calls goes through the same method,
`generate_json(...)`, and every one of them:

1. sends a **system prompt** read from a Markdown file, plus a **user prompt** built in Python that
   carries this run's data between `BEGIN` / `END` markers;
2. tells the API the **exact JSON shape** the answer must have, generated from a Pydantic model;
3. turns the answer into a **typed Python object**, or raises an exception; no step ever sees raw
   model text;
4. hands that object to [`safety.py`](../src/contract_trap_finder/safety.py), which checks every
   quote in it against the original documents and deletes anything it cannot find.

```
 worker's documents (text / PDF)
        │
        ▼
 step 1  s1_ingest.py            plain text in memory                       no model
        │
        ▼
 step 2  s2_structure.py  ──►  generate_json(structure.md, StructuredDocument)   one call per document
        │                        └► safety.ground_structured_document()
        ▼
 step 3  s3_cross_reference.py ► generate_json(cross_reference.md, CrossReferenceResult)
        │                        └► _ground()  (same quote check)
        ▼
 step 4  s4_legal_checks.py      rules/legal_rules.json, plain Python         no model
        │
        ▼
 gate    safety.should_gate()    too unsure, or documents contradict? stop here, refer to a person
        │
        ▼
 step 5  s5_compose.py    ──►  generate_json(compose.md, ComposedOutput)
        │                        └► _reconcile_findings() + safety.ground_findings()
        ▼
 Report  (a Pydantic object)  ─►  Streamlit page, CLI text, --json, or the .docx sheet
```

The orchestration is in [`pipeline.py`](../src/contract_trap_finder/pipeline.py), function
`analyse`. It is about 180 lines and reads top to bottom in the order above.

---

## The three calls

| Step | Where the call is made | System prompt | User prompt built by | Answer must fit | Temperature |
|---|---|---|---|---|---|
| 2 · Structure | [`s2_structure.py:52`](../src/contract_trap_finder/steps/s2_structure.py) | [`structure.md`](../src/contract_trap_finder/llm/prompts/structure.md) | `_build_prompt` ([`s2_structure.py:32`](../src/contract_trap_finder/steps/s2_structure.py)): document id, filename, full text | `StructuredDocument` | 0.0 |
| 3 · Cross-reference | [`s3_cross_reference.py:108`](../src/contract_trap_finder/steps/s3_cross_reference.py) | [`cross_reference.md`](../src/contract_trap_finder/llm/prompts/cross_reference.md) | inline at [`s3_cross_reference.py:97`](../src/contract_trap_finder/steps/s3_cross_reference.py): step 2's output for every document, as JSON | `CrossReferenceResult` | 0.1 |
| 5 · Compose | [`s5_compose.py:96`](../src/contract_trap_finder/steps/s5_compose.py) | [`compose.md`](../src/contract_trap_finder/llm/prompts/compose.md) | `_build_prompt` ([`s5_compose.py:41`](../src/contract_trap_finder/steps/s5_compose.py)): step 2 and 3 output, step 4's findings, the target language | `ComposedOutput` | 0.3 |

The schemas are all in [`models.py`](../src/contract_trap_finder/models.py). The temperatures are in
[`config.py`](../src/contract_trap_finder/config.py): zero for extraction, because copying text is not
a creative task, and a little higher only for the step that writes sentences for a person to read.

Each call names a **role** (`extraction`, `reasoning` or `compose`) rather than a model id. The client
maps the role to a model (`gemini-3.8-flash` by default for all three, set in `config.py`), so the
steps do not change when the model does.

---

## One call, step by step

### 1. Getting a client

The API key is read from `.env` by `python-dotenv` when `config.py` is imported, and collected by
`config.get_api_keys()`. More than one key can be given (`GEMINI_API_KEY`, `GEMINI_API_KEY_2`, ...);
why that helps is under [When the API says no](#when-the-api-says-no).

A client is built by [`build_client()`](../src/contract_trap_finder/llm/__init__.py) (`llm/__init__.py:86`),
which returns a `GeminiClient` by default, or an `OllamaClient` when the user picked the local option.
Both satisfy the same small `LLMClient` protocol, so the pipeline never checks which one it has.
[`app.py:606`](../app.py) and [`cli.py`](../src/contract_trap_finder/cli.py) each build one client per
run.

### 2. Making the request

This is [`GeminiClient.generate_json`](../src/contract_trap_finder/llm/client.py)
(`llm/client.py:257`), shortened to the lines that matter:

```python
from google.genai import types

model_id = model or self.model_for(role)
response_schema = schema_for(schema_model)          # Pydantic model -> JSON schema Gemini accepts

config = types.GenerateContentConfig(
    temperature=temperature,
    response_mime_type="application/json",          # answer in JSON, not prose
    response_json_schema=response_schema,           # ...and in exactly this shape
    system_instruction=system_instruction,          # the Markdown prompt file
)

response = genai_client.models.generate_content(    # the live API call (client.py:369)
    model=model_id,
    contents=prompt,                                # the user prompt built by the step
    config=config,
)
raw_text = response.text
```

Three details worth knowing:

- **The schema is generated, not written by hand.** Pydantic produces a JSON schema from the model
  class, and `sanitise_schema` (`client.py:75`) rewrites it into the dialect Gemini accepts: `$ref`
  references are inlined, unsupported keywords are removed, and `X | None` becomes `nullable`. One
  class in `models.py` is therefore both the instruction to the model and the validator of its answer.
- **The request has a deadline.** `types.HttpOptions(timeout=...)` is set when the SDK client is
  built (`client.py:251`). Without it, a model that stops answering hangs the run with no error.
- **The SDK's own retries are switched off** (`HttpRetryOptions(attempts=1)`), so that there is one
  retry policy, ours, rather than two multiplying each other.

### 3. Handling the response

What happens to `raw_text`, in order (`client.py:314` onwards):

1. **Empty answer:** raise `LLMInvalidOutput`.
2. **Parse and validate:** `schema_model.model_validate_json(raw_text)`. If this succeeds, the
   caller gets a typed object such as a `StructuredDocument`, with every field type-checked.
3. **One repair attempt:** if validation fails, the usual cause is an answer cut off mid-JSON.
   `_try_repair_json` (`client.py:670`) strips a code fence if there is one and closes any brackets
   left open. It never invents a value. If the repaired JSON validates, it is used.
4. **Otherwise, fail loudly:** raise `LLMInvalidOutput` with the number of validation errors. A
   malformed answer never becomes part of a report.

A valid answer is not yet a trusted one. The step that asked for it then runs the grounding check:

5. **Every quote is looked up in the original text.** `safety.verify_quote` folds away case, whitespace,
   quote-mark and dash variants and requires a 0.90 match against the document the quote claims to come from
   (reasoning in [decisions.md](decisions.md#grounding-threshold-at-090-not-10)). A field whose quote
   fails is deleted together with the quote. In step 2 that is `safety.ground_structured_document`, in
   step 3 `_ground`, in step 5 `_reconcile_findings` and `safety.ground_findings`.
6. **In step 5, the model cannot change a legal finding.** Findings from step 4 are sent to the model
   with `DET-` ids. Afterwards `_reconcile_findings` (`s5_compose.py:130`) keeps only the model's
   *wording* for those and restores the category, severity, quotes and rule id from the code's
   version. A finding the model left out is put back; a `DET-` id the code never issued is deleted.

### 4. What the pipeline does when a call fails

`generate_json` raises one of two exceptions (from
[`llm/errors.py`](../src/contract_trap_finder/llm/errors.py)): `LLMUnavailable` when nothing
answered, `LLMInvalidOutput` when something answered badly. Each step decides what that failure costs:

| Step fails | What the user gets instead |
|---|---|
| Step 2, for one document | The other documents are still analysed; the report names the document it could not read. |
| Step 2, for every document | No analysis, a clear message, and the list of organisations to contact. |
| Step 3 | Each document is covered on its own; the report says the comparison did not complete. |
| Step 5 | Step 4's findings in English, without the timeline or questions; the report says why. |

---

## When the API says no

The free Gemini tier limits requests per key, per model, per day, and in testing the models were often
overloaded. `_call_with_retries` (`client.py:400`) decides what to do from the HTTP status, because
the fix is different for each:

| Status | What it means | What the code does |
|---|---|---|
| 429 `RESOURCE_EXHAUSTED` | This key has used today's quota for this model | Try the next key on the same model |
| 503 / 504 / 404 | This model is overloaded, hanging, or retired | Try the next model in `config.MODEL_FALLBACKS` |
| 500 `INTERNAL` | A one-off server fault | Retry the same request, with exponential backoff |
| 401 / 403, or "API key not valid" | This key is broken | Drop the key for this run and carry on with the others |
| 400 | The request itself is wrong | Stop, and show the real error |

**The fallback list runs from better models to worse ones.** The pinned model, `gemini-3.8-flash`, is
always tried first. After it come older Flash models (`3.7`, `3.6`, `3.5`, `3-flash-preview`), and last
the two `-lite` models, which are the weakest readers of a contract but are often still answering when
the Flash models are not. Having several models in the list also stretches the free tier, because
Google meters the daily quota per model: every extra model is an extra allowance. The same goes for
keys, since the quota is also metered per key, so a second key in `.env` doubles what a day can do. Once
a model and key have answered, the rest of the run starts with them, instead of every step waiting on
the same dead model again. The list is set in `config.py` and can be changed with
`CTF_MODEL_FALLBACKS` in `.env`.

The model that actually answered is recorded in `last_model_used` and shown in the report. If it was a
`-lite` model, which reads contracts noticeably worse, the run counts as **degraded**: `pipeline.py`
lowers the confidence score, which can push the report under the gate and send the user to a person
instead.

---

## System prompts

The three system prompts are Markdown files, not strings in the code:

| File | Used in | What it tells the model |
|---|---|---|
| [`structure.md`](../src/contract_trap_finder/llm/prompts/structure.md) | Step 2 | Extract parties, money terms, hours, termination conditions and 15 factual flags from one document. Every field must carry a quote copied character for character. Answer factual questions about the text, never whether something is lawful. |
| [`cross_reference.md`](../src/contract_trap_finder/llm/prompts/cross_reference.md) | Step 3 | Look across the documents for the same company in different roles, for one ending that triggers another, for obligations binding one side only, and for contradictions. Quote both documents for each dependency. |
| [`compose.md`](../src/contract_trap_finder/llm/prompts/compose.md) | Step 5 | Write the findings, the exit timeline and the safe questions in the user's language, for someone reading on a phone. Keep `DET-` findings as given. Never tell the user what to do, never say the contract is fine, never invent a quote. |

**How they are loaded.** `load_prompt(name)` (`llm/__init__.py:104`) reads
`llm/prompts/<name>.md` and caches it for the life of the process.

**How they are sent.** The system prompt and the user prompt go to the model separately:

- Gemini: as `system_instruction` in `GenerateContentConfig`, with the user prompt as `contents`.
- Ollama: as a message with `"role": "system"`, followed by one with `"role": "user"`.

**What goes where.** The system prompt holds everything that is the same on every run: the model's
job, the rules, and what a bad answer looks like. The user prompt holds only this run's data, fenced
between markers such as `--- BEGIN DOCUMENT TEXT ---` and `--- END DOCUMENT TEXT ---`, followed by a
one-line instruction. Keeping the two apart means the rules are never mixed into contract text, and
a sentence inside a contract is presented to the model as data to be read.

**Prompts are not the safety mechanism.** Every rule a prompt states that matters for the user is
also enforced in code: the prompt asks for exact quotes and `safety.py` deletes the inexact ones; the
prompt says not to re-decide `DET-` findings and `_reconcile_findings` restores them; the prompt says
never to tell the user to act and `safety.find_instruction_language` flags it when it happens. The
prompt makes a good answer likely. The code makes a bad one harmless.

**Why files.** A change to a prompt shows up as a readable diff, and the person tuning the wording does
not have to edit Python to do it.

---

## Sessions: what is remembered, and where

### The model remembers nothing

There is **no conversation history** in this tool. Each `generate_json` call is one independent
request: one system prompt and one user message. The model in step 5 has never seen the messages sent
in step 2. There is no chat object, no message list that grows, and no conversation id.

State is carried between steps **by Python**, not by the model. Each step returns a Pydantic object,
and the next step serialises what it needs into its own prompt:

| From | To | What is passed on |
|---|---|---|
| Step 2 | Step 3 | For each document: parties, money terms, termination conditions, flags, each with its quote (`_summarise_for_reasoning`) |
| Steps 2, 3, 4 | Step 5 | The same summaries, the cross-document result, and the code's findings with their `DET-` ids |

This was chosen on purpose:

- **Only checked data moves forward.** Everything passed to step 3 has already been through the quote
  check. With a chat history, an invented clause deleted after step 2 would still be sitting in the
  conversation for step 5 to repeat.
- **Each step can be tested on its own.** The tests in `tests/` feed a step a fixed input and check its
  output, without replaying a conversation.
- **Smaller prompts.** Step 3 receives a compact JSON summary, not the full text of every document.
- **Nothing to leak between users.** No conversation survives the run, so nothing from one worker's
  contract can surface in another's.

### What is kept, and for how long

| What | Where | How long |
|---|---|---|
| The uploaded documents, the finished report, the chosen language, provider and model | Streamlit's `st.session_state` ([`app.py:77`](../app.py)), in server memory, per browser tab | Until the tab is closed or the server stops. Never written to disk. |
| Which model and which API key last worked; which keys are broken or out of quota | The `GeminiClient` object built for the run | One run. The next press of the button builds a fresh client, so the preferred model always gets another chance. |
| The three system prompts | `load_prompt`'s cache | The life of the process. |
| The list of locally installed Ollama models | `st.cache_data(ttl=20)` in `app.py` | 20 seconds. |
| The local model's weights (Ollama only) | Ollama's `keep_alive` setting, default 10 minutes | Keeps the model loaded between the steps of a run. It keeps the weights in memory, not a conversation. |

Why the client remembers the working model for the length of a run: when the first-choice model is
down, every step would otherwise rediscover that on its own, waiting for a timeout each time. During one
outage that rediscovery was measured at 111 seconds for a single call.

Nothing is written to disk except a report the user explicitly asks for (`-o` on the command line, or
the download button). Log lines record exception types and counts, never document text and never the
API key.

---

## The same contract, on your own machine

[`OllamaClient.generate_json`](../src/contract_trap_finder/llm/ollama_client.py)
(`ollama_client.py:248`) does the same job over plain HTTP with `requests`, against Ollama on
`localhost`:

```python
payload = {
    "model": model_id,
    "messages": [
        {"role": "system", "content": system_instruction},   # the same Markdown prompt
        {"role": "user", "content": prompt},                 # the same user prompt
    ],
    "format": schema_for_ollama(schema_model),               # the same Pydantic schema
    "stream": False,
    "keep_alive": config.OLLAMA_KEEP_ALIVE,
    "options": {"temperature": temperature, "num_ctx": ...},
}
response = session.post(f"{host}/api/chat", json=payload, timeout=...)
```

The answer then goes through the same validate, repair, or raise sequence. One difference matters:
Ollama does not reject a prompt that is too long for the model's context window. It silently drops
the start of it, which here is the contract. `_context_for` therefore measures each prompt first and
refuses to send one that will not fit.

---

## Seeing it for yourself

- `python cli.py samples/bundle_a_nl_tied_housing/*.txt --verbose` prints every model call as it
  happens: which step, which model, which schema, how many tokens went in and out, and how long it took.
- `python scripts/demo_offline.py` runs the whole pipeline against a fake model that returns fixed
  JSON, including one invented clause, so you can watch the quote check delete it without an API key.
- `tests/test_llm_failover.py` covers the status-code table above; `tests/test_pipeline.py` covers a
  model that invents a clause, one that deletes a legal finding and one that invents a verdict.
