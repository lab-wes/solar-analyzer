import streamlit as st
import pytesseract
from PIL import Image
import io, os, re
import pandas as pd

st.set_page_config(page_title='Solar Bill Analyzer', layout='wide')
LEADS_CSV = 'leads.csv'

def preprocess(img): return img.convert('L')
def ocr_image(img): return pytesseract.image_to_string(preprocess(img), config='--psm 11')

def parse_data(text, utility):
    # Total Bill: Max dollar amount > 10
    money = re.findall(r'\$?(\d{1,4}\.\d{2})', text)
    money_floats = [float(m) for m in money if 10.00 < float(m) < 5000.00]
    bill_amount = max(money_floats) if money_floats else 0.0
    
    # Usage: 3-4 digits followed by kwh
    kwh = re.findall(r'(\d{3,4})\s*kwh', text, re.I)
    bill_usage = float(kwh[0]) if kwh else 0.0
    
    # Logic: avg_rate based on total bill / total usage
    avg_rate = bill_amount / bill_usage if bill_usage > 0 else 0
    # Sanity cap: if OCR got a bad number, force a typical CA rate
    if avg_rate > 0.80 or avg_rate < 0.10: avg_rate = 0.35 
    
    annual_usage = (bill_usage * 6) if utility == 'LADWP' else (bill_usage * 12)
    est_annual_cost = bill_amount * (6 if utility == 'LADWP' else 12)
    monthly_avg = est_annual_cost / 12
    
    target_annual_kwh = annual_usage * 1.10
    system_kw = target_annual_kwh / (365 * 5 * 0.8)
    fixed_monthly = (target_annual_kwh / 12) * (avg_rate * 0.75)
    
    return {
        'bill_amount': bill_amount, 'bill_usage': bill_usage, 'annual_usage': annual_usage,
        'est_annual_cost': est_annual_cost, 'monthly_avg': monthly_avg, 'avg_rate': avg_rate,
        'system_kw': system_kw, 'fixed_monthly': fixed_monthly
    }

st.title('Solar Bill Analyzer')
utility = st.radio("Select Utility", ("SCE", "LADWP"))
files = st.file_uploader('Upload bill pages', accept_multiple_files=True)
contact = st.text_input('Phone or email')

if files:
    all_text = '\n'.join([ocr_image(Image.open(io.BytesIO(f.read()))) for f in files]).lower()
    data = parse_data(all_text, utility)

    c1, c2, c3 = st.columns(3)
    c1.metric('Bill Amount', f"${data['bill_amount']:.2f}")
    c2.metric('Est. Monthly', f"${data['monthly_avg']:.2f}")
    c3.metric('Avg Rate', f"${data['avg_rate']:.3f}/kWh")

    if st.button('Generate Report') and contact:
        pd.DataFrame([data | {'contact': contact}]).to_csv(LEADS_CSV, mode='a', header=not os.path.exists(LEADS_CSV))
        with open(LEADS_CSV, "rb") as f:
            st.download_button('Download Leads CSV', f, "leads.csv")
        st.success('Saved to leads.csv!')
