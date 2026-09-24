# Ethical reflection

**Contract Trap Finder: AI for Good, Hackathon 3, SDG 10**

A tool meant to reduce inequality can create new ones. Eight risks specific to *this* prototype, each
with the harm it would do to our users, what the code does about it, and what we have not solved. How
each guard works is in the README under *What happens when the AI gets it wrong*; this is about the
risks, not the mechanisms.

> Alongside this: [README.md](README.md) for what the tool is and how to run it,
> [docs/decisions.md](docs/decisions.md) for why it is built this way, and
> [docs/llm_integration.md](docs/llm_integration.md) for how the code calls the model and checks what
> comes back.

---

## 1. The biggest risk: false reassurance

**The risk.** Our user cannot check our output, and that is the reason the tool exists. If the model
misses an unlawful deduction, or that the housing annex ends with the job, they cannot detect the
omission and will reasonably read a short list of findings as *"a system looked at this and it is
mostly fine"*.

**Who it harms.** They sign, travel, and find out when it is expensive: the assignment ends on a
Friday, the room must be empty by Monday. Someone who arrived with a well-founded suspicion may have it
talked down by a clean-looking report. **A false negative leaves them worse off than no tool at all**,
because it spends their one moment of leverage on unwarranted confidence.

**What we did.** A quiet result is reported as *"we did not find these specific problems in the
documents you gave us"*, never as a clean contract. Documents the bundle charges for but does not
contain are named. Below a confidence threshold, or where two documents contradict each other, the tool
refuses to summarise and routes to a named organisation, before the composition call, so no fluent
wrong summary is ever produced. And **a report that did find things now says the same about itself**:
`safety.TALK_TO_A_HUMAN` sits above the findings, in all seven languages, saying a computer did this
reading, it misses things, and a person should go through the documents with you. A correctly quoted
list of real problems is the output most likely to be mistaken for a complete one, and until this was
added nothing said otherwise.

**What we can measure.** The hosted model found **12 of 13** planted clauses in the tied-housing bundle
with no false positives; a local 12B model found **3 of 14** across the four Dutch bundles. We wrote
those bundles, so that is an upper bound on real-world recall, not an estimate of it.

**Not solved.** This makes over-reading a quiet result less likely, not a false negative less likely.
We do not know our recall on real contracts, having no labelled set of them; obtaining one via FNV or
FairWork is the most valuable next step for this project.

## 2. The tool invents a clause

A fabricated clause could have a user confront an employer about a term that does not exist, or lose a
caseworker their credibility for every case they bring afterwards.

This is the one risk we have reduced rather than disclosed: **every quote is checked against the
original document text, and anything that cannot be found is deleted with the finding built on it.** A
paraphrase fails as surely as a fabrication, and deliberately so: a quote the worker cannot find in
their own document is not evidence they can use. Discards are counted in the report.

**Not solved.** Grounding stops invention, not misinterpretation: a real quote can still carry a wrong
conclusion. Hence the next risk.

## 3. A confident wrong statement about the law

*"Your employer is taking more than the law allows"* is a claim with a number behind it, and a model
produces it identically whether or not it knows the ceiling. Wrong, it harms the worker and our standing
with the organisations we would need as partners.

So **the model is kept out of the legal conclusions entirely**. It extracts what a document says, and
plain Python decides what that means against rules held as data. It cannot overturn or invent a
verdict either. Every legal figure records which article was read in which version, and a finding resting
on an unverified entry carries a visible caveat. A check whose inputs are missing says it could not run
rather than guessing: a guessed minimum wage produces confident, specific, wrong statements about
somebody's pay.

**Not solved.** The rules are moving (the WTTA regime, scheduled amendments to Waadi art. 9a, BMLMV
art. 2a and BW 7:672), and the minimum wage goes stale every 1 January and 1 July. Nothing here keeps
the rule file current; a deployed version needs a named owner for it.

## 4. Retaliation against the user

The company that employs them also houses them, so acting on our report can cost the job, the room and
the transport in one week. **We could produce a technically correct report that gets someone evicted**,
and the people least able to absorb that are the ones with no savings, an outstanding travel advance, no
Dutch and no other address.

Three choices follow. The tool never tells anyone what to do: no "do not sign", no "quit", no "report
this". The questions it suggests are safe to ask: *"If I move to a different job later, can I stay in the
accommodation?"* is a question anyone might ask, where *"why does clause 7 tie my housing to this job?"*
reveals that somebody has been through the contract hunting for problems. And confidential advice always
precedes enforcement, ordered in code, with every contact answering *"will your employer find out?"*,
including the honest *possibly* for the Labour Authority.

**Not solved.** We cannot make acting on the information safe, only avoid pushing people into it. A
worker who reads the report and does nothing has still gained something, and the tool treats that as a
legitimate outcome.

## 5. Unequal quality across languages

This one would make us guilty of what we are trying to fix: worse Bulgarian output means a worse tool for
the Bulgarian-speaking worker, an inequality created by us and falling on the people with the fewest
alternatives.

The unevenness is stated in the interface beside the language selector rather than buried here, and
**quotes are never translated**. The explanation is in the user's language, the clause stays in the
document's, so even where our prose is poor the evidence they can show someone else is exact. Contacts
covering their language come first, and the take-away sheet admits on itself that its fixed headings are
unchecked in the five languages no native speaker has read.

**Not solved.** We have not measured the gap, so that warning is a disclosure, not a mitigation. The same
holds for *document* languages, which is why the samples now exist in English as well as Dutch: with only
Dutch bundles, a missed clause cannot be told apart from a language failure.

## 6. The tool is used against the people it is for

Nothing stops an agency running its own contracts through this and editing until the report comes back
empty. That is compliance laundering for the operators we want to expose, and every worker later handed a
*careful* contract is harder for a caseworker to help, not easier.

We did little about it that is technical and would not pretend otherwise: telling a worker from a
recruiter needs accounts and identity checks, which would destroy the no-account property that makes this
usable at a recruitment desk. What we did do is write the risk categories around *structures* (housing
tied to employment, no hours plus no other work) rather than particular wordings, which is harder to
edit around than a keyword list.

**Not solved.** A known risk of the approach, not a bug for a later sprint.

## 7. Privacy: the documents are sent to Google

Contracts carry names, addresses, dates of birth and sometimes BSN numbers, and our users have a
well-founded fear that information about them reaches their employer.

What we can promise is in the code: no account, no login, no personal details requested; documents held
in memory for the session and never written to disk; logging that records exception types and counts,
never document text or the API key; Streamlit telemetry off. The README sets out what leaves the machine
at each of the five steps, in each mode, because a claim like this is worth nothing unless it can be
checked.

**The gap, in full, because it is the real one. By default the full text of every document is sent over
the internet to Google's Gemini API to be read.** We keep nothing; what Google does with it is outside
our control, and we have not reviewed the data-retention terms of the free tier we use. For a user whose
central fear is that information about them travels, "we do not keep it, but we do send it to a third
party" is material, so the tool says it in five places rather than one: on the page with the button, in
the sidebar, before the CLI's first call, in `--check-setup`, and beside the key in `.env.example`. A
disclaimer only counts where the person is at the moment they decide.

Two things reduce it. The tool **asks the user to remove their name, date of birth, BSN, address and
employer before importing**, and can say why that costs them nothing: no rule reads those fields, so a
stripped contract produces the same findings. It is real and incomplete: it depends on the user doing
it, and a clause can still identify a small employer; doing it in code is what a production version owes
them. And the documents **can be read by a model on the user's own machine**, after which nothing leaves
it. That answers the risk instead of reassuring anyone about it, and it is not free: a model that fits on
a consumer graphics card reads a Dutch contract less accurately, so a local run is reported as degraded
with the model named. Privacy against accuracy is a genuine trade, and both sides are stated where the
choice is made.

## 8. Displacing the human it should lead to

This tool is free and instant; a union appointment is neither. If it becomes a substitute for advice
rather than a route into it, we have replaced somebody who can act on a worker's behalf with a report
that cannot.

So contacts are part of every report, including those with no findings and gated ones where we refused to
summarise; the gate routes to a person rather than to a weaker automated answer; a report with findings
opens with the line from risk 1; and every report ends by saying this is information, not legal advice,
and does not tell you whether to sign.
