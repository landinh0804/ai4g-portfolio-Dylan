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
- [`homework/Week6_Lecture_Prep.md`](homework/Week6_Lecture_Prep.md) is the lecture preparation: notes on the two videos (NLP and the prompt formula), four probes of an LLM with the answers checked against real sources, one LLM product (Duolingo Max), and the article on Kenyan data labelling work with the question who pays.

**What did I find difficult, and how did I solve it?**
The model's confidence was the surprise: it was 94% to 99% sure that friendly German and Dutch sentences were negative, so confidence is not a warning light. I solved the analysis by sorting every failure into "what would a reader need": the order of the words, a memory of an earlier word, or the context around a word. A limit: only 14 sentences, and my labels are my own judgement, so the numbers are a rough picture. I did not do the bonus options, and the DataCamp courses are still to do on my own account.

### Checklist
- [x] My workshop / homework files are in `homework/`
- [x] Everything runs without errors, or I explained what does not and why

---


## 2. Hackathon prototype -> [`hackathon/`](hackathon/)

Full write-up: [`hackathon/README.md`](hackathon/README.md)

**Project title:** Bahn-Puls: live passenger sentiment for Deutsche Bahn (Live Pulse)

**My pair partner:** Felix Reichle (group 12)

**Tool we had to use:** a pre-trained Hugging Face sentiment model that we run ourselves (we used two, `oliverguhr/german-sentiment-bert` and `cardiffnlp/twitter-xlm-roberta-base-sentiment`), on a live public data stream, with no chat model doing the sentiment analysis.

**SDG we had to address:** SDG 9, Industry, Innovation and Infrastructure (main target 9.1, secondary 9.4)

**What problem does it solve, and for whom?**
A regional customer-communication team at Deutsche Bahn (or a passenger association such as Pro Bahn) has to decide every morning which issue gets proactive communication: delays, construction, the app, or on-board problems. Passengers complain on social media long before it shows in official statistics, and punctuality is at a record low (52.4% of long-distance trains on time in September 2026). Bahn-Puls shows which topic is more negative than its own 7-day baseline, and the posts behind it.

**What did you build?**
A collector that searches Bluesky for German rail posts every 10 minutes, filters out bots and off-topic posts, stores the text with a timestamp (no author data), scores every post with both models, and a Streamlit dashboard that charts the negative share per topic per day or hour and lets you open the posts behind a point. It ran unattended for more than 48 hours.

**Link to the live thing (if any):** the dashboard is at https://pulse-deutsche-bahn.streamlit.app/ and the collector's runs are in Felix's repo: https://github.com/flxr8/ai4g-portfolio-felix-reichle/actions

**How do I run it?**
`cd "Term 1/Week 6/hackathon"`, create a Python environment, `pip install torch --index-url https://download.pytorch.org/whl/cpu`, `pip install -r requirements.txt`, then `python -m pulse.collect` for one collection cycle and `streamlit run dashboard.py` for the dashboard. Full steps are in `hackathon/README.md` section 7. The first run downloads about 1.5 GB of models.

**Who did what?**
Felix built the collector and filters, the GitHub Actions scheduler, the dashboard and its hosting, the evaluation code and the model cards. I ran a second, independent collection on my laptop (739 posts over 50 hours, 301 runs, none failed, kept in `hackathon/dylan_run/`), checked the data and the model results, read Bluesky's terms, wrote the SDG 9, results and failure-analysis text, and made the slides. We shared the choice of stream and the 50 hand labels. An AI coding assistant (Claude) helped with code, checks and drafting; the sentiment itself is scored only by the two pre-trained models.

**Ethical reflection - what are the risks of your tool? Who could it harm?**
The main harm is to passengers who are misread. In our 50-post test the models agreed with our own labels only 50% to 54% of the time, and they miss sarcasm, read plain service notices as neutral, and score posts that are not about rail. If a communication team used the dashboard as a measurement, it could ignore real problems or chase false ones, so we describe it as a trend indicator only. The second risk is to the people whose public Bluesky posts we collect without asking: we store no handles, names or post URLs, but the post texts are public and we do not re-check deletions, so we only partly meet Bluesky's rule to delete content users removed. The data is also not representative, because Bluesky users skew young, urban and online and people post when something goes wrong. It must not be used to judge staff, contact passengers or rank lines on a handful of posts.

### Checklist
- [x] Prototype code (or export / workflow file) is in `hackathon/`
- [x] This week's slides are in `hackathon/`
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
A language model is trained to sound right, not to be right. In my workshop test the model was 93% to 100% sure about sarcasm, slang and Dutch and German sentences that it got wrong, and in the hackathon our two models agreed with our own labels only about half of the time. So its confidence score is not a warning light. From now on I label a small sample myself before I trust a model, and I check it on the kinds of text it was not trained on.

**Where does this connect to "AI for Good"?**
Bahn-Puls could help a railway company warn passengers earlier (SDG 9), but every system has a hidden invoice, as the lecture said. For our case, the benefit goes to a railway communication team and the passengers who get a faster answer, and the cost is paid by passengers whose posts are misread (especially if they write in another language or in slang), by people whose public posts we collect without asking, and by the people and energy behind the models. That is why we call the dashboard a trend indicator that needs a person checking, not a measurement.
