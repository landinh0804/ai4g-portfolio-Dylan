# Model cards: summary and assessment

Both models are downloaded from the Hugging Face Hub at a **pinned commit** and run
locally on CPU with `transformers` (see `pulse/sentiment.py`). Sources were read on
2026-10-09.

| | Model 1 | Model 2 |
|---|---|---|
| Hub ID | `oliverguhr/german-sentiment-bert` | `cardiffnlp/twitter-xlm-roberta-base-sentiment` |
| Pinned revision | `b1177ff5` | `f2f1202b` (tokenizer: `FacebookAI/xlm-roberta-base@e73636d4`) |
| Architecture | BERT-base (German) | XLM-RoBERTa-base, further pre-trained on tweets |
| Training data | 1.834 M German samples: Twitter, Facebook, movie / app / hotel reviews, plus Wikipedia sentences as "neutral" (Guhr et al., LREC 2020) | ~198 M multilingual tweets for domain pre-training; sentiment fine-tuning on tweets in 8 languages: ar, en, fr, **de**, hi, it, es, pt (Barbieri et al., LREC 2022, "XLM-T") |
| Languages | German only | Multilingual (8 fine-tuned, usable beyond) |
| Labels (raw) | `positive`, `negative`, `neutral` | `negative`, `neutral`, `positive` |
| Our labels | lower-cased, identical | lower-cased, identical |
| Max input | 512 tokens | 512 tokens (514 positions incl. specials) |
| Licence | **MIT** (Hub tag) | **No licence on the Hub card.** The accompanying code repo `cardiffnlp/xlm-t` is Apache-2.0. The base model XLM-R is MIT. |
| Reported quality | F1 micro 0.96 overall, but **0.74 on SB10k** and **0.68 on PotTS**, the two German *Twitter* sets, i.e. the domain closest to ours | Per-language results in the XLM-T paper; no German-specific number on the card |
| Preprocessing | Card says inputs must be cleaned like the training data. We re-implement `germansentiment.clean_text`: remove URLs and @mentions, digits to German words, **drop every character outside A-Z, umlauts, ß and space**, lower-case | Mentions to `@user`, links to `http` (from the card) |

## Things that argue against (or limit) the choice

1. **Model 1 is weaker on social media than its headline number suggests.** 0.96 F1 is
   dominated by reviews and Wikipedia. On German tweets it gets 0.68–0.74. Bluesky
   posts are closest to the tweet sets, so expect roughly that, not 0.96.
2. **Model 1's preprocessing deletes emojis and punctuation.** "Danke Deutsche Bahn 🙃"
   and "Danke Deutsche Bahn!" become the same string. Emojis and "?!" are some of the
   strongest sarcasm signals in train complaints, and sarcastic thanks ("Danke, DB") is
   very common in this domain. Expect sarcasm to be read as positive or neutral.
3. **Model 1 rarely predicts "positive".** In the first 294 test-run posts: 8 positive vs. 37
   for Model 2. Possibly real (people post when things go wrong), possibly a bias
   from the Wikipedia-as-neutral training data. The evaluation will show which.
4. **Model 2 has no licence stated on the Hub.** For a university hackathon that only
   runs the model and publishes no weights, the Apache-2.0 code repo and MIT base
   model make this low-risk. For any production use by a real DB team it would need
   clarifying with the authors.
5. **Model 2's tokenizer comes from the base model.** The Cardiff repo ships only the
   slow `sentencepiece.bpe.model`, which would need the extra `sentencepiece`
   package. Its file is byte-identical (sha256 `cfc8146a…2865`) to the one in
   `FacebookAI/xlm-roberta-base`, so we load that repo's fast `tokenizer.json`
   instead. Same vocabulary, same token ids, no extra dependency.
6. **Both models predate this data by years** (training data roughly 2018–2020). New
   vocabulary ("D-Ticket", "Generalsanierung", "Palla") is unknown to them, though
   subword tokenisation softens this.
7. **News posts describe negative events neutrally**, but both models label the
   *event* ("Stellwerk defekt") as negative. This is why the dashboard defaults to
   personal posts only, and why the evaluation splits personal vs. news.
8. **Language mix.** About 75% of our items are tagged `de`, and the rest are untagged
   or English. Model 1 is German-only, so its labels on English posts are
   unreliable. Model 2 handles both.

None of these is a reason to drop either model. Points 1–3 are exactly what the
hand-labelled evaluation (`python -m pulse.evaluate`) is designed to measure. If
Model 1 does badly on sarcasm, the dashboard can default to Model 2.

## References
- Guhr, O., Schumann, A.-K., Bahrmann, F., Böhme, H. J. (2020). *Training a Broad-Coverage German Sentiment Classification Model for Dialog Systems.* LREC 2020, pp. 1620–1625.
- Barbieri, F., Espinosa Anke, L., Camacho-Collados, J. (2022). *XLM-T: Multilingual Language Models in Twitter for Sentiment Analysis and Beyond.* LREC 2022, pp. 258–266.
