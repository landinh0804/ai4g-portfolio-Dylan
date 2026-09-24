"""The take-away sheet: a .docx the worker can print, keep, and hand to somebody.

Everything else this tool produces ends on a screen the worker may not have with
them at the moment it matters. The report is read at a recruitment desk, on a phone,
minutes before signing; the conversation it is supposed to enable happens afterwards,
with a recruiter, a caseworker or an inspector, and usually in Dutch, which the
reader does not speak. A report that cannot leave the screen stops exactly where the
worker needs it to start.

So this sheet is bilingual by construction. Every question appears in the worker's
language and in Dutch, side by side, and every quote stays in the language of the
document it was taken from. Someone who speaks no Dutch can put the page in front of
a Dutch speaker and point at a line. That is the whole design.

Three things it does not do:

* It does not call a model. `SafeQuestion` already carries
  `question_in_employer_language`, produced by step 5, and the quotes are already in
  the original language because the compose prompt keeps them there. Adding a
  translation call here would put an unverified sentence on a page built to be
  handed to the employer.
* It does not soften the gate. When the pipeline refused to summarise, the sheet
  leads with that refusal. Deterministic findings still appear underneath, because a
  rule check that fired is still a fact, which is the same rule `pipeline.py`
  follows.
* It does not tell anyone what to do. The questions are questions.

The only strings here that the pipeline did not produce are the fixed labels in
LABELS. They are translations written for this file and not checked by a native
speaker, except English and Dutch; the sheet says so on itself for the languages
where it is true, in the same spirit as the unverified-rule caveat.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.shared import Pt, RGBColor

from . import config
from .models import Report

# --- Fixed strings ---------------------------------------------------------

# Dutch is always present on the sheet: it is the language of the documents and of
# the person the worker has to talk to. The worker's own language is the other half.
PINK = RGBColor(0xDD, 0x13, 0x67)
GREY = RGBColor(0x66, 0x66, 0x66)
BLACK = RGBColor(0x16, 0x16, 0x1A)

# Languages whose fixed labels a native speaker has read. Until a language is in
# here, the sheet prints a line saying its fixed labels are unchecked - the same
# move as `verified` in legal_rules.json, for the same reason.
LABELS_CHECKED = {"en", "nl"}

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Before you sign: questions to ask",
        "intro": "This sheet was produced from the documents you were given. It is information, not legal advice, and it does not tell you whether to sign.",
        "questions": "Questions to ask, in both languages",
        "questions_hint": "You can show this page to the person asking you to sign and point at the question on the right.",
        "why": "What the answer tells you",
        "refusal": "If this is not answered in writing",
        "findings": "What was found in your documents",
        "talk_to_human": "Talk to a person about what is on this page. This check was done by a computer: it can read a clause wrongly, and it cannot see anything that was not in the documents. The organisations listed below will go through them with you.",
        "quote_from": "In the document",
        "unverified": "The legal rule behind this finding has not yet been confirmed against the version in force.",
        "timeline": "If the work ends",
        "contacts": "Who you can ask, without going through your employer",
        "employer_knows": "Will your employer find out",
        "response_time": "Usually answers in",
        "gated": "This tool did not have enough confidence to summarise these documents",
        "conflicts": "Where the documents disagree with each other",
        "footer": "Keep this page. The quotes are copied from your documents word for word.",
        "labels_unchecked": "The fixed headings on this sheet were translated for this tool and have not been checked by a native speaker. The questions and findings come from your documents.",
    },
    "nl": {
        "title": "Voordat u tekent: vragen om te stellen",
        "intro": "Dit blad is gemaakt op basis van de documenten die u heeft gekregen. Het is informatie, geen juridisch advies, en het zegt niet of u moet tekenen.",
        "questions": "Vragen om te stellen, in beide talen",
        "questions_hint": "U kunt deze pagina laten zien aan degene die u vraagt te tekenen, en naar de vraag rechts wijzen.",
        "why": "Wat het antwoord u vertelt",
        "refusal": "Als dit niet schriftelijk wordt beantwoord",
        "findings": "Wat er in uw documenten is gevonden",
        "talk_to_human": "Bespreek deze pagina met een mens. Deze controle is door een computer gedaan: die kan een clausule verkeerd lezen en ziet niets wat niet in de documenten stond. De organisaties hieronder nemen ze met u door.",
        "quote_from": "In het document",
        "unverified": "De juridische regel achter deze bevinding is nog niet gecontroleerd tegen de geldende versie.",
        "timeline": "Als het werk stopt",
        "contacts": "Wie u kunt vragen, buiten uw werkgever om",
        "employer_knows": "Komt uw werkgever hierachter",
        "response_time": "Antwoordt meestal binnen",
        "gated": "Dit hulpmiddel had niet genoeg zekerheid om deze documenten samen te vatten",
        "conflicts": "Waar de documenten elkaar tegenspreken",
        "footer": "Bewaar deze pagina. De citaten zijn woordelijk uit uw documenten overgenomen.",
        "labels_unchecked": "",
    },
    "pl": {
        "title": "Zanim podpiszesz: pytania, które warto zadać",
        "intro": "Ta strona powstała na podstawie dokumentów, które otrzymałeś lub otrzymałaś. To informacja, a nie porada prawna, i nie mówi, czy masz podpisać.",
        "questions": "Pytania do zadania, w obu językach",
        "questions_hint": "Możesz pokazać tę stronę osobie, która prosi o podpis, i wskazać pytanie po prawej stronie.",
        "why": "Co mówi odpowiedź",
        "refusal": "Jeśli nie otrzymasz odpowiedzi na piśmie",
        "findings": "Co znaleziono w twoich dokumentach",
        "talk_to_human": "Porozmawiaj o tej stronie z człowiekiem. Tę analizę wykonał komputer: może błędnie odczytać zapis umowy i nie widzi niczego, czego nie było w dokumentach. Organizacje wymienione poniżej przejdą je razem z tobą.",
        "quote_from": "W dokumencie",
        "unverified": "Przepis prawny stojący za tym ustaleniem nie został jeszcze potwierdzony z obowiązującą wersją.",
        "timeline": "Jeśli praca się skończy",
        "contacts": "Kogo możesz zapytać, z pominięciem pracodawcy",
        "employer_knows": "Czy pracodawca się dowie",
        "response_time": "Zwykle odpowiada w ciągu",
        "gated": "To narzędzie nie miało wystarczającej pewności, aby podsumować te dokumenty",
        "conflicts": "Gdzie dokumenty są ze sobą sprzeczne",
        "footer": "Zachowaj tę stronę. Cytaty przepisano z twoich dokumentów słowo w słowo.",
        "labels_unchecked": "",
    },
    "ro": {
        "title": "Înainte să semnezi: întrebări de pus",
        "intro": "Această pagină a fost creată din documentele pe care le-ai primit. Este informație, nu consultanță juridică, și nu îți spune dacă să semnezi.",
        "questions": "Întrebări de pus, în ambele limbi",
        "questions_hint": "Poți arăta această pagină persoanei care îți cere să semnezi și să indici întrebarea din dreapta.",
        "why": "Ce îți spune răspunsul",
        "refusal": "Dacă nu primești răspuns în scris",
        "findings": "Ce s-a găsit în documentele tale",
        "talk_to_human": "Discută această pagină cu o persoană. Verificarea a fost făcută de un computer: poate citi greșit o clauză și nu vede nimic care nu se afla în documente. Organizațiile de mai jos le vor parcurge împreună cu tine.",
        "quote_from": "În document",
        "unverified": "Regula juridică din spatele acestei constatări nu a fost încă verificată față de versiunea în vigoare.",
        "timeline": "Dacă munca se încheie",
        "contacts": "Pe cine poți întreba, fără să treci prin angajator",
        "employer_knows": "Va afla angajatorul",
        "response_time": "De obicei răspunde în",
        "gated": "Acest instrument nu a avut suficientă certitudine pentru a rezuma aceste documente",
        "conflicts": "Unde documentele se contrazic",
        "footer": "Păstrează această pagină. Citatele sunt copiate cuvânt cu cuvânt din documentele tale.",
        "labels_unchecked": "",
    },
    "bg": {
        "title": "Преди да подпишете: въпроси, които да зададете",
        "intro": "Този лист е създаден от документите, които сте получили. Това е информация, не правен съвет, и не ви казва дали да подпишете.",
        "questions": "Въпроси за задаване, на двата езика",
        "questions_hint": "Можете да покажете тази страница на човека, който иска да подпишете, и да посочите въпроса вдясно.",
        "why": "Какво ви казва отговорът",
        "refusal": "Ако това не получи писмен отговор",
        "findings": "Какво беше намерено във вашите документи",
        "talk_to_human": "Обсъдете тази страница с човек. Проверката е направена от компютър: той може да разчете клауза погрешно и не вижда нищо, което не е било в документите. Организациите по-долу ще ги прегледат заедно с вас.",
        "quote_from": "В документа",
        "unverified": "Правното правило зад тази находка още не е проверено спрямо действащата версия.",
        "timeline": "Ако работата приключи",
        "contacts": "Към кого можете да се обърнете, без да минавате през работодателя",
        "employer_knows": "Ще разбере ли работодателят",
        "response_time": "Обикновено отговаря в рамките на",
        "gated": "Този инструмент нямаше достатъчна увереност да обобщи тези документи",
        "conflicts": "Къде документите си противоречат",
        "footer": "Запазете тази страница. Цитатите са преписани дословно от вашите документи.",
        "labels_unchecked": "",
    },
    "uk": {
        "title": "Перш ніж підписати: питання, які варто поставити",
        "intro": "Цей аркуш створено з документів, які вам дали. Це інформація, а не юридична консультація, і він не каже, чи підписувати.",
        "questions": "Питання, які варто поставити, обома мовами",
        "questions_hint": "Ви можете показати цю сторінку людині, яка просить підписати, і вказати на питання праворуч.",
        "why": "Що каже відповідь",
        "refusal": "Якщо на це не відповіли письмово",
        "findings": "Що знайдено у ваших документах",
        "talk_to_human": "Обговоріть цю сторінку з людиною. Цю перевірку зробив комп'ютер: він може неправильно прочитати пункт і не бачить нічого, чого не було в документах. Організації, наведені нижче, розглянуть їх разом з вами.",
        "quote_from": "У документі",
        "unverified": "Правова норма, на якій ґрунтується цей висновок, ще не звірена з чинною редакцією.",
        "timeline": "Якщо робота закінчиться",
        "contacts": "До кого можна звернутися, оминаючи роботодавця",
        "employer_knows": "Чи дізнається роботодавець",
        "response_time": "Зазвичай відповідає протягом",
        "gated": "Цей інструмент не мав достатньої впевненості, щоб підсумувати ці документи",
        "conflicts": "Де документи суперечать одне одному",
        "footer": "Збережіть цю сторінку. Цитати переписано з ваших документів дослівно.",
        "labels_unchecked": "",
    },
    "hu": {
        "title": "Mielőtt aláírja: kérdések, amelyeket érdemes feltenni",
        "intro": "Ez a lap a kapott dokumentumokból készült. Tájékoztatás, nem jogi tanácsadás, és nem mondja meg, hogy aláírja-e.",
        "questions": "Felteendő kérdések, mindkét nyelven",
        "questions_hint": "Megmutathatja ezt az oldalt annak, aki az aláírást kéri, és rámutathat a jobb oldali kérdésre.",
        "why": "Mit árul el a válasz",
        "refusal": "Ha erre nem kap írásbeli választ",
        "findings": "Mit találtunk a dokumentumaiban",
        "talk_to_human": "Beszélje meg ezt az oldalt egy emberrel. Az ellenőrzést számítógép végezte: félreolvashat egy szerződési pontot, és nem lát semmit, ami nem szerepelt a dokumentumokban. Az alább felsorolt szervezetek együtt átnézik önnel.",
        "quote_from": "A dokumentumban",
        "unverified": "A megállapítás mögötti jogszabályt még nem ellenőriztük a hatályos változattal.",
        "timeline": "Ha a munka véget ér",
        "contacts": "Kit kérdezhet meg a munkáltató megkerülésével",
        "employer_knows": "Megtudja-e a munkáltató",
        "response_time": "Általában ennyi időn belül válaszol",
        "gated": "Ennek az eszköznek nem volt elég bizonyossága ahhoz, hogy összefoglalja ezeket a dokumentumokat",
        "conflicts": "Ahol a dokumentumok ellentmondanak egymásnak",
        "footer": "Őrizze meg ezt a lapot. Az idézeteket szó szerint másoltuk a dokumentumaiból.",
        "labels_unchecked": "",
    },
}

EMPLOYER_LANGUAGE = "nl"


def labels_for(language: str) -> dict[str, str]:
    """Fixed strings for one language, falling back to English."""
    return LABELS.get(language, LABELS["en"])


# --- Small helpers over python-docx ----------------------------------------


def _style_run(run, *, size: int, bold: bool = False, italic: bool = False, colour: RGBColor = BLACK) -> None:
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = colour


def _para(document, text: str, *, size: int = 10, bold: bool = False, italic: bool = False,
          colour: RGBColor = BLACK, space_after: int = 4, align=None):
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(space_after)
    if align is not None:
        paragraph.alignment = align
    _style_run(paragraph.add_run(text), size=size, bold=bold, italic=italic, colour=colour)
    return paragraph


def _heading(document, text: str) -> None:
    # Not upper-cased. Two of the seven languages here are written in Cyrillic, where
    # the all-caps treatment the web app uses for its eyebrow text reads badly, and
    # this page is read by someone under pressure in their second language.
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(14)
    paragraph.paragraph_format.space_after = Pt(6)
    _style_run(paragraph.add_run(text), size=12, bold=True, colour=PINK)


def _unwrap(quote: str) -> str:
    """Collapse the line breaks a source file wraps a clause with.

    Word puts a literal newline inside a run wherever it finds one, which on paper
    looks like the clause has been cut in half. The words are untouched: where the
    text was hyphenated across a break the hyphen goes with it, exactly as
    `safety.normalise_text` treats it when checking the quote against the source, so
    what is printed still matches the contract word for word.
    """
    without_hyphenation = re.sub(r"-\s*\n\s*", "", quote)
    return re.sub(r"\s+", " ", without_hyphenation).strip()


def _cell_text(cell, text: str, *, size: int = 10, bold: bool = False, italic: bool = False,
               colour: RGBColor = BLACK) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(2)
    _style_run(paragraph.add_run(text), size=size, bold=bold, italic=italic, colour=colour)


# --- The sheet --------------------------------------------------------------


def _add_gate_banner(document, report: Report, labels: dict[str, str]) -> None:
    """When the pipeline refused to summarise, the sheet says so first.

    Leading with the findings and mentioning the refusal at the bottom would turn a
    refusal into a footnote, which is how a gate stops working.
    """
    _para(document, labels["gated"], size=12, bold=True, colour=PINK, space_after=2)
    if report.gate_reason:
        _para(document, report.gate_reason, size=10)
    if report.conflicts:
        _para(document, labels["conflicts"], size=10, bold=True, space_after=2)
        for conflict in report.conflicts:
            _para(document, f"•  {conflict}", size=10, space_after=2)


def _add_questions(document, report: Report, labels: dict[str, str]) -> None:
    """The half of the sheet that is meant to be pointed at.

    Two columns: the worker's language on the left, Dutch on the right. Under each
    pair, one merged row carrying what the answer would tell them and what a refusal
    would tell them - which is often the more useful of the two.
    """
    if not report.safe_questions:
        return

    _heading(document, labels["questions"])
    _para(document, labels["questions_hint"], size=9, italic=True, colour=GREY, space_after=8)

    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for index, question in enumerate(report.safe_questions, start=1):
        pair = table.add_row().cells
        _cell_text(pair[0], f"{index}.  {question.question_in_user_language}", size=10, bold=True)
        _cell_text(pair[1], question.question_in_employer_language, size=10, bold=True, colour=PINK)

        detail = table.add_row().cells
        merged = detail[0].merge(detail[1])
        merged.text = ""
        first = merged.paragraphs[0]
        first.paragraph_format.space_after = Pt(2)
        _style_run(first.add_run(f"{labels['why']}: "), size=9, bold=True, colour=GREY)
        _style_run(first.add_run(question.why_this_question), size=9, colour=GREY)

        second = merged.add_paragraph()
        second.paragraph_format.space_after = Pt(2)
        _style_run(second.add_run(f"{labels['refusal']}: "), size=9, bold=True, colour=GREY)
        _style_run(second.add_run(question.what_a_refusal_means), size=9, colour=GREY)


def _add_findings(document, report: Report, labels: dict[str, str]) -> None:
    if not report.findings:
        return

    _heading(document, labels["findings"])
    # `safety.TALK_TO_A_HUMAN`, in the reader's language. On paper this matters more
    # than on the screen: a printed page of quoted clauses with a heading over it
    # looks like a verdict, and this is the line that says it is not one.
    _para(document, labels["talk_to_human"], size=9, italic=True, colour=GREY, space_after=8)

    for finding in report.findings:
        _para(document, finding.title, size=10, bold=True, space_after=2)
        _para(document, finding.what_it_means, size=10, space_after=2)

        for quote in finding.quotes:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Pt(18)
            paragraph.paragraph_format.space_after = Pt(2)
            # The quote stays in the language of the document it came from. That is
            # what makes it possible to point at the clause in the contract itself.
            _style_run(paragraph.add_run(f"“{_unwrap(quote.quote)}”"), size=9, italic=True)
            _style_run(paragraph.add_run(f"   — {labels['quote_from']}: {quote.doc_id}"), size=8, colour=GREY)

        if finding.rule_id and not finding.rule_verified:
            _para(document, labels["unverified"], size=8, italic=True, colour=GREY, space_after=8)
        else:
            _para(document, "", size=6, space_after=6)


def _add_timeline(document, report: Report, labels: dict[str, str]) -> None:
    scenario = report.exit_scenario
    if scenario is None or not scenario.events:
        return

    _heading(document, labels["timeline"])
    _para(document, scenario.trigger_description, size=10, space_after=6)

    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for event in scenario.events:
        cells = table.add_row().cells
        when = "?" if event.day_offset is None else (
            "day 0" if event.day_offset == 0 else f"+{event.day_offset}"
        )
        _cell_text(cells[0], when, size=9, bold=True, colour=PINK)
        _cell_text(cells[1], f"{event.label} — {event.description}", size=9)

    if scenario.caveat:
        _para(document, scenario.caveat, size=8, italic=True, colour=GREY)


def _add_contacts(document, report: Report, labels: dict[str, str]) -> None:
    if not report.contacts:
        return

    _heading(document, labels["contacts"])
    for contact in report.contacts:
        _para(document, contact.name, size=10, bold=True, space_after=2)
        _para(document, contact.what_they_do, size=9, space_after=2)
        # The contact route itself is printed verbatim, including the caveat that
        # rules/contacts.json attaches when the details have not been confirmed. A
        # wrong number given to somebody frightened to call at all is worse than none.
        route = contact.contact if not contact.url else f"{contact.contact}   |   {contact.url}"
        _para(document, route, size=9, bold=True, space_after=2)
        _para(
            document,
            f"{labels['employer_knows']}: {contact.will_employer_find_out}   |   "
            f"{labels['response_time']}: {contact.typical_response_time}",
            size=8,
            colour=GREY,
            space_after=8,
        )


def build_document(report: Report) -> Document:
    """Assemble the sheet. No model call, no network, no state."""
    language = report.user_language if report.user_language in LABELS else "en"
    labels = labels_for(language)
    document = Document()

    section = document.sections[0]
    section.left_margin = section.right_margin = Pt(42)
    section.top_margin = section.bottom_margin = Pt(42)

    _para(document, labels["title"], size=17, bold=True, space_after=2)
    if language != EMPLOYER_LANGUAGE:
        _para(document, LABELS[EMPLOYER_LANGUAGE]["title"], size=11, colour=GREY, space_after=6)

    generated = report.generated_at or datetime.now()
    _para(document, labels["intro"], size=9, colour=GREY, space_after=2)
    _para(document, generated.strftime("%Y-%m-%d"), size=8, colour=GREY, space_after=10)

    if report.gated:
        _add_gate_banner(document, report, labels)

    _add_questions(document, report, labels)
    _add_findings(document, report, labels)
    _add_timeline(document, report, labels)
    _add_contacts(document, report, labels)

    _para(document, "", size=6, space_after=10)
    _para(document, labels["footer"], size=8, italic=True, colour=GREY, space_after=2)
    if language not in LABELS_CHECKED and labels.get("labels_unchecked"):
        _para(document, labels["labels_unchecked"], size=7, italic=True, colour=GREY, space_after=2)
    elif language not in LABELS_CHECKED:
        _para(document, LABELS["en"]["labels_unchecked"], size=7, italic=True, colour=GREY, space_after=2)

    return document


def write_takeaway(report: Report, path: str | Path) -> Path:
    """Write the sheet to `path` and return it."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    build_document(report).save(str(destination))
    return destination


def default_filename(report: Report) -> str:
    stamp = (report.generated_at or datetime.now()).strftime("%Y-%m-%d")
    language = report.user_language if report.user_language in config.SUPPORTED_LANGUAGES else "en"
    return f"questions-to-ask-{language}-{stamp}.docx"
