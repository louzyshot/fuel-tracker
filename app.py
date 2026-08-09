import streamlit as st
from google import genai
from google.genai import types
import json
import pandas as pd
from datetime import datetime
import os
import gspread
from google.oauth2.service_account import Credentials

# Page Configuration for Mobile
st.set_page_config(page_title="Fuel & Distance Tracker", page_icon="⛽", layout="centered")

st.title("⛽ Fuel & Distance Tracker")
st.write("Upload receipts and odometer photos to log fill-ups directly to Google Sheets.")

# API Keys & Credentials
api_key = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else os.environ.get("GEMINI_API_KEY")

# Google Sheets Helper Function
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

def load_sheet_data():
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(st.secrets["SPREADSHEET_ID"]).worksheet("Logs")
        data = sheet.get_all_records()
        return pd.DataFrame(data), sheet
    except Exception as e:
        st.error(f"Google Sheets Connection Error: {e}")
        return pd.DataFrame(), None

# Image Processing Function with Fallback Models
def extract_data_with_gemini(client, receipt_file, odo_file):
    prompt = """
    Analyze the provided images carefully:
    1. Receipt / Fuel Display Image: Extract fuel_type, unit_price, volume, total_price, and purchase date (YYYY-MM-DD).
    2. Odometer Dashboard Image (if provided): Extract current odometer reading (numeric value only, e.g. 45210).

    Return strictly a raw JSON object with keys:
    "date", "fuel_type", "unit_price", "volume", "total_price", "odometer"

    If a value cannot be found, use null. Do not wrap in markdown or extra text.
    """
    
    contents = []
    if receipt_file:
        contents.append(types.Part.from_bytes(data=receipt_file.getvalue(), mime_type=receipt_file.type or "image/jpeg"))
    if odo_file:
        contents.append(types.Part.from_bytes(data=odo_file.getvalue(), mime_type=odo_file.type or "image/jpeg"))
    contents.append(prompt)

    candidate_models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']
    
    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(response.text), model_name
        except Exception:
            continue
    return None, "Failed on all models"

# UI Layout: Dual Photo Upload
st.subheader("1. Capture / Upload Images")
col1, col2 = st.columns(2)

with col1:
    receipt_img = st.file_uploader("📷 Fuel Receipt / Display", type=["jpg", "jpeg", "png"], key="receipt")
with col2:
    odo_img = st.file_uploader("🚗 Odometer Dashboard", type=["jpg", "jpeg", "png"], key="odo")

if receipt_img or odo_img:
    if st.button("Extract All Data 🪄", type="primary"):
        with st.spinner("AI analyzing receipt and odometer dashboard..."):
            try:
                client = genai.Client(api_key=api_key)
                data, used_model = extract_data_with_gemini(client, receipt_img, odo_img)
                
                if data:
                    st.session_state['extracted_all'] = data
                    st.success(f"Extracted using {used_model}!")
                else:
                    st.error("Could not process images properly.")
            except Exception as e:
                st.error(f"Error: {e}")

# Verification & Calculation Form
if 'extracted_all' in st.session_state:
    st.subheader("2. Verify & Save to Google Sheets")
    ext = st.session_state['extracted_all']
    
    # Load previous history to calculate distance/efficiency
    df_history, sheet_ref = load_sheet_data()
    
    last_odometer = 0.0
    if not df_history.empty and 'Odometer' in df_history.columns:
        valid_odo = [float(x) for x in df_history['Odometer'].values if str(x).replace('.','',1).isdigit()]
        if len(valid_odo) > 0:
            last_odometer = valid_odo[-1]

    with st.form("verify_google_sheet_form"):
        parsed_date = ext.get('date') or str(datetime.now().date())
        try:
            default_date = datetime.strptime(parsed_date, "%Y-%m-%d")
        except ValueError:
            default_date = datetime.now()

        date = st.date_input("Date", value=default_date)
        fuel_type = st.text_input("Fuel Type", value=ext.get('fuel_type') or "Regular")
        price = st.number_input("Unit Price", value=float(ext.get('unit_price') or 0.0), format="%.3f")
        volume = st.number_input("Volume (L/Gal)", value=float(ext.get('volume') or 0.0), format="%.2f")
        total = st.number_input("Total Cost", value=float(ext.get('total_price') or 0.0), format="%.2f")
        odometer = st.number_input("Current Odometer", value=float(ext.get('odometer') or 0.0), format="%.1f")
        
        # Calculate distance and MPG/KML on the fly
        distance = max(0.0, odometer - last_odometer) if last_odometer > 0 and odometer > last_odometer else 0.0
        efficiency = (distance / volume) if volume > 0 and distance > 0 else 0.0
        
        if last_odometer > 0:
            st.caption(f"💡 Distance since last log: **{distance:.1f}** | Calculated Efficiency: **{efficiency:.2f} per unit**")

        if st.form_submit_button("Save to Google Sheets ☁️"):
            if sheet_ref:
                new_row = [
                    str(date),
                    fuel_type,
                    price,
                    volume,
                    total,
                    odometer,
                    distance,
                    round(efficiency, 2)
                ]
                sheet_ref.append_row(new_row)
                st.success("Successfully logged to Google Sheets!")
                del st.session_state['extracted_all']
                st.rerun()

# History Section from Google Sheets
st.divider()
st.subheader("3. Google Sheets History")
df_logs, _ = load_sheet_data()

if not df_logs.empty:
    st.dataframe(df_logs.sort_index(ascending=False), use_container_width=True)
else:
    st.info("No records found in Google Sheets yet.")
