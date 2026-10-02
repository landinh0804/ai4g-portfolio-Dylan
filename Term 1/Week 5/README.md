# Term 1 - Week 5: Machine Learning Basics

---

## 1. Homework & workshop assignments -> [`homework/`](homework/)

**What was the assignment?**
My first machine-learning models with scikit-learn, on a real breast-cancer screening dataset: KNN, logistic regression and decision trees, overfitting, and reading a confusion matrix. Then the big individual assignment, **Build & Evaluate Your Own Classifier**.
Homework: (1) run the Titanic wrap-up section (the 8-step recipe for messy data) and do its 4 *Your turn* cells; (2) finish the classifier and run the same workflow on a **second dataset**, with a paragraph comparing the results; (3) DataCamp *Supervised Learning with scikit-learn*, chapters 1–4.

**What did I hand in?**
- [`homework/Week5_Workshop_Student.ipynb`](homework/Week5_Workshop_Student.ipynb) contains:
  - Exercises 1–3: KNN (96.5%), logistic regression vs trees, the overfitting tree (100% train / 95.1% test), and the confusion matrix (4 dangerous misses, 1 false alarm), plus the reflection on which error is worse
  - **Big assignment**: one reusable `run_workflow()` function (split → 4 models → tune k with a plot → classification report → confusion matrix of the best model). Best on breast cancer: logistic regression + scaler, **98.6%**, with 1 missed cancer in 143 test patients
  - **Second dataset (wine)** with a comparison table and paragraph: scaling lifts KNN from 0.78 to 0.93 on wine; logistic regression wins on both datasets
  - **Titanic wrap-up**, all 4 *Your turn* cells: the cheat column (`alive`) and copied columns, tuning the tree depth (best depth 4; deeper trees overfit), fairness per class (3rd class served worst), and a person on the Titanic (11% as male vs 64% as female)

**What did I find difficult, and how did I solve it?**
Understanding why accuracy alone isn't enough. On breast cancer, 96.5% sounded great until the confusion matrix showed 4 cancers sent home, and on the Titanic a lazy model already gets 61% without learning anything. I solved it by always looking at the confusion matrix and recall per group, not just one score. A second surprise: unscaled KNN got only 78% on wine because one measurement (proline) has much bigger numbers than the others, and scaling fixed that.

### Checklist
- [x] My workshop / homework files are in `homework/`
- [x] Everything runs without errors, or I explained what does not and why

> DataCamp chapters 1–4: still to do on my own DataCamp account (progress is tracked there, not in this repo).

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
Every model follows the same four steps (choose → fit → predict → score), so swapping KNN for a tree is one line. The real work is everything around the model: splitting first, scaling inside a Pipeline, comparing against a lazy baseline, and choosing the score that matches which mistake hurts people most.

**Where does this connect to "AI for Good"?**
A model learns the history inside its data. The Titanic model finds 96% of the women who survived but only 12% of the men, and it serves 3rd class worst. Used to decide who gets help first today, it would automate 1912's unfair rules with confidence. In healthcare the same thing can happen when a model trained on one hospital's patients is used on another population. That's why you check results per group, and why a doctor, not the model, makes the decision.

**AI use:** I used Claude (Anthropic) to help write and run the notebook code and to word the reflections. All numbers come from actually running the notebook in Colab, and I checked that the answers match the outputs.
