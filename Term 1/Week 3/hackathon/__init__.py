"""Contract Trap Finder — SDG 10 (Reduced Inequalities), targets 10.3 and 10.7.

Reads a bundle of documents a labour migrant is asked to sign and reports, before
they commit: what is unlawful, what is lawful but shifts every risk onto them, and
where they are offered less than the equal-treatment norm already promises.

The package is deliberately split so that it is always clear which parts are the
model's judgement and which parts are deterministic law:

    steps.s1_ingest          plain Python   — text and PDF into raw documents
    steps.s2_structure       LLM            — raw text into typed JSON, quote-anchored
    steps.s3_cross_reference LLM            — relationships *between* documents
    steps.s4_legal_checks    plain Python   — ceilings, prohibitions, arithmetic
    steps.s5_compose         LLM            — the four outputs, in the user's language

`safety` sits between all of them and enforces the rules from the brief: no finding
without a verbatim quote, no safe verdict, name the missing documents, gate on low
confidence.
"""

__version__ = "0.1.0"
