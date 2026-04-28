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
    # Bill Amount
    money = re.findall(r'\$?(\d{1,4}\.\d{2})', text)
    money_floats = [float(m) for m in money if 10.00 < float(m) < 5000.00]
    bill_amount = max(money_floats) if money_floats else 0.0
    
    # ULTIMATE USAGE DETECTION - Collect ALL candidates, pick largest realistic
    candidates = []
    
    # Pattern 1: Direct kWh matches
    for pat in [r'(\d{3,4})\s*kwh', r'kwh\s+(\d{3,4})', r'(\d{3,4})\s*kWh']:
        candidates.extend(re.findall(pat, text, re.I))
    
    # Pattern 2: Comma formatted
    candidates.extend([int(''.join(m).replace(',','')) for m in re.findall(r'(\d{1,3}),(\d{3})', text)])
    
    # Pattern 3: Total usage keywords
    for pat in [r'total\s+usage[:\s]*(\d{3,4})', r'usage[:\s]*(\d{3,4})']:
        candidates.extend(re.findall(pat, text, re.I))
    
    # Convert to ints, filter realistic bill usages, pick MAX
    bill_usage = 0
    for cand in candidates:
        try:
            num = int(str(cand).replace(',',''))
            if 300 <= num <= 3000:  # SCE residential range
                bill_usage = max(bill_usage, num)
        except: pass
    
    avg_rate = bill_amount / bill_usage if bill_usage > 0 else 0
    if avg_rate > 0.80 or avg_rate < 0.10: avg_rate = 0.35
    
    annual_usage = bill_usage * 12 if utility == 'SCE' else bill_usage * 6
    est_annual_cost = bill_amount * 12 if utility == 'SCE' else bill_amount * 6
    monthly_avg = est_annual_cost / 12
    
    target_annual_kwh = annual_usage * 1.10
    new_rate = avg_rate * 0.75
    system_kw = target_annual_kwh / (365 * 5 * 0.8)
    fixed_monthly = (target_annual_kwh / 12) * new_rate
    
    return {
        'bill_amount': bill_amount, 'bill_usage': bill_usage, 'avg_rate': avg_rate,
        'annual_usage': annual_usage, 'est_annual_cost': est_annual_cost, 
        'monthly_avg': monthly_avg, 'system_kw': system_kw, 
        'fixed_monthly': fixed_monthly, 'new_rate': new_rate
    }

st.title('Solar Bill Analyzer')
utility = st.radio("Select Utility", ("SCE", "LADWP"))
files = st.file_uploader('Upload bill pages', accept_multiple_files=True)
contact = st.text_input('Phone or email')

if files:
    all_text = '\n'.join([ocr_image(Image.open(io.BytesIO(f.read()))) for f in files]).lower()
    data = parse_data(all_text, utility)

    st.subheader('Current Bill Summary')
    c1, c2, c3 = st.columns(3)
    c1.metric('Bill Amount', f"${data['bill_amount']:.2f}")
    c2.metric('Usage (kWh)', f"{data['bill_usage']:.0f} kWh")
    c3.metric('Avg Rate', f"${data['avg_rate']:.3f}/kWh")
    
    c1, c2, c3 = st.columns(3)
    c1.metric('Annual Usage', f"{data['annual_usage']:.0f} kWh")
    c2.metric('Est. Annual Cost', f"${data['est_annual_cost']:.2f}")
    c3.metric('Est. Monthly Avg', f"${data['monthly_avg']:.2f}")

    st.subheader('Solar Proposal')
    col1, col2, col3 = st.columns(3)
    col1.metric('Recommended System', f"{data['system_kw']:.1f} kW")
    col2.metric('New Rate', f"${data['new_rate']:.3f}/kWh")
    col3.metric('New Fixed Monthly', f"${data['fixed_monthly']:.2f}")

    if st.button('Generate Report'):
        if contact:
            pd.DataFrame([data | {'contact': contact}]).to_csv(LEADS_CSV, mode='a', header=not os.path.exists(LEADS_CSV))
            with open(LEADS_CSV, "rb") as f: st.download_button('Download Leads CSV', f, "leads.csv")
            st.success('Report created and saved!')
        else:
            st.warning("Please enter your phone or email first!")
