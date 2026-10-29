# Invasive Plant Spotter (Hackathon 7: Eyes on Earth)

By Dylan and Ana, HHS AI for Good 26/27.

## What it does
A computer vision model (trained in Roboflow, RF-DETR Small) that detects invasive plants in photos
taken in the Netherlands. Upload a photo in a small Streamlit app and it draws boxes
around detected plants with a confidence score.

Classes: japanese_knotweed, giant_hogweed

## Who it is for
Municipal green-space teams, water boards and volunteer groups who need to find
invasive plants early, before they spread and damage paving, dikes and native habitat.
It is a screening aid: a person confirms every finding.

## SDG
SDG 15, Life on Land (target 15.8: prevent and reduce the impact of invasive alien species).

## Dataset
- 415 images, all scraped from iNaturalist (215 knotweed, 200 hogweed), none of our own.
- Research grade observations in the Netherlands, CC BY or CC BY-NC.
- Boxes made with Roboflow Auto Label, spot-checked on 14 images.
- Random split by image: 291 train, 83 valid, 41 test.
- Every image is listed in `data/sources.csv` with author, licence and link. The images
  themselves are not in this repository.

## How to run
```bash
pip install -r requirements.txt
set ROBOFLOW_API_KEY=your_key
set ROBOFLOW_MODEL_ID=invasive-plants-nl/1
python -m streamlit run app.py
```
Copy `.env.example` for the variable names. Never commit your real key.
On macOS or Linux use `export` instead of `set`.

## Results
On the 41-image test set: mAP@50 90.5%, precision 98.0%, recall 82.5%, F1 89.4%.
The test labels also come from Auto Label, and photos of the same observation can be in
both train and test, so these numbers are probably optimistic.
Three new photos that were not in the dataset (one hogweed, two knotweed) all got the right class, at 90%, 93% and 99% confidence.

## Ethical reflection
See [ETHICS.md](ETHICS.md).
