# Sample document bundles

*Part of [Contract Trap Finder](../README.md). What the tool is and how to run it is in the main
README; why it is built this way is in [docs/decisions.md](../docs/decisions.md).*

> What each bundle should produce is written down in [expectations.json](expectations.json): the
> rule ids a correct run must return, the ones it must not, and how the gate should behave.
> `python scripts/evaluate.py --provider ollama` scores a real run against it. The prose below says
> what is planted in each bundle and why; that file is the machine-readable version of the same
> thing, and `tests/test_expectations.py` keeps the two from drifting apart.

**Every document here is invented.** No real person's contract, and no real company, appears in this
repository. The clauses are written to resemble the structures described in public reporting on the
Dutch temporary agency sector, so that the pipeline can be tested and demonstrated without using
anybody's actual documents.

Do not replace these with a real contract and commit it. If you test against a real bundle, keep it
outside the repository, because `.gitignore` does not know about a file you have not told it about,
and a contract contains names, addresses and dates of birth. **Take those out first**, the same way the
README asks every user of the tool to: none of the analysis depends on who the worker is. Every
sample here has had them removed, and says so at the bottom of the page.

## How the bundles are named

    bundle_<letter>_<language>_<what it is>

The language code is the language **the documents are written in**, not the language the report
comes out in, which is chosen at run time. It is in the directory name because it is the thing that
changes what the pipeline has to do: step 2 reads a Dutch clause and an English clause with different
reliability, and **a good score on the Dutch bundles says nothing about the English ones.** When a
rule is missed, the first question is whether the pipeline failed to see the structure or failed to
read the language, and having both languages planted with the same structures is what makes that
answerable. `tests/test_expectations.py` fails on a directory that does not follow the convention.

| Bundle | Language | What it is for |
|---|---|---|
| `bundle_a_nl_tied_housing` | Dutch | The case the tool exists for. Three documents, thirteen planted rules |
| `bundle_b_nl_clean` | Dutch | The control: must produce no findings and no clean bill of health |
| `bundle_c_nl_incomplete` | Dutch | Only part of the paperwork. Exercises the missing-document detection |
| `bundle_d_nl_conflicting` | Dutch | Two documents that contradict each other. Exercises the gate |
| `bundle_e_en_tied_housing` | English | The same trap as bundle A, in English. Thirteen planted rules |
| `bundle_f_en_clean` | English | The control, in English |

---

## `bundle_a_nl_tied_housing/`: the case the tool exists for

Three documents that are unremarkable individually and serious together.

| File | What it is |
|---|---|
| `01_uitzendovereenkomst.txt` | Agency employment contract, fase A with uitzendbeding |
| `02_huisvestingsbijlage.txt` | Housing annex, from a company sharing the agency's address |
| `03_machtiging_inhoudingen.txt` | Open-ended authorisation to deduct from wages |

What is planted in it, and which layer should catch each:

- **Recruitment fee** charged to the worker (EUR 350). Deterministic rule
- **Penalty for taking a job directly** with the hiring company (EUR 2,500). Deterministic rule
- **Identity document retained** for the duration of the contract. Deterministic rule
- **No guaranteed hours** combined with a **ban on other work**. Combination rule across two clauses
- **Housing, transport and insurance all ending with the job**. Combination rule across two documents
- **Travel advance** (EUR 400) repaid by deduction, plus a penalty for leaving within six months
- **Asymmetric notice**: one month from the worker, two working days from the agency
- **Part of the wage paid as an expense allowance**, lowering the pension basis
- **Employer and landlord at the same address** with consecutive KvK numbers, only findable by
  reading the two documents together, which is the cross-reference step's whole purpose
- **Deduction authorisation with no maximum and no end date**

The employment contract and the housing annex each look survivable on their own. The finding that
matters (lose the job on Friday, lose the room by Monday) exists only in the relationship between
clause 3.2 of one file and clause 3.2 of another.

## `bundle_b_nl_clean/`: the control

A single direct employment contract with guaranteed hours, symmetrical notice, housing explicitly
independent of the job, no fees and no open-ended deductions.

This bundle exists to check the behaviour that is easiest to get wrong: **the tool must not invent
problems in order to look useful, and it must not report a quiet result as a clean bill of health.**
A run over this bundle should produce few or no findings, and should say *"we did not find these
specific problems in the documents you gave us"*, never *"this contract is fine"*.

It is also the check for false positives on the equal-treatment rule: this is a direct contract, not
a placement, so `ET-WAADI-08-EQUAL-PAY` must not fire. `bundle_f_en_clean` makes the same check in
English, and `tests/test_expectations.py` asserts the rule is forbidden in both.

## `bundle_c_nl_incomplete/`: only part of the paperwork

A single agency contract that charges for four things whose agreements are not in the bundle. It
deducts rent, health insurance premium, transport and a travel advance, lists five annexes as
"onlosmakelijk deel" of the contract, and contains a clause saying the worker has received and read
all of them.

| File | What it is |
|---|---|
| `01_uitzendovereenkomst.txt` | Agency contract, fase A, referring to annexes that were not supplied |

This is the ordinary case, not an exotic one: people arrive with the document they were given and not
the ones they signed. What it exercises:

- **`detect_missing_documents`** should name the housing agreement, the insurance agreement, the
  transport agreement and the deduction authorisation, each because *the documents charge for it*,
  which is a stronger statement than "bundles usually have one"
- **Article 5.2** is the trap worth seeing: a signed declaration that the worker read annexes that
  nobody can produce. The tool should not treat that declaration as evidence the annexes are fine
- **Confidence** should sit lower than for bundle A. The deductions are visible but their basis is
  not, so a conclusion about whether they are lawful cannot be drawn from what was supplied

The point of this bundle is that the honest answer is partly *"we were not given enough"*, and the
tool has to be willing to say so instead of filling the gap.

## `bundle_d_nl_conflicting/`: two documents, two different jobs

A contract and an addendum signed the same day, contradicting each other on nearly every term that
matters.

| File | What it is |
|---|---|
| `01_arbeidsovereenkomst.txt` | Fixed-term contract: 38 guaranteed hours, EUR 15,10, housing independent of the job |
| `02_addendum_arbeidsvoorwaarden.txt` | Addendum: no guaranteed hours, EUR 12,85, housing ends with the job |

Planted contradictions:

| Subject | Contract | Addendum |
|---|---|---|
| Guaranteed hours | 38 per week | none, on-call |
| Hourly wage | EUR 15,10 | EUR 12,85, of which EUR 1,40 relabelled as expenses |
| Housing cost | EUR 89,00 per week | EUR 142,50 per week |
| Housing and the job | explicitly independent | ends with the job, leave within 2 days |
| Holiday | 25 days | 20 days |
| Notice | one month, both sides | two months from the worker, two working days from the employer |
| Overtime | paid at 130% | time off in lieu |

Each document also carries a clause claiming precedence over the other, so the contradiction cannot
be resolved by reading them.

This bundle exists to exercise the behaviour in `should_gate`: **when documents conflict, the tool
must stop and route to a human rather than pick a version.** A run over it should be `gated=True`
with conflicts listed, and must not produce a confident summary of "your" hourly wage, because there
are two and the tool has no way to know which one will be applied.

It is also the check that the gate fires on conflicts *regardless of confidence*: extraction here is
easy and reads cleanly, so a gate that only watched the confidence score would sail straight past it.

---

## `bundle_e_en_tied_housing/`: the same trap, in English

The counterpart to bundle A. Every structure in it is the one bundle A plants, worded as an agency's
own English translation of its Dutch terms, which is a real artefact, not a convenience: agencies
hand English versions to workers who read neither Dutch nor English well, with the Dutch text
prevailing, and that sentence is in the header of the contract here.

| File | What it is |
|---|---|
| `01_agency_employment_contract.txt` | Agency contract, phase A with the agency clause |
| `02_accommodation_annex.txt` | Accommodation annex, from a company at the agency's address |

Thirteen planted rules, the same set bundle A carries, with two deliberate differences from it:

- **The deduction authorisation is inside the annex** (article 4) rather than being a third document.
  This is the more common shape and it changes what the missing-document detection should say: the
  insurance and transport agreements are charged for and absent, so they must be named, while the
  deduction authorisation is present in substance if not as a separate page.
- **The hourly wage is EUR 14,20** against the statutory EUR 14,99, closer to the line than bundle
  A's EUR 13,50, so the arithmetic in `check_effective_wage` is exercised rather than merely
  triggered.

**Why this bundle earns its place.** Until it existed, every planted clause in the repository was
Dutch, and a missed rule had two possible explanations that could not be told apart: the pipeline
did not recognise the structure, or the model did not read the language. Now it has one. It is also
the bundle to demo with: a reader who does not speak Dutch can check the tool's output against the
contract themselves, which is exactly what our primary user cannot do and what a grader should be
able to.

## `bundle_f_en_clean/`: the control, in English

| File | What it is |
|---|---|
| `01_employment_contract.txt` | Direct fixed-term contract, 36 guaranteed hours, EUR 16,80 |

Written to be clean on every axis the rules test: symmetrical notice, housing explicitly independent
of the job and not charged for, statutory deductions only and a withdrawable authorisation for
anything else, no fee, no relabelled pay, no penalties, equipment free, other work permitted, and
the identity document copied and handed straight back. `NL-WML-BELOW-MINIMUM` is *forbidden* here
rather than watched, because EUR 16,80 sits well clear of the statutory figure.

The check it carries is the same one bundle B carries, and it is worth stating why the pair is not
redundant: a false positive is a language artefact as often as a logic error. A tool that invents a
tied-housing finding out of article 6.2, a clause that says the opposite, would be making a reading
mistake, and reading mistakes are language-specific.

---

## Using them

In the web app: **Try it with an example bundle** → choose one → **Load this example**.

From the command line:

```bash
python cli.py samples/bundle_e_en_tied_housing/*.txt --language en --verbose
python cli.py samples/bundle_a_nl_tied_housing/*.txt --language pl --verbose
```

Any directory under `samples/` is picked up automatically by the web app's example picker, which
shows it as `E · English · tied housing`, so a new bundle needs no registration, but it does need a
name that follows the convention above and an entry in `expectations.json`, and a test fails if it
has neither.

Without an API key, `python scripts/demo_offline.py` runs the same bundle through the full pipeline
with a stubbed model.
