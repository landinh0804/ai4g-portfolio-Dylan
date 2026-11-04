# Hackathon 5: Who will miss their next credit card payment?
SDG 8 | AI for Good | Dylan Dinh Duy & Nina Borutyńska
## The problem
If someone misses a credit card payment, the debt gets bigger, and after a few months it can turn into a debt spiral. That's what happened in Taiwan in 2005 and 2006. There was a big credit card debt crisis and more than half a million people couldn't pay back their loans ([Seven Pillars Institute](https://sevenpillarsinstitute.org/case-studies/taiwans-credit-card-crisis)). In our data, 22% of the clients miss their next payment.
## User and decision
Our user is the collections team of a bank in Taiwan. They don't have time to call every client every month, so they have to choose. Our model helps them decide who to call first and offer a repayment plan to.
We think the data fits this user well. It comes from the same kind of bank and the same kind of clients (credit card clients of a bank in Taiwan). The big difference is time: the data is from 2005, so a bank today would need newer data.
The people affected are the clients. A call can really help them, but it can also feel like pressure.
Some people are not in the data at all: people who were refused a card, clients of other banks, people in other countries, and anyone after 2005.
The model must NOT be used to refuse credit, raise fees or put pressure on clients.
## Why SDG 8
SDG 8 is about decent work and economic growth, and economic security is part of that. If the bank helps people early, their debt doesn't have time to grow. This is good for the clients at risk, and also for the bank, because they waste fewer calls.
## Dataset
| | |
|---|---|
| Name | Default of Credit Card Clients (UCI) |
| Link | https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients |
| Collected by | Yeh & Lien (2009), clients of one bank in Taiwan |
| How it was collected | Credit card records of the bank's clients: credit limit, personal info (sex, education, marriage, age), and 6 months of payment status, bills and payments |
| Time | April to September 2005 |
| Licence | CC BY 4.0 |
| Size | 30,000 rows, 23 features + ID + target |
| Target | default payment next month (1 = misses the payment). 22% yes, 78% no |
| Cleaning | We removed 35 duplicate rows and dropped the ID column |
| Limits | The data is old (2005) and comes from one bank in one country. EDUCATION has some strange codes (0, 5, 6) and MARRIAGE has 0. There are only a few of them, so we put them in the "other" group that already exists (EDUCATION 4, MARRIAGE 3). |
## Our solution, step by step
**Input:** data about one client: credit limit, sex, education, marriage, age, and the last 6 months of payment status, bills and payments.
**Output:** the chance that the client misses the next payment, plus advice: call or don't call.
1. We wrote down the problem and who it's for.
2. We explored the data and removed the 35 duplicate rows before splitting.
3. We split the data 80/20 (stratified, random_state=42).
4. We built a Pipeline. Sex, education and marriage go through one-hot encoding, and all the other columns get scaled.
5. We made a baseline and a simple rule, so we had something to compare with.
6. We tuned the models with 5-fold cross-validation and used F1 as the score. For KNN we tried n_neighbors from 5 to 51, for logistic regression C from 0.0001 to 1, and for random forest max_depth 4 and 8 with min_samples_leaf 20 and 50. Logistic regression and random forest used class_weight="balanced".
7. We tested the models on the test set, only once.
8. We looked at the mistakes the models made.
9. We picked the model we want to recommend.
10. We made a prediction for a new client.
We used scikit-learn for: Pipeline, ColumnTransformer, GridSearchCV, KNN, LogisticRegression, RandomForest, DummyClassifier and the metrics.
## Results
| Model | Best settings | CV F1 | Test precision | Test recall | Test F1 |
|---|---|---|---|---|---|
| Baseline (always pays) | - | - | 0.000 | 0.000 | 0.000 |
| KNN | n_neighbors=15 | 0.447 ± 0.020 | 0.629 | 0.340 | 0.442 |
| Logistic regression | C=0.01 | 0.481 ± 0.005 | 0.377 | 0.633 | 0.473 |
| Random forest | max_depth=8, min_samples_leaf=50 | 0.543 ± 0.007 | 0.466 | 0.611 | 0.529 |
| Simple rule (late last month) | PAY_0 ≥ 1 | - | 0.498 | 0.503 | 0.501 |
## Why we used F1
For us the worst mistake is missing someone who won't pay, because then nobody calls them and the debt just grows. But the team can't call everyone either. So we need to find a lot of the defaulters (recall) without wasting too many calls (precision), and F1 looks at both. Accuracy doesn't really help here, because a model that says "everyone pays" already gets 78%.
## Our recommendation
We recommend the random forest. It had the best F1 in cross-validation (0.54) and on the test set (0.53). We don't think it's overfitting, because the scores on the training data (0.56), in cross-validation (0.54) and on the test set (0.53) are very close to each other. It also gives a probability, so the team can start at the top of the list and work their way down.
To be honest, it's only a bit better than the simple rule (0.53 vs 0.50). When both of them make the same number of calls (1,339), the random forest finds 709 people who don't pay and the rule finds 667, so 42 more. It still misses 39% of the people who don't pay (516 of 1,326). Almost all of them (96%) paid on time last month, so they look safe. That's why the call list shouldn't be the only way the bank helps people.
Logistic regression finds more defaulters, but 62% of its calls go to people who would have paid anyway. KNN misses two thirds of the defaulters, so we don't recommend it.
## Ethics
You can find our ethical reflection in [ETHICS.md](ETHICS.md).
## How to run
1. Open the notebook in Google Colab.
2. Click Runtime > Run all.
The data loads from our GitHub repo by itself, so you don't need to install anything.
Versions: pandas 2.2.3, scikit-learn 1.6.1
## Files
- `hackathon5_credit_default.ipynb`: the notebook, with outputs saved
- `README.md`: this file
- `ETHICS.md`: the ethical reflection
- `../credit_card_default.csv`: the data (the notebook loads it from GitHub by itself)
## Credits
Data: Yeh, I. C. & Lien, C. H. (2009). Default of Credit Card Clients. UCI Machine Learning Repository. CC BY 4.0.
Taiwan credit card crisis: Seven Pillars Institute, https://sevenpillarsinstitute.org/case-studies/taiwans-credit-card-crisis
