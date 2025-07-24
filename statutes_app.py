import streamlit as st
from extractor.main_statutes_extractor import run_statute_scraper
from transformer.main_statutes_transform import transform_statute

st.set_page_config(page_title="LegalMorph Statutes Pipeline", layout="centered")

st.title("📚 LegalMorph Statutes Pipeline")
st.markdown("This interface runs the Statutes pipeline in phases. Use the buttons below to execute each phase.")

# --- Input: Number of Statutes to Scrape ---
statute_limit = st.number_input(
    "📑 Number of Statutes to Scrape", min_value=1, max_value=1000, value=10, step=1
)

# --- Extract Button ---
if st.button("🧲 Extract Statutes"):
    with st.spinner(f"Extracting {statute_limit} statutes..."):
        try:
            run_statute_scraper(limit=statute_limit)
            st.success("✅ Statutes extracted successfully.")
        except Exception as e:
            st.error(f"❌ Extraction failed: {e}")

# --- Transform Button ---
if st.button("🔄 Transform Statutes (Raw → Custom → Base → Merged)"):
    with st.spinner("Transforming statute JSONs..."):
        try:
            transform_statute()
            st.success("✅ Transformation completed successfully.")
        except Exception as e:
            st.error(f"❌ Transformation failed: {e}")



