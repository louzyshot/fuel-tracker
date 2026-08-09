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

# Setup API Key
api_key = st.sidebar.text_input("Gemini API Key", type="password")
if not api_key:
    # Try reading from environment or secrets
    api_key = os.environ.get("GEMINI_API_KEY")

# Local storage setup
DATA_FILE = "fuel_data.csv"

def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Date", "Fuel Type", "Price ($)", "Volume (L/Gal)", "Total Cost ($)"])

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# Camera / File Input
st.subheader("1. Capture Photo")
image_file = st.file_input_buffer = st.camera_input("Take a photo") or st.file_uploader("Or upload image...", type=["jpg", "jpeg", "png"])

if image_file and api_key:
    if st.button("Extract Fuel Data 🪄", type="primary"):
        with st.spinner("Extracting receipt data..."):
            try:
                # Initialize Gemini client
                client = genai.Client(api_key=api_key)
                
                # Load image bytes
                image_bytes = image_file.getvalue()
                
                # Prompt setup for strict structured JSON output
                prompt = """
                Analyze this receipt or fuel pump screen. Extract the following details:
                - Date of purchase (YYYY-MM-DD format). If not found, output null.
                - Fuel type (e.g., Regular, Premium, Diesel, Unleaded 95). If unknown, return "Unknown".
                - Price per unit/gallon/liter (numeric value only).
                - Total volume/amount of fuel purchased in liters or gallons (numeric value only).
                - Total price paid (numeric value only).

                Return the response STRICTLY as a JSON object with keys:
                "date", "fuel_type", "unit_price", "volume", "total_price"
                """
                
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type=image_file.type),
                        prompt
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )

                extracted_data = json.loads(response.text)
                
                # Save to session state for manual review
                st.session_state['data_extracted'] = extracted_data
                st.success("Extraction complete! Check details below.")
                
            except Exception as e:
                st.error(f"Error processing image: {e}")

# Verification Form
if 'data_extracted' in st.session_state:
    st.subheader("2. Verify & Save Details")
    ext = st.session_state['data_extracted']
    
    with st.form("verify_form"):
        parsed_date = ext.get('date') if ext.get('date') else str(datetime.now().date())
        date = st.date_input("Date", value=datetime.strptime(parsed_date, "%Y-%m-%d") if ext.get('date') else datetime.now())
        fuel_type = st.text_input("Fuel Type", value=ext.get('fuel_type', 'Regular'))
        price = st.number_input("Price per Unit ($)", value=float(ext.get('unit_price') or 0.0), format="%.3f")
        volume = st.number_input("Volume (L/Gal)", value=float(ext.get('volume') or 0.0), format="%.2f")
        total = st.number_input("Total Cost ($)", value=float(ext.get('total_price') or 0.0), format="%.2f")
        
        if st.form_submit_button("Save to History 💾"):
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

# Data History & Analytics
st.divider()
st.subheader("3. Consumption History")
history_df = load_data()

if not history_df.empty:
    st.dataframe(history_df.sort_values(by="Date", ascending=False), use_container_width=True)
    
    col1, col2 = st.columns(2)
    col1.metric("Total Spent", f"${history_df['Total Cost ($)'].sum():.2f}")
    col2.metric("Total Fuel", f"{history_df['Volume (L/Gal)'].sum():.2f} units")
else:
    st.info("No logs saved yet.")
