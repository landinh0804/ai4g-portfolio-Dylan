"""Invasive plant detector: upload a photo, get detections from a Roboflow model."""
import os

import streamlit as st
from inference_sdk import InferenceHTTPClient
from PIL import Image, ImageDraw

API_URL = "https://detect.roboflow.com"
CONFIDENCE_DEFAULT = 40


def get_client() -> InferenceHTTPClient:
    api_key = os.environ.get("ROBOFLOW_API_KEY") or st.secrets.get("ROBOFLOW_API_KEY", "")
    if not api_key:
        st.error("Set ROBOFLOW_API_KEY (see .env.example and README).")
        st.stop()
    return InferenceHTTPClient(api_url=API_URL, api_key=api_key)


def draw_boxes(image: Image.Image, predictions: list) -> Image.Image:
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    for p in predictions:
        x0, y0 = p["x"] - p["width"] / 2, p["y"] - p["height"] / 2
        x1, y1 = p["x"] + p["width"] / 2, p["y"] + p["height"] / 2
        draw.rectangle([x0, y0, x1, y1], outline="red", width=4)
        draw.text((x0 + 4, y0 + 4), f"{p['class']} {p['confidence']:.0%}", fill="red")
    return out


st.set_page_config(page_title="Invasive Plant Spotter", layout="centered")
st.title("Invasive Plant Spotter")
st.write(
    "Upload a photo of a plant. The model looks for invasive species in the "
    "Netherlands (Japanese knotweed and giant hogweed). It is a screening aid, not a "
    "final identification: always have an expert confirm before acting."
)

model_id = os.environ.get("ROBOFLOW_MODEL_ID", "your-project/1")
confidence = st.slider("Minimum confidence (%)", 10, 90, CONFIDENCE_DEFAULT)
upload = st.file_uploader("Photo", type=["jpg", "jpeg", "png"])

if upload:
    image = Image.open(upload)
    client = get_client()
    with st.spinner("Analysing..."):
        result = client.infer(image, model_id=model_id)
    preds = [p for p in result["predictions"] if p["confidence"] * 100 >= confidence]
    st.image(draw_boxes(image, preds), caption=f"{len(preds)} detection(s)")
    if not preds:
        st.info("Nothing found at this confidence. That does NOT prove the plant is absent.")
    for p in preds:
        st.write(f"- {p['class']}: {p['confidence']:.0%}")
