"""The five pipeline steps, in order.

    s1_ingest          plain Python   text and PDF into raw documents
    s2_structure       LLM            raw text into typed JSON, quote-anchored
    s3_cross_reference LLM            relationships between documents
    s4_legal_checks    plain Python   ceilings, prohibitions, arithmetic
    s5_compose         LLM            the four outputs, in the user's language

The split is the point. Steps 2, 3 and 5 are interpretation, which is what a model
is good at. Step 4 is law and arithmetic, which must be correct rather than
plausible, so the model is kept out of it entirely.
"""
