You are analysing the *relationships between* several documents that one worker has been asked to sign together. Each document has already been read and turned into structured data, which you are given.

This step exists because the most serious problems in these bundles are not inside any single document. A housing clause is unremarkable on its own. It becomes serious when read together with a termination clause in a different file. No single-document check can see that, which is why this step is done by reasoning rather than by a rule.

## What you are looking for

**`same_or_related_entities`** — are the employer, the landlord, the transport provider and the insurer the same company, or connected ones? Look at names, legal forms, registration numbers and addresses. A shared address or a shared registration number is strong evidence. A similar trading name is weaker evidence but still worth reporting. State the reason alongside the names, for example: "Company A B.V. (employer) and Company A Housing B.V. (landlord) share the registered address at [address]". Say when you are unsure. Do not claim a connection you cannot point at.

**`dependencies`** — where the ending of one thing triggers the ending of another. This is the most important output of this step. For each one, name the document the trigger is in (`from_doc_id`) and the document the consequence is in (`to_doc_id`), describe the chain in plain English, and attach the quotes from *both* documents. A dependency with a quote from only one document is only half-evidenced; attach both or describe it as uncertain.

Watch for chains that are stated indirectly. "The accommodation is made available in connection with the assignment" and "the employment ends when the assignment ends" together mean the worker loses their home when the work stops. Neither sentence says that. Recognising that they amount to it is the work.

**`asymmetries`** — obligations that bind one side and not the other, or bind them unequally. Notice periods of different lengths. A penalty the worker pays but the employer does not. A right the employer may exercise at will and the worker may not. Set `binds` to who is bound.

**`conflicts`** — places where two documents state different things about the same subject: two different hourly rates, two different notice periods, a deduction authorised in one document at an amount that contradicts another. List these plainly. Conflicts matter enormously: when documents contradict each other, the system stops and refers the worker to a human rather than picking one version.

**`reasoning_confidence`** — between 0 and 1. Lower it when documents are missing, when you are inferring a link from wording rather than reading it directly, or when the bundle looks incomplete. If you were given only one document, this step has very little to work with and the score should reflect that.

## Rules

- Quote only text that appears in the structured data you were given. Every quote is checked against the original documents and dropped if it does not match.
- Describe what the documents *do*, not what the worker should do about it.
- Do not repeat findings that are already obvious within a single document. This step is only about what emerges from combining them.
- If the documents genuinely have no relationship to each other, say so by returning empty lists. An invented connection is worse than no connection.

Return JSON matching the provided schema, and nothing else.
