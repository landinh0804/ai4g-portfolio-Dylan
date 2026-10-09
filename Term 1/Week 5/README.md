# Term 1 - Week 5: Machine Learning Basics

---

## 1. Homework & workshop assignments -> [`homework/`](homework/)

**What was the assignment?**
My first machine-learning models with scikit-learn, on a real breast-cancer screening dataset: KNN, logistic regression and decision trees, overfitting, and reading a confusion matrix. Then the big individual assignment, **Build & Evaluate Your Own Classifier**.
Homework: (1) run the Titanic wrap-up section (the 8-step recipe for messy data) and do its 4 *Your turn* cells; (2) finish the classifier and run the same workflow on a **second dataset**, with a paragraph comparing the results; (3) DataCamp *Supervised Learning with scikit-learn*, chapters 1-4.

**What did I hand in?**
- [`homework/Week5_Workshop_Student.ipynb`](homework/Week5_Workshop_Student.ipynb) contains:
  - Exercises 1-3: KNN (96.5%), logistic regression vs trees, the overfitting tree (100% train / 95.1% test), and the confusion matrix (4 dangerous misses, 1 false alarm), plus the reflection on which error is worse
  - **Big assignment**: one reusable `run_workflow()` function (split → 4 models → tune k with a plot → classification report → confusion matrix of the best model). Best on breast cancer: logistic regression + scaler, **98.6%**, with 1 missed cancer in 143 test patients
  - **Second dataset (wine)** with a comparison table and paragraph: scaling lifts KNN from 0.78 to 0.93 on wine; logistic regression wins on both datasets
  - **Titanic wrap-up**, all 4 *Your turn* cells: the cheat column (`alive`) and copied columns, tuning the tree depth (best depth 4; deeper trees overfit), fairness per class (3rd class served worst), and a person on the Titanic (11% as male vs 64% as female)

**What did I find difficult, and how did I solve it?**
Understanding why accuracy alone isn't enough. On breast cancer, 96.5% sounded great until the confusion matrix showed 4 cancers sent home, and on the Titanic a lazy model already gets 61% without learning anything. I solved it by always looking at the confusion matrix and recall per group, not just one score. A second surprise: unscaled KNN got only 78% on wine because one measurement (proline) has much bigger numbers than the others, and scaling fixed that.

### Checklist
- [x] My workshop / homework files are in `homework/`
- [x] Everything runs without errors, or I explained what does not and why

> DataCamp chapters 1-4: still to do on my own DataCamp account (progress is tracked there, not in this repo).

---


## 2. Hackathon prototype -> [`hackathon/`](hackathon/)

Full write-up: [`hackathon/README.md`](hackathon/README.md)

**Project title:** Who misses the extra grant? A model showdown on income data (UCI Adult)

**My pair partner:** Nina Borutyńska

**Tool we had to use:** scikit-learn (KNN, logistic regression and a random forest, in a Jupyter notebook)

**SDG we had to address:** SDG 8, Decent Work and Economic Growth

**What problem does it solve, and for whom?**
In the Netherlands, 24% of first-year hbo/wo students who are entitled to the aanvullende beurs never use it, and they miss about EUR 175 a month (CPB, 2018 data). A DUO team member has to decide which students get an information letter about it. Our model predicts whether a person earns $50K or less (a stand-in for "parents may be entitled") and ranks people by that probability. It is trained on 1994 US Census data, so it is a demonstration of the method and not a tool for Dutch students.

**What did you build?**
A notebook that takes the UCI Adult dataset (48,842 people) from the raw file to a fair comparison of a baseline and three tuned models: split first, a scikit-learn Pipeline, 5-fold cross-validation, one evaluation on the test set, an error analysis by sex and race, and a prediction for a made-up person. We recommend the random forest (balanced accuracy 0.827 on the test set), with conditions: it misses 17% of low-income people, so the letter cannot be the only channel.

**Link to the live thing (if any):** notebook: [`hackathon/hackathon5_model_showdown.ipynb`](hackathon/hackathon5_model_showdown.ipynb) (runs in Google Colab) · slides: [`hackathon/Hackathon5_slides.pptx`](hackathon/Hackathon5_slides.pptx)

**How do I run it?**
Open the notebook in Google Colab and choose Runtime > Run all. It downloads `adult.csv` if the file is not next to the notebook. A full run takes about 15 minutes. Packages, versions and a pandas 3 note are in [`hackathon/README.md`](hackathon/README.md).

**Who did what?**
- Nina: the notebook (data exploration, split, pipeline, baseline, the three tuned models, comparison table, error analysis, prediction)
- Lan Dinh (me): problem definition and sources, user group, ethical reflection, README and slides, testing that the notebook runs
- Together: the recommendation and preparing for questions

**Ethical reflection - what are the risks of your tool? Who could it harm?**
The data is from the 1994 US Census, so the model says nothing about Dutch students and must not be used on them before it is trained again on recent Dutch data. Sex and race are features, and the model learns old patterns from them: it finds 96% of low-income women but only 75% of low-income men, and it misses 17% of all low-income people, mostly married men, because it learned "married man with a full-time job = high income". A student who is missed gets no letter and may lose money they are entitled to. We chose balanced accuracy instead of recall (a baseline that flags everyone has recall 1.0), checked the results per sex and race, and wrote in the README who must not use the model. We did not check age or native country, and removing sex and race would not remove them because marital status and occupation can stand in for them.

**AI use:** I used Claude (Anthropic) to help write the README and slides, to review the notebook and to test that it runs. Claude also helped Nina write the notebook code. All numbers come from the notebook's outputs, and I checked that the text matches them.

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
Every model follows the same four steps (choose → fit → predict → score), so swapping KNN for a tree is one line. The real work is everything around the model: splitting first, scaling inside a Pipeline, comparing against a lazy baseline, and choosing the score that matches which mistake hurts people most.

**Where does this connect to "AI for Good"?**
A model learns the history inside its data. The Titanic model finds 96% of the women who survived but only 12% of the men, and it serves 3rd class worst. Used to decide who gets help first today, it would automate 1912's unfair rules with confidence. In healthcare the same thing can happen when a model trained on one hospital's patients is used on another population. That's why you check results per group, and why a doctor, not the model, makes the decision.

**AI use:** I used Claude (Anthropic) to help write and run the notebook code and to word the reflections. All numbers come from actually running the notebook in Colab, and I checked that the answers match the outputs.

