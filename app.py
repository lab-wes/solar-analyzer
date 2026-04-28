import streamlit as st
import pytesseract
from PIL import Image
import io, os, re
import pandas as pd
import numpy as np
from pdf2image import convert_from_bytes
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

st.set_page_config(page_title='Solar Bill Analyzer', layout='wide')
CALENDLY_LINK = 'https://calendly.com/your-link'
LEADS_CSV = 'leads.csv'

def preprocess(img):
    return img.convert('L')

def ocr_image(img):
    # PSM 11 for flexible, sparse text reading
    return pytesseract.image_to_string(preprocess(img), config='--psm 11')

def get_pages(file_bytes, filename):
    if filename.lower().endswith('.pdf'):
        return convert_from_bytes(file_bytes)
    return [Image.open(io.BytesIO(file_bytes))]

def load_bill_pages(files):
    pages = []
    for f in files:
        raw = f.read()
        for img in get_pages(raw, f.name):
            text = ocr_image(img)
            pages.append({'text': text.lower()})
    return pages

def parse_sce_data(text):
    bill_amount = re.findall(r'\$?(\d{1,4}\.\d{2})', text)
    bill_amount = float(bill_amount[-1]) if bill_amount else 0.0
    kwh = re.findall(r'(\d{3,4})\s*kwh', text, re.I)
    current_kwh = float(kwh[0]) if kwh else 0.0
    return {'bill_amount': bill_amount, 'current_kwh': current_kwh, 'avg_rate': bill_amount/current_kwh if current_kwh else 0}

def parse_ladwp_data(text):
    money = re.findall(r'\$?(\d{1,4}\.\d{2})', text)
    money_floats = [float(m) for m in money if 10.00 < float(m) < 5000.00]
    total_charges = money_floats[-1] if money_floats else 0.0
    kwh = re.findall(r'(\d{3,4})\s*kwh', text, re.I)
    total_kwh = float(kwh[0]) if kwh else 0.0
    return {'bill_amount': total_charges, 'current_kwh': total_kwh, 'avg_rate': total_charges/total_kwh if total_kwh else 0}

def solar_estimate(data):
    annual_kwh = (data['current_kwh'] * 12) * 1.10
    target_rate = data['avg_rate'] * 0.75
    return {'system_kw': annual_kwh / (365 * 5 * 0.8), 'fixed_monthly': (annual_kwh / 12) * target_rate, 'target_rate': target_rate}

st.title('Solar Bill Analyzer')
utility_choice = st.radio("Select Utility", ("SCE", "LADWP"))
files = st.file_uploader('Upload bill pages', accept_multiple_files=True)

if files:
    pages = load_bill_pages(files)
    all_text = '\n'.join(p['text'] for p in pages)
    st.sidebar.write(f"OCR SAMPLE: {all_text[:150]}")
    
    data = parse_sce_data(all_text) if utility_choice == 'SCE' else parse_ladwp_data(all_text)
    solar = solar_estimate(data)

    st.subheader('Results')
    cols = st.columns(3)
    cols[0].metric('Bill Amount', f"${data.get('bill_amount', 0):.2f}")
    cols[1].metric('Est. Monthly', f"${solar['fixed_monthly']:.2f}")
    cols[2].metric('System Size', f"{solar['system_kw']:.2f} kW")
    
    if st.button('Generate Report'):
        st.success('Report successfully analyzed!')
