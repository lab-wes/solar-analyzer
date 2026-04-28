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
def ocr_image(img): return pytesseract.image_to_string(preprocess(img), config='--psm 11')

def parse_data(text, utility):
    # LOOK FOR TOTAL: Finds "total" then the next dollar amount
    total_match = re.search(r'total.*?\$?\s*(\d{1,4}\.\d{2})', text, re.I | re.S)
    total_charges = float(total_match.group(1)) if total_match else 0.0
    
    # LOOK FOR KWH: Find "total used" then the next 3-4 digit number
    kwh_match = re.search(r'(?:total\s*used|total\s*kwh\s*used|usage).*?(\d{3,4})', text, re.I | re.S)
    total_kwh = float(kwh_match.group(1)) if kwh_match else 0.0
    
    # Logic: SCE monthly, LADWP bi-monthly
    avg_rate = total_charges / total_kwh if total_kwh > 0 else 0
    annual_kwh = (total_kwh * 6) if utility == 'LADWP' else (total_kwh * 12)
    
    return {'bill_amount': total_charges, 'current_kwh': total_kwh, 'avg_rate': avg_rate, 'annual_kwh': annual_kwh, 'utility': utility}

def make_pdf(data, solar):
    doc = SimpleDocTemplate("solar_report.pdf", pagesize=letter)
    story = [Paragraph("Solar Savings Report", getSampleStyleSheet()['Title']), Spacer(1, 0.2*inch)]
    rows = [['Bill Amount', f"${data['bill_amount']:.2f}"], ['Annual kWh', f"{data['annual_kwh']:.0f}"], 
            ['Avg Rate', f"${data['avg_rate']:.3f}/kWh"], ['System Size', f"{solar['system_kw']:.2f} kW"],
            ['New Fixed Monthly', f"${solar['fixed_monthly']:.2f}"]]
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
        st.success('Report created!')
