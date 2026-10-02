# Term 1 - Week 4: Strings, Text & Files

---

## 1. Homework & workshop assignments -> [`homework/`](homework/)

**What was the assignment?**
The Week 4 workshop on cleaning, splitting and counting text, and reading and writing files (3 exercises). Then the big individual assignment: a **Community Feedback Analyzer** that reads a file of citizen feedback, cleans and splits the text, counts word frequencies and writes a report. The report gives the number of responses, average words per response, top 5 keywords, and the urgent responses.
Homework: polish the analyzer, run it on a piece of **real public text**, and explain what it reveals and what it misses.

**What did I hand in?**
- [`homework/Week4_Workshop_Student.ipynb`](homework/Week4_Workshop_Student.ipynb) contains:
  - Exercises 1–3 (clean one response, word frequencies with stopwords, read/write `feedback.txt` and `report.txt`) and the reflection on whose voices are missing from the data
  - **Community Feedback Analyzer**: one helper function per job (`read_responses`, `clean_words`, `count_words`, `top_keywords`, `find_urgent`, `build_report`, …). It writes `feedback_report.txt`, and includes all 3 bonus features: sentiment score, word search, and numbers found with `re.findall`
  - **Homework**: the same analyzer, unchanged, run on **1000 real Yelp reviews** (UCI *Sentiment Labelled Sentences*, Kotzias et al. 2015), with a write-up of what it reveals and what it misses

**What did I find difficult, and how did I solve it?**
The analyzer worked on the small practice file, but the real data showed its limits. My sentiment score called the Yelp reviews "mostly positive" (229 vs 29 words), while the dataset is actually 500 positive and 500 negative. I found the reasons by checking the data: negation ("not good" still counts as positive; 112 reviews contain "not") and word lists written for city feedback rather than restaurants. I documented this in the notebook instead of hiding it, because it's the main lesson of the homework.

### Checklist
- [x] My workshop / homework files are in `homework/`
- [x] Everything runs without errors, or I explained what does not and why

---

## 2. Hackathon prototype -> [`hackathon/`](hackathon/)

> Your tool and your SDG for this hackathon are announced at the **start of Friday's class**.
> Write them down here once you know them.

**Project title:**

**My pair partner:**

**Tool we had to use:**

**SDG we had to address:**

**What problem does it solve, and for whom?**
_Name a real, specific user. "Everyone" is not a user._

**What did you build?**
_Two or three sentences. What can a user actually do with it?_

**Link to the live thing (if any):**
_Deployed URL, workflow export, video demo - whatever proves it works._

**How do I run it?**
_Short instructions so someone else can start it._

**Who did what?**
_Be honest about the split of work between you and your partner._

**Ethical reflection - what are the risks of your tool? Who could it harm?**
_Every hackathon requires this. One honest paragraph beats three vague ones._

### Checklist
- [ ] Prototype code (or export / workflow file) is in `hackathon/`
- [ ] This week's slides are in `hackathon/`
- [ ] The prototype actually runs, and I wrote down how to run it
- [ ] Ethical reflection written above

---

## 3. Presentation -> [`presentation/`](presentation/)

*Only fill this in for the week your group was selected to present. You need at least **one** of these across the whole term.*

- [ ] My group presented in this week
- [ ] Slides are in `presentation/`
- [ ] Proof of the live demo is in `presentation/` (recording, screenshots, or link)

**How did it go? What would I do differently next time?**

---

## 4. Reflection

**What is the most important thing I learned this week?**
A computer doesn't understand text, it counts it. Cleaning (`strip`, `lower`, removing punctuation), splitting into words and counting with a dictionary is enough to find out **what** people talk about. It is not enough to know **how they feel**: word lists only know the words I put in them.

**Where does this connect to "AI for Good"?**
A city that "listens at scale" with a tool like this only hears the people who wrote something down, in the words the programmer expected. Elderly people, people without internet, or people writing in another language are invisible, and a rare but serious complaint can be outranked by many small ones. A human (and the affected community) should decide what counts as urgent and still read the unusual responses.

**AI use:** I used Claude (Anthropic) to help with the homework part: downloading the Yelp dataset in the notebook and wording the "reveals / misses" write-up. The analysis results come from running my own analyzer code.
