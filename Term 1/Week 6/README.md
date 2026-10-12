# Term 1 - Week 6: Language Models

---

## 1. Homework & workshop assignments -> [`homework/`](homework/)

**What was the assignment?**
Week 6 was about language models: word embeddings, RNNs and LSTMs, and transformers, using small ready-made models instead of building any. The big individual assignment was to **stress-test a sentiment model**: pick a context, write at least 12 test sentences covering at least four kinds of difficulty, label them myself first, run the model, analyse the failures, run a bias probe, and write a judgement. Homework: DataCamp *Recurrent Neural Networks for Language Modeling with Keras* (chapters 1 and 4) and the first chapter of *Introduction to LLMs in Python*.

**What did I hand in?**
- [`homework/Week6_Stress_Test_Dylan.ipynb`](homework/Week6_Stress_Test_Dylan.ipynb) is the big assignment, section 4 of the workshop notebook, as a standalone notebook that runs top to bottom with its outputs saved:
  - **Context:** feedback from railway passengers, because I read hundreds of rail posts in the Week 6 hackathon.
  - **Test set:** 14 sentences covering all six kinds (negation, mixed feelings, sarcasm, a long sentence, typos and slang, Dutch and German), each with my own label written before running the model.
  - **Result:** the model (DistilBERT, English only) agreed with me on 9 of 14. It failed on the long polite complaint, the slang with typos, a sarcastic sentence, and the Dutch and German sentences, with 93% to 100% confidence.
  - **Error analysis:** three failures explained, with what a reader would have needed and which rung of the ladder (embedding, RNN, LSTM, transformer) would or would not handle it.
  - **Bias probe:** after "The train driver said that", "he" is about 11 times more likely than "she"; after "The cleaner said that" it is about 2.4 times.
  - **Judgement:** I would not let the model read passenger feedback on its own, only as a first sorting step in English with a person checking a sample.

**What did I find difficult, and how did I solve it?**
The model's confidence was the surprise: it was 94% to 99% sure that friendly German and Dutch sentences were negative, so confidence is not a warning light. I solved the analysis by sorting every failure into "what would a reader need": the order of the words, a memory of an earlier word, or the context around a word. A limit: only 14 sentences, and my labels are my own judgement, so the numbers are a rough picture. I did not do the bonus options, and the DataCamp courses are still to do on my own account.
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

**Where does this connect to "AI for Good"?**
_One concrete link to ethics, sustainability or social impact._
