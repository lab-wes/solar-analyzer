import streamlit as st
import pytesseract
from PIL import Image
import io, os, re
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

st.set_page_config(page_title='Solar Bill Analyzer', layout='wide')
LEADS_CSV = 'leads.csv'

def preprocess(img): return img.convert('L')

def ocr_image(img):
    return pytesseract.image_to_string(preprocess(img), config='--psm 11')

def parse_data(text, utility):
    # Standardize Extraction
    money = re.findall(r'\$?(\d{1,4}\.\d{2})', text)
    money_floats = [float(m) for m in money if 10.00 < float(m) < 5000.00]
    total_charges = money_floats[-1] if money_floats else 0.0
    
    kwh = re.findall(r'(\d{3,4})\s*kwh', text, re.I)
    total_kwh = float(kwh[0]) if kwh else 0.0
    
    # Calculate estimates
    avg_rate = total_charges / total_kwh if total_kwh > 0 else 0
    annual_kwh = (total_kwh * 6) if utility == 'LADWP' else (total_kwh * 12)
    
    return {'bill_amount': total_charges, 'current_kwh': total_kwh, 'avg_rate': avg_rate, 'annual_kwh': annual_kwh}

def make_pdf(data, solar):
    doc = SimpleDocTemplate("solar_report.pdf", pagesize=letter)
    story = [Paragraph("Solar Savings Report", getSampleStyleSheet()['Title'])]
    rows = [['Bill Amount', f"${data['bill_amount']:.2f}"], ['Annual kWh', f"{data['annual_kwh']:.0f}"], 
            ['Avg Rate', f"${data['avg_rate']:.3f}/kWh"], ['System Size', f"{solar['system_kw']:.2f} kW"]]
    story.append(Table(rows))
    doc.build(story)
    with open("solar_report.pdf", "rb") as f: return f.read()

st.title('Solar Bill Analyzer')
utility = st.radio("Select Utility", ("SCE", "LADWP"))
files = st.file_uploader('Upload bill pages', accept_multiple_files=True)
contact = st.text_input('Phone or email for report')

if files:
    all_text = '\n'.join([ocr_image(Image.open(io.BytesIO(f.read()))) for f in files]).lower()
    data = parse_data(all_text, utility)
    annual_kwh = data['annual_kwh'] * 1.10
    solar = {'system_kw': annual_kwh / (365 * 5 * 0.8), 'fixed_monthly': (annual_kwh/12) * (data['avg_rate']*0.75)}

    st.subheader('Results')
    cols = st.columns(3)
    cols[0].metric('Bill Amount', f"${data['bill_amount']:.2f}")
    cols[1].metric('Est. Fixed Monthly', f"${solar['fixed_monthly']:.2f}")
    cols[2].metric('Proposed System', f"{solar['system_kw']:.2f} kW")
    
    if st.button('Generate Report') and contact:
        pdf = make_pdf(data, solar)
        st.download_button('Download PDF report', pdf, "solar_report.pdf")
        pd.DataFrame([data | solar | {'contact': contact}]).to_csv(LEADS_CSV, mode='a', header=not os.path.exists(LEADS_CSV))
        st.success('Report created and saved!')
