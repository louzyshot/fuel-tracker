import streamlit as st
from google import genai
from google.genai import types
import json
import pandas as pd
from datetime import datetime
import os

# Page Configuration for Mobile
st.set_page_config(page_title="Fuel Tracker", page_icon="⛽", layout="centered")

st.title("⛽ Fuel Consumption Tracker")
st.write("Snap or upload a picture of your fuel receipt or pump screen to log your fill-up.")

# Fetch API Key from Streamlit Secrets or Environment
api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else os.environ.get("GEMINI_API_KEY")

if not api_key:
    api_key = st.sidebar.text_input("Enter Gemini API Key manually:", type="password")

# Local CSV Storage
DATA_FILE = "fuel_data.csv"

def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Date", "Fuel Type", "Price ($)", "Volume (L/Gal)", "Total Cost ($)"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# File / Camera Input
st.subheader("1. Capture Photo")
image_file = st.file_uploader("Upload or take photo...", type=["jpg", "jpeg", "png"]) or st.camera_input("Take a photo")

if image_file:
    st.image(image_file, caption="Selected Image", use_container_width=True)

if image_file and api_key:
    if st.button("Extract Fuel Data 🪄", type="primary"):
        with st.spinner("Extracting receipt data via Gemini Vision..."):
            client = genai.Client(api_key=api_key)
            mime_type = image_file.type if hasattr(image_file, "type") and image_file.type else "image/jpeg"
            image_bytes = image_file.getvalue()
            
            prompt = """
            Analyze this fuel receipt or pump screen display. Extract the following:
            - date: Date of purchase (YYYY-MM-DD format). If missing, return null.
            - fuel_type: Type of fuel (e.g., Regular, Premium, Diesel). If unknown, return "Regular".
            - unit_price: Price per liter or gallon (numeric value only).
            - volume: Amount of fuel purchased in liters or gallons (numeric value only).
            - total_price: Total cost paid (numeric value only).

            Return strictly a raw JSON object with keys: "date", "fuel_type", "unit_price", "volume", "total_price".
            Do not wrap in markdown code fences or extra text.
            """

            # Fallback array of active Gemini Flash models
            candidate_models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash-002']
            
            extracted_data = None
            last_error = None

            for model_name in candidate_models:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                            prompt
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                    extracted_data = json.loads(response.text)
                    st.session_state['data_extracted'] = extracted_data
                    st.success(f"Extraction complete using {model_name}! Verify details below.")
                    break  # Successfully processed, exit loop
                except Exception as e:
                    last_error = str(e)
                    continue  # Try next candidate model

            if not extracted_data:
                st.error(f"Failed to process image with available models. Last error: {last_error}")

elif image_file and not api_key:
    st.warning("Please provide a Gemini API Key in Streamlit Secrets or the sidebar to extract data.")

# Verification Form
if 'data_extracted' in st.session_state:
    st.subheader("2. Verify & Save Details")
    ext = st.session_state['data_extracted']
    
    with st.form("verify_form"):
        parsed_date = ext.get('date') if ext.get('date') else str(datetime.now().date())
        
        try:
            default_date = datetime.strptime(parsed_date, "%Y-%m-%d")
        except ValueError:
            default_date = datetime.now()

        date = st.date_input("Date", value=default_date)
        fuel_type = st.text_input("Fuel Type", value=ext.get('fuel_type', 'Regular'))
        price = st.number_input("Price per Unit", value=float(ext.get('unit_price') or 0.0), format="%.3f")
        volume = st.number_input("Volume (L/Gal)", value=float(ext.get('volume') or 0.0), format="%.2f")
        total = st.number_input("Total Cost", value=float(ext.get('total_price') or 0.0), format="%.2f")
        
        if st.form_submit_button("Save Entry 💾"):
            df = load_data()
            new_entry = pd.DataFrame([{
                "Date": str(date),
                "Fuel Type": fuel_type,
                "Price ($)": price,
                "Volume (L/Gal)": volume,
                "Total Cost ($)": total
            }])
            df = pd.concat([df, new_entry], ignore_index=True)
            save_data(df)
            st.success("Receipt saved successfully!")
            del st.session_state['data_extracted']
            st.rerun()

# History Table
st.divider()
st.subheader("3. Consumption Log")
history_df = load_data()

if not history_df.empty:
    st.dataframe(history_df.sort_values(by="Date", ascending=False), use_container_width=True)
    col1, col2 = st.columns(2)
    col1.metric("Total Cost", f"${history_df['Total Cost ($)'].sum():.2f}")
    col2.metric("Total Fuel", f"{history_df['Volume (L/Gal)'].sum():.2f} units")
else:
    st.info("No logs saved yet.")
