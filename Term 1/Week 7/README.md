# Term 1 - Week 7: Computer Vision

---

## 1. Homework & workshop assignments -> [`homework/`](homework/)

**What was the assignment?**

**What did I hand in?**
_List the files, or link to them. Notebook exports, screenshots, scripts._

**What did I find difficult, and how did I solve it?**

### Checklist
- [ ] My workshop / homework files are in `homework/`
- [ ] Everything runs without errors, or I explained what does not and why

---


## 2. Hackathon prototype -> [`hackathon/`](hackathon/)

**Project title:** Invasive Plant Spotter (Eyes on Earth)

**My pair partner:** Ana

**Tool we had to use:** Roboflow, to train a computer vision model on a Netherlands subject and run it on new unseen images.

**SDG we had to address:** SDG 15, Life on Land (target 15.8: prevent and reduce the impact of invasive alien species).

**What problem does it solve, and for whom?**
Municipal green-space teams, water boards and volunteer groups need to find Japanese knotweed and giant hogweed early, before they damage paving and dikes or burn someone's skin. The model gives them a first screening of a photo, and a person confirms every finding.

**What did you build?**
A Roboflow RF-DETR Small object detection model for two classes (japanese_knotweed, giant_hogweed), trained on 415 openly licensed iNaturalist photos from the Netherlands, and a small Streamlit app. A user uploads a photo and the app draws boxes with the class and a confidence score. On the 41-image test set the model scored mAP@50 90.5%, precision 98.0% and recall 82.5%. A new hogweed photo that was not in the dataset was detected at 90% confidence.

**Link to the live thing (if any):**
No public deployment. It runs locally from [`hackathon/`](hackathon/), with a Roboflow API key kept outside the repository.

**How do I run it?**
Short version: install `requirements.txt`, set `ROBOFLOW_API_KEY` and `ROBOFLOW_MODEL_ID`, then run `python -m streamlit run app.py`. Full steps are in [`hackathon/README.md`](hackathon/README.md).

**Who did what?**
We had no photos of our own, so all images were scraped from iNaturalist with per-photo author and licence kept in `hackathon/data/sources.csv`. An AI coding assistant (Claude) did most of the hands-on work under Dylan's direction: the scraping script, the Roboflow project setup and Auto Label run, the app code and the first drafts of the README and ethical reflection. Dylan chose the topic, approved each step, set up the accounts and ran the app. [Dylan: add what Ana did.]

**Ethical reflection - what are the risks of your tool? Who could it harm?**
The labels were made by Roboflow Auto Label and only 14 of the 415 images were checked by a person, so the test scores are probably optimistic, and photos of the same observation can sit in both train and test. The model misses about 1 in 6 plants, so a false negative could let an invasive plant spread unnoticed, while a false positive could lead to a native plant being sprayed or a landowner being wrongly blamed. We never tested look-alike plants such as giant cow parsley or angelica, or knotweed on a new photo. Giant hogweed sap burns skin, so the app must never encourage anyone to approach or touch a plant. It is a screening aid and a person has to confirm every detection. The full reflection is in [`hackathon/ETHICS.md`](hackathon/ETHICS.md).

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

**Where does this connect to "AI for Good"?**
_One concrete link to ethics, sustainability or social impact._
