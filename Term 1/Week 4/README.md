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

> Full write-up: **[`hackathon/README.md`](hackathon/README.md)**

**Project title:** Silent Tides, a 35-second climate film about coral bleaching

**My pair partner:** Evaldas

**Tool we had to use:** ComfyUI

**SDG we had to address:** SDG 13, Climate Action

**What problem does it solve, and for whom?**
From 1 Jan 2023 to 30 Mar 2025, ocean heat hit 84% of the world's coral reefs (ICRI, 2025), but Dutch/EU 18–30-year-olds still see climate change as slow and far away. The film shows them, in a format they actually watch (short, vertical, sound-off), that this collapse already happened.

**What did you build?**
A ComfyUI workflow (Wan 2.2 TI2V 5B, text-to-video) that generates every frame of a 7-shot film from text prompts, plus the film itself, cut in CapCut with a voiceover made in ComfyUI (Kokoro TTS). Any shot can be regenerated from the prompt, seed and frame count in the shot list.

**Link to the live thing (if any):** [YouTube link]. Workflow: [`hackathon/workflow/silent_tides_workflow.json`](hackathon/workflow/silent_tides_workflow.json)

**How do I run it?**
Install ComfyUI, download the 3 Wan 2.2 model files, load the workflow JSON, paste a shot's prompt, set seed 112233 (fixed) and the frame count (97, or 113 for shots 4 and 7), and click Run. Full steps are in the [hackathon README](hackathon/README.md#7-how-to-run--regenerate-a-shot).

**Who did what?**
- **Lan Dinh (me):** storyboard and shot list, refining the workflow (prompts, seeds, frame lengths), rendering all 7 shots, README and ethical reflection
- **Evaldas:** base ComfyUI workflow (Wan 2.2 setup), voiceover (Kokoro TTS in ComfyUI), editing the final cut in CapCut

**Ethical reflection - what are the risks of your tool? Who could it harm?**
The footage is photoreal enough to be taken for documentary footage of a real reef. If it's shared as "the Great Barrier Reef now" and debunked, it hurts trust in real reef footage and gives climate deniers an easy argument. We never name a real place, the film ends with an on-screen "AI-generated imagery & voice" card, and the only hard number is sourced, so viewers can check it. The voice is AI too, but a stock voice, not a clone of anyone. Making the film used about 1.2 kWh for 15 renders, and only a quarter of that went into the 7 clips in the film. Full reflection in the [hackathon README](hackathon/README.md#9-ethical-reflection).

### Checklist
- [x] Prototype code (or export / workflow file) is in `hackathon/`
- [ ] This week's slides are in `hackathon/`
- [x] The prototype actually runs, and I wrote down how to run it
- [x] Ethical reflection written above

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
