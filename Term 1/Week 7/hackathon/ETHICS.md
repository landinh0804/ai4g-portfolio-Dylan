# Ethical reflection and data card

## What data did we collect and how?
- Own photos: none. It is autumn, the plants are dying back, and we had no photos of our own.
- Scraped photos: 415 images from iNaturalist (215 Japanese knotweed, 200 giant hogweed). Only research grade observations in the Netherlands with a CC BY or CC BY-NC licence were used, taken through the public iNaturalist API, at most 3 photos per observation, medium size. Autumn and winter observations were picked first, then spring and summer. Author, licence and source link of every image are in `data/sources.csv`.
- Labels: the boxes were drawn by Roboflow Auto Label (a Gemini based model), not by hand. We opened and checked 14 of the 415 images, found one stray box and deleted it, then approved all of them. The other images were not checked one by one, so some boxes are probably wrong.
- Split: 291 train, 83 valid, 41 test, chosen at random by image. Photos of the same observation can land in different sets, which can make the test scores look better than they would be on truly new places.
- People and private land: we did not check every photo for faces or gardens. The photos are public, openly licensed and shown at medium size only. The app does not store uploaded photos.

## Limitations and failure modes
- Test results on 41 images: mAP@50 90.5%, precision 98.0%, recall 82.5%. Those labels also came from Auto Label, so the model is partly graded against another AI. Treat the numbers as promising, not as field accuracy.
- Recall is lower than precision: about 1 in 6 plants is missed.
- Unseen photo check: three new photos that were not in the dataset (one hogweed, two knotweed) all got the right class, at 90%, 93% and 99% confidence. On one knotweed photo the box covered only the upper part of the plant. Three photos is a sanity check, not an evaluation. Every Dutch knotweed observation with a CC BY or CC BY-NC licence was already in the dataset, so the two knotweed test photos come from other licences and are not in this repository (see `data/unseen_sources.csv`).
- Seasonal bias: we picked autumn and winter photos first, but we did not measure how well the model works per season, for example on dead knotweed canes.
- Look-alikes: other tall plants with white umbels (for example giant cow parsley, angelica) or other knotweed hybrids could be confused with the two classes. We did not test them, so we do not know how often this happens.
- Narrow conditions: only Dutch locations, only two classes, a small test set, and mostly photos taken by iNaturalist users who already knew what they were photographing. Boxes on wide shots cover whole stands, not single plants.
- Confidence is not truth: a low score or an empty result does not prove a plant is absent.

## What could go wrong if deployed for real decisions?
- A false positive could lead to needless removal or spraying of a native plant, or a wrongly accused landowner.
- A false negative could let an invasive plant spread unnoticed.
- Dangerous plants: giant hogweed sap burns skin. The app must never encourage touching or approaching it.
- Mitigation: a human expert confirms every detection before any action, and the app states that it is a screening aid.
