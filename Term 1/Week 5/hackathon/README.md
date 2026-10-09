# Hackathon 5: Model Showdown. Who misses the extra grant?

**SDG 8: Decent Work and Economic Growth** | AI for Good | Dylan Dinh Duy and Nina Borutyńska

A Jupyter notebook that takes a real dataset from raw file to a fair, honest comparison of three tuned classifiers (KNN, logistic regression, random forest), and ends with a recommendation for a named user.

> **Read this first.** The data is from the **1994 US Census**, not from the Netherlands. The model predicts whether a person earns **$50K or less**. It does **not** predict who is entitled to a Dutch grant. The project applies the full method to a public dataset. It must not be used on Dutch students before it is trained again on recent Dutch data.

## 1. The problem

In the Netherlands, many students who are entitled to the **aanvullende beurs** (a supplementary grant for students whose parents have a low income) never use it.

- The CPB (Netherlands Bureau for Economic Policy Analysis), in a note from December 2020 that uses October 2018 data, found that **24%** of entitled first-year hbo/wo students do not use the grant.
- They miss about **EUR 175 per month** on average, about EUR 1.5 million per month in total.
- **41%** of the students who do not use the grant take a DUO loan instead, which must be repaid.
- DUO estimates that an information letter reduces non-use by about **15%** (a better email by about 5%), so reaching the right students matters.

Sources:

- CPB note, "Niet-gebruik van de aanvullende beurs" (December 2020): https://www.cpb.nl/sites/default/files/omnidownload/CPB-Notitie-Niet-gebruik-van-de-aanvullende-beurs.pdf
- Vox, 10 Dec 2020: https://www.voxweb.nl/nieuws/kwart-studenten-laat-aanvullende-beurs-ten-onrechte-links-liggen
- TU/e Cursor, 22 Nov 2021: https://www.cursor.tue.nl/nieuws/2021/november/week-4/aanvullende-beurs-vaker-aangevraagd-na-brief-van-duo/

## 2. SDG 8: why this problem, and who benefits

SDG 8 is about decent work and economic security. Students from low-income families who miss the grant lose about EUR 175 a month, which can mean extra loans (41% of them borrow from DUO instead) or even dropping out. Helping them claim money they are entitled to gives them a fairer start before their working life begins.

**Who benefits:** first-year students from low- and middle-income families, who would hear about money they are entitled to, and DUO, which reaches them with fewer wasted letters (see section 9).

## 3. What the model predicts

- **Target:** `income`, whether a person earns more than $50K a year.
- **Positive class:** `<=50K` (low income). Low income is a stand-in for "parents with a low income, so the child may be entitled to the grant".
- **Population match: no.** The dataset describes US adults in 1994. Nobody from the Netherlands is in it, and $50K in 1994 is not the DUO income limit. A real DUO tool would need recent Dutch data, which is not public for privacy reasons.

## 4. User and conditions of use

**Intended user:** a DUO team member who decides which students get an information letter about the grant.

**Situation and needs:** limited budget for letters and staff time. They need a ranked list of students whose parents are probably low income, and they must be able to explain to a student why they did or did not get a letter.

**Conditions of use:**

- The model only decides who gets a letter. DUO checks the real income and decides entitlement.
- The letter cannot be the only way students hear about the grant.
- Do not use the model on Dutch students before it is trained again on recent Dutch data.

**Not the intended user / not in the data:** anyone outside the 1994 US adult population. There are no Dutch families, no recent data, and no students (the data is about adults). The model sees one person's data, not a household. Never use it to refuse a grant.

## 5. Dataset card

| Item | Value |
|---|---|
| Name | UCI Adult (Census Income) |
| Source | UCI Machine Learning Repository: https://archive.ics.uci.edu/dataset/2/adult |
| Collected by | Extracted from the 1994 US Census database by Barry Becker (donated to UCI by Becker and Kohavi) |
| Licence | CC BY 4.0 |
| Size | 48,842 rows, 15 columns (14 features and the target) |
| Target | `income`: `<=50K` 76.1%, `>50K` 23.9% |
| Missing values | `workclass`, `occupation`, `native-country` (stored as empty cells and as `?`) |
| Duplicates | 52 rows, removed before the split |
| Dropped columns | `fnlwgt` (a census weight, not a trait of the person), `education` (same information as `education-num`) |
| Known limits | 1994 US data. Sex and race are columns. 99,999 in `capital-gain` and 99 in `hours-per-week` look like form limits. |

## 6. Solution, step by step

**Input:** one person's record: `age`, `workclass`, `education-num`, `marital-status`, `occupation`, `relationship`, `race`, `sex`, `capital-gain`, `capital-loss`, `hours-per-week` and `native-country` (12 features).

**Output:** the predicted class (low income or not) and the probability of low income. DUO ranks people by that probability.

**Where scikit-learn is used:** `train_test_split`, `Pipeline` and `ColumnTransformer` (impute, scale, one-hot encode), `DummyClassifier`, `KNeighborsClassifier`, `LogisticRegression`, `RandomForestClassifier`, `GridSearchCV` with `StratifiedKFold`, and the scoring functions. Without it there is no prediction step.

**Steps:**

1. **Frame the problem.** The main metric is balanced accuracy (see section 8).
2. **Explore the data.** Fix the `<=50K.` / `<=50K` labels, turn `?` into real missing values, check duplicates, impossible values and groups.
3. **Split first.** 20% test set, stratified, `random_state=42`. The test set is used once, at the end.
4. **Pre-process inside a Pipeline.** Median impute and scale the numbers. Most-frequent impute and one-hot encode the categories. Everything is learned from the training data only.
5. **Baseline.** A `DummyClassifier` that always says "low income".
6. **Tune with 5-fold cross-validation** on the training set only, with the same folds and metric for all models:
   - KNN: `n_neighbors`
   - Logistic regression: `C`, `class_weight`
   - Random forest: `max_depth`, `class_weight`
7. **Evaluate once on the test set.**
8. **Look at the errors,** including results per sex and race.
9. **Recommend** a model.
10. **Use it:** predict a made-up parent.

## 7. Results

Test set: 9,758 people (7,422 low income, 2,336 higher income). Numbers are from the notebook's saved outputs.

| Model | Best settings | CV balanced accuracy (mean ± std) | Test balanced accuracy | Test precision | Test recall | Test F1 |
|---|---|---|---|---|---|---|
| Baseline (always "low income") | - | 0.500 ± 0.000 | 0.500 | 0.761 | 1.000 | 0.864 |
| KNN | n_neighbors=31 | 0.766 ± 0.006 | 0.770 | 0.884 | 0.925 | 0.904 |
| Logistic regression | C=10, balanced | 0.820 ± 0.005 | 0.823 | 0.944 | 0.795 | 0.863 |
| **Random forest** | max_depth=20, balanced | **0.826 ± 0.006** | **0.827** | 0.938 | 0.830 | 0.881 |

Confusion matrix of the random forest on the test set:

| | Model says low income | Model says higher income |
|---|---|---|
| **Really low income (7,422)** | 6,163 found | **1,259 missed** |
| **Really higher income (2,336)** | 410 get a letter by mistake | 1,926 correctly left out |

## 8. Why balanced accuracy and not recall

76% of the people are low income. A baseline that says "low income" for everyone has recall 1.0 without learning anything, so recall cannot show whether a model is better than doing nothing. Balanced accuracy is the average of the share of low-income people found and the share of higher-income people correctly left out. It gives the baseline 0.5, so every model has to beat 0.5. Recall, precision and F1 are still reported in every table.

## 9. Recommended model: random forest, with conditions

- The random forest and logistic regression are tied on the main metric (0.826 vs 0.820, spread about 0.006). The random forest finds more low-income people (recall 0.830 vs 0.795), which is 264 more students in the test set.
- Logistic regression is easier to explain. It is a reasonable alternative with almost the same score.
- KNN has the highest recall (0.925), but it sends a letter to 38% of the higher-income people and has the lowest main score.
- The random forest overfits somewhat (train 0.902, CV 0.826), but it is still best on new data: its test score (0.827) matches cross-validation (0.826).

**Why not the simpler alternative?** The simplest option is the baseline: send everyone a letter. It reaches every low-income person, but in the test set it wastes a letter on all 2,336 higher-income people. The random forest reaches 83% of the low-income people and wastes only 410 letters, which is 82% fewer. The price is that it misses 17% that a letter to everyone would have reached.

**Why a model if DUO knows the parents' income?** DUO only checks the real income after a student applies. The model is for the step before that: deciding whom to write to. It does not replace the income check. A real version could only use information DUO already has before an application, so it would be trained on that kind of data and not on census records of adults, which is why our dataset is a stand-in.

**Conditions:** because of those misses, the letter cannot be the only channel. A false positive costs little, so DUO could send the letter at a probability below 50%. That threshold has to be chosen with cross-validation, which we did not do. The model must be trained again on recent Dutch data before any real use.

## 10. Ethical reflection

The model is trained on US adults from the 1994 Census (UCI Adult, CC BY 4.0, 48,842 rows), so it says nothing about Dutch students and must not be used on them until it is trained again on recent Dutch data.

**Sex and race are features in the model.** Low income is much more common among women (89%) than men (70%), and among Black (88%) than White (75%) people in the data, and the model learns these patterns.

| Group | People in test set | Low-income people found (recall) | Higher-income people correctly left out | Balanced accuracy |
|---|---|---|---|---|
| Women | 3,274 | 0.963 | 0.628 | 0.796 |
| Men | 6,484 | 0.745 | 0.861 | 0.803 |
| White | 8,342 | 0.813 | 0.838 | 0.826 |
| Black | 962 | 0.933 | 0.649 | 0.791 |
| Asian-Pac-Islander | 300 | 0.857 | 0.750 | 0.804 |

The Amer-Indian-Eskimo (83 people) and Other (71 people) groups are too small in the test set to conclude anything. We checked sex and race. We did not check age groups or native country, so we cannot say whether the model makes more mistakes for younger or older people, or for migrants.

**What the errors show.** The random forest misses 1,259 of the 7,422 low-income people (17%). 96% of the missed people are married and 91% are men, so the model has learned "married man with a full-time job = high income" and misses low-income families who fit that picture.

**What it costs people.** A missed student gets no letter and may miss money they are entitled to. A false positive only costs a letter. That is why we chose balanced accuracy and a probability threshold below 50% as a next step.

**Hidden sensitive columns.** Removing sex and race would not remove them: columns such as marital status and occupation can stand in for them.

**Privacy, consent and licence.** Income is personal data. The people in the data answered a census, not a survey for this project, so they were not asked about this use. We use only a public, anonymised dataset. Its licence (CC BY 4.0) allows reuse with credit, and we credit the source below.

**What we would do next.** Train again on recent Dutch data, test without sex and race, repeat the per-group check (and add age), and choose the probability threshold with cross-validation.

**Who must not use this model:** anyone who would use it to refuse or reduce a grant, or on people outside the 1994 US adult population.

## 11. Using the model

The last cell predicts a made-up parent: a 46-year-old divorced woman who works 32 hours a week in a service job. The model returns "low income, send the letter" with a probability of 99%. DUO should always see the probability, because 55% and 99% are different messages.

## 12. How to run

The notebook runs in **Google Colab** without extra installs: open `hackathon5_model_showdown.ipynb` and choose **Runtime > Run all**. If `adult.csv` is not next to the notebook, the first data cell downloads it from the UCI repository.

To run it on your own computer:

```bash
pip install pandas numpy scikit-learn matplotlib jupyter
jupyter notebook hackathon5_model_showdown.ipynb
```

- The saved outputs and every number in the tables come from Python 3.9, pandas 2.3.3, scikit-learn 1.6.1, numpy 2.0.2 and matplotlib 3.9.4. The notebook was also run end to end with Python 3.13, pandas 3.0.6, scikit-learn 1.9.1, numpy 2.5.3 and matplotlib 3.11.2.
- **pandas 3 note:** in step 6 the plot cell uses `.map(str)` instead of `.astype(str)` (two places), because `astype(str)` turns `max_depth=None` into a missing value in pandas 3. With `.astype(str)` the notebook stops with a `TypeError` on pandas 3.
- A full run takes about 15 minutes, mostly the tuning of KNN and the random forest. The tuning cell uses `n_jobs=2`. On a computer with many cores you can raise it (for example to `n_jobs=-1`) to run faster, but on a small laptop `-1` can freeze the computer. The results do not change.
- With newer library versions the numbers can differ slightly (for example, the random forest recall was 0.809 instead of 0.830, and the best KNN setting was `n_neighbors=21`). The ranking of the models stays the same. The tables in this README are from the notebook's saved outputs.

## 13. Files

- `hackathon5_model_showdown.ipynb`: the notebook
- `adult.csv`: the data (5 MB, CC BY 4.0)
- `Hackathon5_slides.pptx`: the slides for the presentation
- `README.md`: this file

## 14. AI use and credits

**AI use:** Claude (Anthropic) helped write the notebook code, this README and the slides, was used to review the notebook, and tested that the notebook runs. All numbers in this README come from the notebook's saved outputs and were checked against them.

**Credits:** Data: Becker, B. and Kohavi, R. (1996). Adult. UCI Machine Learning Repository. CC BY 4.0. Tool: scikit-learn (https://scikit-learn.org/stable/).
