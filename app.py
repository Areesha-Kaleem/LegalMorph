import streamlit as st
from extractor.main_extraction import extractor
from transformer.main_transform import transform
from loader.main_load import load

st.set_page_config(page_title="LegalMorph Pipeline", layout="centered")

st.title("⚖️ LegalMorph Data Pipeline")
st.markdown("Welcome! Use the buttons below to process legal case data end-to-end.")

# --- Input: Number of Cases to Scrape ---
case_limit = st.number_input(
    "📄 Number of Cases to Scrape", min_value=1, max_value=1000, value=5, step=1
)

# --- Extract Button ---
if st.button("🧲 Extract Case Files"):
    with st.spinner(f"Extracting {case_limit} cases..."):
        try:
            extractor(case_limit=case_limit)
            st.success("✅ Extraction completed successfully.")
        except Exception as e:
            st.error(f"❌ Extraction failed: {e}")

# --- Transform Button ---
if st.button("🔄 Transform & Merge JSON"):
    with st.spinner("Running transformer..."):
        try:
            transform()
            st.success("✅ Transformation completed successfully.")
        except Exception as e:
            st.error(f"❌ Transformation failed: {e}")

# --- Load Button ---
if st.button("📥 Load into MongoDB"):
    with st.spinner("Loading into MongoDB..."):
        try:
            load()
            st.success("✅ JSONs loaded into MongoDB.")
        except Exception as e:
            st.error(f"❌ Loading failed: {e}")
