import streamlit as st
import pytesseract
from PIL import Image
import io, re
import pandas as pd

st.set_page_config(page_title='Solar Bill Analyzer', layout='wide')

def preprocess(img): return img.convert('L')
def ocr_image(img): return pytesseract.image_to_string(preprocess(img), config='--psm 11')

def parse_data(text, utility):
    # Total Bill Amount
    total_match = re.search(r'total.*?\$?\s*(\d{1,4}\.\d{2})', text, re.I | re.S)
    bill_amount = float(total_match.group(1)) if total_match else 0.0
    
    # Bill Usage (kWh)
    kwh_match = re.search(r'(?:total\s*used|total\s*kwh\s*used|usage).*?(\d{3,4})', text, re.I | re.S)
    bill_usage = float(kwh_match.group(1)) if kwh_match else 0.0
    
    # 12-Month Logic
    annual_usage = (bill_usage * 6) if utility == 'LADWP' else (bill_usage * 12)
    
    # Financials
    avg_rate = bill_amount / bill_usage if bill_usage > 0 else 0
    est_annual_cost = bill_amount * (6 if utility == 'LADWP' else 12)
    monthly_avg = bill_amount if utility == 'SCE' else (bill_amount / 2)
    
    # Solar Proposal: 10% more energy, 25% cheaper rate
    target_annual_kwh = annual_usage * 1.10
    target_rate = avg_rate * 0.75
    system_kw = target_annual_kwh / (365 * 5 * 0.8)
    fixed_monthly = (target_annual_kwh / 12) * target_rate
    
    return {
        'bill_amount': bill_amount, 'bill_usage': bill_usage, 'annual_usage': annual_usage,
        'est_annual_cost': est_annual_cost, 'monthly_avg': monthly_avg, 'avg_rate': avg_rate,
        'system_kw': system_kw, 'fixed_monthly': fixed_monthly, 'target_rate': target_rate
    }

st.title('Solar Bill Analyzer')
utility = st.radio("Select Utility", ("SCE", "LADWP"))
files = st.file_uploader('Upload bill pages', accept_multiple_files=True)

if files:
    all_text = '\n'.join([ocr_image(Image.open(io.BytesIO(f.read()))) for f in files]).lower()
    data = parse_data(all_text, utility)

    st.subheader('Current Bill Summary')
    c1, c2, c3 = st.columns(3)
    c1.metric('Bill Amount', f"${data['bill_amount']:.2f}")
    c2.metric('Usage (kWh)', f"{data['bill_usage']:.0f}")
    c3.metric('Avg Rate', f"${data['avg_rate']:.3f}/kWh")
    
    c1, c2, c3 = st.columns(3)
    c1.metric('Annual Usage', f"{data['annual_usage']:.0f} kWh")
    c2.metric('Est. Annual Cost', f"${data['est_annual_cost']:.2f}")
    c3.metric('Est. Monthly Avg', f"${data['monthly_avg']:.2f}")

    st.subheader('Solar Proposal')
    col1, col2, col3 = st.columns(3)
    col1.metric('Recommended System', f"{data['system_kw']:.1f} kW")
    col2.metric('New Fixed Monthly', f"${data['fixed_monthly']:.2f}")
    col3.metric('Target Rate', f"${data['target_rate']:.3f}/kWh")
    st.info("Proposed solar system includes 10% more energy production and a 25% rate reduction.")
