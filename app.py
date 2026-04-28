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
CALENDLY_LINK = 'https://calendly.com/your-link'

def preprocess(img): return img.convert('L')
def ocr_image(img): return pytesseract.image_to_string(preprocess(img), config='--psm 11')

def parse_data(text, utility):
    # Total Bill Amount
    total_match = re.search(r'total.*?\$?\s*(\d{1,4}\.\d{2})', text, re.I | re.S)
    bill_amount = float(total_match.group(1)) if total_match else 0.0
    
    # Bill Usage (kWh)
    kwh_match = re.search(r'(?:total\s*used|total\s*kwh\s*used|usage).*?(\d{3,4})', text, re.I | re.S)
    bill_usage = float(kwh_match.group(1)) if kwh_match else 0.0
    
    # Rates
    avg_rate = bill_amount / bill_usage if bill_usage > 0 else 0
    
    # 12-Month Annualization
    annual_usage = (bill_usage * 6) if utility == 'LADWP' else (bill_usage * 12)
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

def make_pdf(data):
    doc = SimpleDocTemplate("solar_report.pdf", pagesize=letter)
    style = getSampleStyleSheet()
    story = [Paragraph("Solar Savings Report", style['Title']), Spacer(1, 0.2*inch)]
    rows = [['Metric', 'Value'],
            ['Bill Amount', f"${data['bill_amount']:.2f}"],
            ['Annual Usage', f"{data['annual_usage']:.0f} kWh"],
            ['Avg Rate', f"${data['avg_rate']:.3f}/kWh"],
            ['Proposed System', f"{data['system_kw']:.1f} kW"],
            ['New Fixed Monthly', f"${data['fixed_monthly']:.2f}']]
    story.append(Table(rows, colWidths=[2*inch, 2*inch]))
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f'Schedule here: {CALENDLY_LINK}', style['BodyText']))
    doc.build(story)
    with open("solar_report.pdf", "rb") as f: return f.read()

st.title('Solar Bill Analyzer')
utility = st.radio("Select Utility", ("SCE", "LADWP"))
files = st.file_uploader('Upload bill pages', accept_multiple_files=True)
contact = st.text_input('Phone or email for report')

if files and contact:
    all_text = '\n'.join([ocr_image(Image.open(io.BytesIO(f.read()))) for f in files]).lower()
    data = parse_data(all_text, utility)

    c1, c2, c3 = st.columns(3)
    c1.metric('Bill Amount', f"${data['bill_amount']:.2f}")
    c2.metric('Est. Monthly', f"${data['monthly_avg']:.2f}")
    c3.metric('Avg Rate', f"${data['avg_rate']:.3f}/kWh")

    if st.button('Generate Report'):
        pdf = make_pdf(data)
        st.download_button('Download PDF report', pdf, "solar_report.pdf")
        pd.DataFrame([data | {'contact': contact}]).to_csv(LEADS_CSV, mode='a', header=not os.path.exists(LEADS_CSV))
        st.success('Report created and saved!')
