"""Presentation for the Streamlit interface: the stylesheet and the card renderers.

Kept out of `app.py` so that file stays a readable description of the page order.

Three things drive every choice here, in this order:

1. **Legibility over decoration.** The reader is often working in their third or
   fourth language, on a phone, possibly at the kitchen table of the house the
   contract is about. Long measure, generous line height, real type sizes. Nothing
   is styled to look impressive at the cost of being read.

2. **Never colour alone.** Every severity and every category carries a word as well
   as a colour. A red card that only means something if you can see red is useless
   to a colour-blind reader and meaningless in a screenshot printed in black and
   white, which is how these get passed around.

3. **Sober, not alarming.** This tool tells people that a contract they may have
   already signed is against the law. The visual language is a serious document,
   not a dashboard: no gauges, no score, no celebration when nothing is found.

Everything that reaches HTML goes through `esc()`. The text being rendered comes
from uploaded documents and from a language model, so it is never trusted markup.
"""

from __future__ import annotations

from html import escape

# --- Palette ---------------------------------------------------------------
# Contrast checked against the page background for body text and against white for
# text on a filled chip. The three category colours are also distinguishable under
# the common forms of colour blindness, which is why they are red / amber / blue
# rather than red / amber / green.

CATEGORY_COLOURS = {
    "ILLEGAL": "#B3121B",
    "RISK_SHIFT": "#A2570A",
    "BELOW_EQUAL_TREATMENT": "#1D4ED8",
}

SEVERITY_WORDS = {
    "high": "Serious",
    "medium": "Worth knowing",
    "low": "Minor",
}

STYLESHEET = """
<style>
:root {
  --ctf-ink:        #16161A;
  --ctf-ink-soft:   #4A4A55;
  --ctf-ink-faint:  #75757F;
  --ctf-page:       #FBFAF8;
  --ctf-card:       #FFFFFF;
  --ctf-line:       #E4E1DC;
  --ctf-brand:      #DD1367;
  --ctf-illegal:    #B3121B;
  --ctf-risk:       #A2570A;
  --ctf-below:      #1D4ED8;
  --ctf-radius:     10px;
}

/* Comfortable measure. Streamlit's default is wide enough to hurt on a laptop
   and the content here is all prose. */
.block-container {
  max-width: 46rem;
  padding-top: 2.2rem;
  padding-bottom: 5rem;
}

/* Scoped to the app shell rather than to every st- class. A blanket
   [class*="st-"] rule also captures Streamlit's Material icon spans, whose glyphs
   come from a ligature font - override that and every icon in the chrome renders
   as its literal name, e.g. "double_arrow_right" where the sidebar toggle should
   be. The icon selectors below put that font back for anything that needs it. */
.stApp, .stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp label, .stApp button, .stApp input, .stApp textarea, .stApp select {
  font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
}

[data-testid="stIconMaterial"],
.material-symbols-rounded,
.material-icons,
span[class*="material-symbols"],
[data-testid="stExpanderIcon"] {
  font-family: "Material Symbols Rounded", "Material Icons" !important;
}

.stApp { background: var(--ctf-page); }

/* Body copy: bigger and looser than the default, for the reason in the docstring. */
.block-container p, .block-container li {
  font-size: 1.02rem;
  line-height: 1.65;
  color: var(--ctf-ink);
}

/* --- Masthead --- */
.ctf-masthead {
  border-bottom: 3px solid var(--ctf-ink);
  padding-bottom: 1rem;
  margin-bottom: 1.6rem;
}
.ctf-masthead h1 {
  font-size: 2.1rem;
  font-weight: 800;
  letter-spacing: -0.021em;
  line-height: 1.12;
  margin: 0 0 0.45rem 0;
  color: var(--ctf-ink);
}
.ctf-masthead .ctf-standfirst {
  font-size: 1.06rem;
  line-height: 1.55;
  color: var(--ctf-ink-soft);
  margin: 0;
  max-width: 34rem;
}
.ctf-eyebrow {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: var(--ctf-brand);
  margin: 0 0 0.5rem 0;
}

/* --- Step headings --- */
.ctf-step {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  margin: 2.2rem 0 0.35rem 0;
}
.ctf-step-n {
  flex: 0 0 auto;
  width: 1.65rem;
  height: 1.65rem;
  border-radius: 50%;
  background: var(--ctf-ink);
  color: #fff;
  font-size: 0.85rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ctf-step-t {
  font-size: 1.18rem;
  font-weight: 700;
  color: var(--ctf-ink);
  letter-spacing: -0.011em;
}

/* --- At a glance --- */
.ctf-glance { display: flex; flex-wrap: wrap; gap: 0.6rem; margin: 0.4rem 0 1.4rem 0; }
.ctf-tile {
  flex: 1 1 8.5rem;
  border: 1px solid var(--ctf-line);
  border-top: 4px solid var(--tile-accent, var(--ctf-ink));
  border-radius: var(--ctf-radius);
  background: var(--ctf-card);
  padding: 0.8rem 0.9rem;
}
.ctf-tile .n {
  font-size: 1.8rem;
  font-weight: 800;
  line-height: 1;
  color: var(--tile-accent, var(--ctf-ink));
  font-variant-numeric: tabular-nums;
}
.ctf-tile .l {
  font-size: 0.83rem;
  line-height: 1.35;
  color: var(--ctf-ink-soft);
  margin-top: 0.35rem;
}

/* --- Finding cards --- */
.ctf-cat { margin: 2rem 0 0.2rem 0; }
.ctf-cat h3 {
  font-size: 1.18rem;
  font-weight: 750;
  margin: 0;
  color: var(--cat-accent, var(--ctf-ink));
  letter-spacing: -0.011em;
}
.ctf-cat p {
  font-size: 0.92rem !important;
  color: var(--ctf-ink-soft) !important;
  margin: 0.3rem 0 0 0;
  line-height: 1.5 !important;
}

.ctf-card {
  background: var(--ctf-card);
  border: 1px solid var(--ctf-line);
  border-left: 5px solid var(--card-accent, var(--ctf-ink));
  border-radius: var(--ctf-radius);
  padding: 1rem 1.15rem;
  margin: 0.85rem 0;
}
.ctf-card .ctf-flag {
  display: inline-block;
  font-size: 0.68rem;
  font-weight: 750;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: #fff;
  background: var(--card-accent, var(--ctf-ink));
  border-radius: 3px;
  padding: 0.16rem 0.45rem;
  margin-bottom: 0.55rem;
}
/* A div, not an <h4>: Streamlit rewrites heading tags into its own heading widget
   with an anchor link and its own margins, which is not wanted inside a card. */
.ctf-card .ctf-title {
  font-size: 1.07rem;
  font-weight: 700;
  margin: 0 0 0.4rem 0;
  color: var(--ctf-ink);
  line-height: 1.35;
}
.ctf-card .ctf-body { font-size: 1rem; line-height: 1.6; color: var(--ctf-ink); margin: 0; }

.ctf-quote {
  border-left: 2px solid var(--ctf-line);
  margin: 0.8rem 0 0 0;
  padding: 0.1rem 0 0.1rem 0.8rem;
}
.ctf-card .ctf-quote .src {
  font-size: 0.76rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ctf-ink-faint);
  margin: 0 0 0.2rem 0;
}
.ctf-card .ctf-quote blockquote {
  font-size: 0.95rem;
  line-height: 1.55;
  color: var(--ctf-ink-soft);
  font-style: italic;
  margin: 0;
}
/* Qualified by .ctf-card so it beats the `.block-container p` colour rule above,
   which is one specificity point higher than a bare class and would otherwise
   repaint this warning in ordinary body ink. */
.ctf-card .ctf-unverified {
  margin-top: 0.7rem;
  font-size: 0.83rem;
  color: var(--ctf-risk);
  line-height: 1.45;
}

/* --- Timeline --- */
.ctf-event {
  position: relative;
  padding: 0 0 1.1rem 1.4rem;
  border-left: 2px solid var(--ctf-line);
}
.ctf-event:last-child { border-left-color: transparent; padding-bottom: 0.2rem; }
.ctf-event::before {
  content: "";
  position: absolute;
  left: -0.42rem;
  top: 0.32rem;
  width: 0.72rem;
  height: 0.72rem;
  border-radius: 50%;
  background: var(--ctf-illegal);
  border: 2px solid var(--ctf-page);
}
.ctf-event .when {
  font-size: 0.74rem;
  font-weight: 750;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ctf-illegal);
}
.ctf-event .what { font-weight: 700; color: var(--ctf-ink); margin: 0.1rem 0 0.2rem 0; }
.ctf-event .why { font-size: 0.95rem; line-height: 1.55; color: var(--ctf-ink-soft); margin: 0; }

/* --- Talk to a person ---
   Above the findings, not in the footer. It carries a weight of its own without
   borrowing the red of an illegal finding: this is not a warning about the contract,
   it is a statement about the limits of the thing that read it. */
.ctf-human {
  border: 1px solid var(--ctf-line);
  border-left: 5px solid var(--ctf-brand);
  border-radius: var(--ctf-radius);
  background: var(--ctf-card);
  padding: 0.9rem 1.1rem;
  margin: 0.6rem 0 1.5rem 0;
}
.ctf-human p {
  font-size: 0.97rem !important;
  line-height: 1.6 !important;
  color: var(--ctf-ink) !important;
  margin: 0;
}

/* --- Footer --- */
.ctf-disclaimer {
  border-top: 1px solid var(--ctf-line);
  margin-top: 2.5rem;
  padding-top: 1rem;
  font-size: 0.86rem;
  line-height: 1.55;
  color: var(--ctf-ink-faint);
}

/* --- Streamlit widgets, nudged rather than rebuilt --- */
.stButton > button {
  border-radius: var(--ctf-radius);
  font-weight: 650;
  padding: 0.55rem 1rem;
  border: 1px solid var(--ctf-line);
}
.stButton > button[kind="primary"] { border-color: var(--ctf-brand); }
div[data-testid="stExpander"] details {
  border: 1px solid var(--ctf-line);
  border-radius: var(--ctf-radius);
  background: var(--ctf-card);
}

@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  .ctf-masthead h1 { font-size: 1.68rem; }
  .ctf-tile { flex: 1 1 100%; }
}
</style>
"""


def esc(text: object) -> str:
    """Escape anything before it reaches the page.

    Findings quote uploaded documents and are written by a language model, so this
    is not a formality: without it, a contract containing a stray angle bracket
    would break the layout, and a crafted one could inject markup.
    """
    return escape(str(text), quote=True)


def accent(category: str) -> str:
    return CATEGORY_COLOURS.get(category, "#16161A")


# --- Blocks ----------------------------------------------------------------


def masthead(title: str, standfirst: str, eyebrow: str = "Before you sign") -> str:
    return (
        '<div class="ctf-masthead">'
        f'<p class="ctf-eyebrow">{esc(eyebrow)}</p>'
        f"<h1>{esc(title)}</h1>"
        f'<p class="ctf-standfirst">{esc(standfirst)}</p>'
        "</div>"
    )


def step_heading(number: int, title: str) -> str:
    return (
        '<div class="ctf-step">'
        f'<div class="ctf-step-n">{esc(number)}</div>'
        f'<div class="ctf-step-t">{esc(title)}</div>'
        "</div>"
    )


def glance(counts: list[tuple[str, int, str]]) -> str:
    """A count per category. Only categories that actually occurred are shown.

    Deliberately not a score or a percentage: "3 things here are against the law" is
    a fact a reader can check, where "risk score 72" is a number they cannot.
    """
    tiles = "".join(
        f'<div class="ctf-tile" style="--tile-accent:{esc(colour)}">'
        f'<div class="n">{esc(count)}</div>'
        f'<div class="l">{esc(label)}</div>'
        "</div>"
        for label, count, colour in counts
        if count
    )
    return f'<div class="ctf-glance">{tiles}</div>' if tiles else ""


def category_heading(label: str, help_text: str, category: str) -> str:
    return (
        f'<div class="ctf-cat" style="--cat-accent:{esc(accent(category))}">'
        f"<h3>{esc(label)}</h3>"
        f"<p>{esc(help_text)}</p>"
        "</div>"
    )


def finding_card(
    *,
    title: str,
    what_it_means: str,
    severity: str,
    category: str,
    quotes: list[tuple[str, str | None, str]],
    unverified: bool,
) -> str:
    colour = accent(category)
    # The separator is a literal entity, so only the clause reference itself is
    # escaped - passing the whole string through `esc` would print "&amp;middot;".
    quote_html = "".join(
        '<div class="ctf-quote">'
        f'<p class="src">{esc(doc_id)}'
        f'{" &middot; clause " + esc(clause_ref) if clause_ref else ""}</p>'
        f"<blockquote>{esc(quote.strip())}</blockquote>"
        "</div>"
        for doc_id, clause_ref, quote in quotes
    )
    warning = (
        '<p class="ctf-unverified">The legal figure behind this check has not yet been '
        "verified by our team. Treat it as a question to ask, not as a settled fact.</p>"
        if unverified
        else ""
    )
    return (
        f'<div class="ctf-card" style="--card-accent:{esc(colour)}">'
        f'<span class="ctf-flag">{esc(SEVERITY_WORDS.get(severity, severity))}</span>'
        f'<div class="ctf-title">{esc(title)}</div>'
        f'<p class="ctf-body">{esc(what_it_means)}</p>'
        f"{quote_html}{warning}"
        "</div>"
    )


def timeline_event(when: str, label: str, description: str) -> str:
    return (
        '<div class="ctf-event">'
        f'<div class="when">{esc(when)}</div>'
        f'<p class="what">{esc(label)}</p>'
        f'<p class="why">{esc(description)}</p>'
        "</div>"
    )


def human_callout(text: str) -> str:
    """`safety.TALK_TO_A_HUMAN`, rendered above the findings rather than below them.

    Placement is the whole point. A reader who has seen three quoted clauses and a
    timeline has already formed their view by the time they reach a footer, and this
    is the sentence that says the list they are about to read is incomplete.
    """
    return f'<div class="ctf-human"><p>{esc(text)}</p></div>'


def disclaimer(text: str) -> str:
    return f'<p class="ctf-disclaimer">{esc(text)}</p>'
