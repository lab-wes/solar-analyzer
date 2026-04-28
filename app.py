import streamlit as st
import pytesseract
from PIL import Image
import io, os, re
import pandas as pd
import numpy as np
import cv2
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
    arr = np.array(img.convert('L')) # Convert to Grayscale
    # Adaptive thresholding: Great for uneven lighting (like shadows)
    th = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    return Image.fromarray(th)

def get_pages(file_bytes, filename):
    if filename.lower().endswith('.pdf'):
        return convert_from_bytes(file_bytes)
    return [Image.open(io.BytesIO(file_bytes))]

def page_number_from_text(text):
    m = re.search(r'page\s*(\d+)\s*of\s*\d+', text, re.I)
    return int(m.group(1)) if m else None

def ocr_image(img):
    text = pytesseract.image_to_string(preprocess(img), config='--psm 3')
    st.sidebar.write(f"FULL TEXT LENGTH: {len(text)}")
    return text
    
def load_bill_pages(files):
    pages = []
    for f in files:
        raw = f.read()
        for img in get_pages(raw, f.name):
            text = ocr_image(img)
            page_no = page_number_from_text(text)
            pages.append({'image': img, 'text': text.lower(), 'page_no': page_no, 'name': f.name})
    return pages

def sort_pages(pages):
    labeled = [p for p in pages if p['page_no'] is not None]
    unlabeled = [p for p in pages if p['page_no'] is None]
    return sorted(labeled, key=lambda x: x['page_no']) + unlabeled

def detect_utility(text):
    text_lower = text.lower()
    
    # LADWP is a "High Priority" lock
    if any(marker in text_lower for marker in ['electric oharges', 'water & power', 'ladwp']):
        return 'LADWP'
    
    # Only if it IS NOT LADWP, then check for SCE
    if any(marker in text_lower for marker in ['southern california edison', 'sce', 'edison']):
        return 'SCE'
        
    return 'Unknown'

def extract_money(pattern, text):
    m = re.search(pattern, text, re.I | re.S)
    return float(m.group(1).replace(',', '')) if m else None

def extract_num(pattern, text):
    m = re.search(pattern, text, re.I | re.S)
    return float(m.group(1).replace(',', '')) if m else None

def parse_name_address(text):
    name = None
    addr = None
    nm = re.search(r'\n\s*([A-Z][A-Z,\s\.\-]+?)\s*\n\s*\d+\s+\w+', text)
    if nm:
        name = nm.group(1).strip().title()
    am = re.search(r'(\d+\s+[^\n]+\n[^\n]+,\s*CA\s*\d{5}(?:-\d{4})?)', text, re.I)
    if am:
        addr = am.group(1).replace('\n', ' ').strip().title()
    return name, addr

def parse_page1(text):
    name, address = parse_name_address(text)
    bill_amount = extract_money(r'amount due\s*\$\s*([\d,]+\.\d{2})', text) or extract_money(r'total amount you owe.*?\$\s*([\d,]+\.\d{2})', text)
    service_account = extract_num(r'customer account\s*(\d+)', text)
    return {'name': name, 'address': address, 'bill_amount': bill_amount, 'service_account': service_account}

def parse_sce_page4(text):
    current_kwh = extract_num(r'total electricity you used this month in kwh\s*(\d+(?:\.\d+)?)', text)
    if current_kwh is None:
        current_kwh = extract_num(r'\b(\d+(?:\.\d+)?)\s*kwh\b', text)
    avg_daily = extract_num(r'daily average electricity usage \(kwh\).*?this year:\s*(\d+(?:\.\d+)?)', text)
    year_this = extract_num(r'this year:\s*(\d+(?:\.\d+)?)', text)
    year_last = extract_num(r'last year:\s*(\d+(?:\.\d+)?)', text)
    if avg_daily is None:
        avg_daily = year_this
    return {'current_kwh': current_kwh, 'year_this_daily_avg': year_this, 'year_last_daily_avg': year_last, 'avg_daily_kwh': avg_daily}

def parse_ladwp_page3(text):
    # Get all numbers that look like money (10.00 to 5000.00 range)
    money_matches = re.findall(r'(\d{1,4}\.\d{2})', text)
    money_floats = [float(m) for m in money_matches if 10.00 < float(m) < 5000.00]
    # The total bill charge is usually the largest number on the bill
    total_charges = max(money_floats) if money_floats else 0.0
    
    # Get all 3-4 digit numbers followed by kwh
    kwh_matches = re.findall(r'(\d{3,4})\s*kwh', text, re.I)
    total_kwh = float(kwh_matches[0]) if kwh_matches else 0.0
    
    return {
        'current_kwh': total_kwh,
        'bi_monthly_kwh': total_kwh,
        'monthly_kwh_est': total_kwh / 2,
        'avg_daily_kwh': total_kwh / 62,
        'total_charges_page3': total_charges,
        'avg_rate': (total_charges / total_kwh) if total_kwh > 0 else 0.0,
        'billing_frequency': 'bi-monthly'
    }

def parse_bill(pages):
    
    pages = sort_pages(pages)
    all_text = '\n'.join(p['text'] for p in pages)
    # DEBUG: See what utility we are actually detecting
    utility = detect_utility(all_text)
    st.sidebar.write(f"Detected Utility: {utility}")
    st.sidebar.write(f"OCR SAMPLE: {all_text[:100]}")
    page1 = next((p for p in pages if p['page_no'] == 1), pages[0])
    page3 = next((p for p in pages if p['page_no'] == 3), pages[1] if len(pages) > 1 else pages[0])
    page4 = next((p for p in pages if p['page_no'] == 4), pages[1] if len(pages) > 1 else pages[0])
    
# ... inside your LADWP check ...
    if utility == 'LADWP':
# Force the LADWP parsing flow here
# ... your parsing code ...
        p1 = parse_page1(page1['text']) if page1 else {}
        p3 = parse_ladwp_page3(page3['text']) if page3 else {}
        bill_amount = p1.get('bill_amount') or p3.get('total_charges_page3')
        current_kwh = p3.get('bi_monthly_kwh')
        annual_kwh_estimate = (p3.get('monthly_kwh_est') * 12) if p3.get('monthly_kwh_est') is not None else (current_kwh * 6 if current_kwh is not None else None)
        annual_cost_estimate = bill_amount * 6 if bill_amount is not None else None
        avg_rate = (bill_amount / current_kwh) if bill_amount and current_kwh else None
        usage_basis = 'ladwp bi-monthly estimate'
        return {**{'utility': utility, 'utility_badge': 'LADWP'}, **p1, **p3, 'annual_kwh_estimate': annual_kwh_estimate, 'annual_cost_estimate': annual_cost_estimate, 'avg_rate': avg_rate, 'monthly_avg_bill': bill_amount / 2 if bill_amount is not None else None, 'usage_basis': usage_basis, 'page1_used': page1.get('page_no'), 'page3_used': page3.get('page_no'), 'template': 'ladwp'}

    p1 = parse_page1(page1['text'])
    p4 = parse_sce_page4(page4['text'])
    bill_amount = p1['bill_amount']
    current_kwh = p4['current_kwh']
    avg_daily = p4['avg_daily_kwh']
    annual_kwh_estimate = avg_daily * 365 if avg_daily is not None else (current_kwh * 12 if current_kwh is not None else None)
    annual_cost_estimate = bill_amount * 12 if bill_amount is not None else None
    avg_rate = (bill_amount / current_kwh) if bill_amount and current_kwh else None
    usage_basis = '12-month estimate' if avg_daily is not None else 'single-bill estimate'
    return {**{'utility': utility, 'utility_badge': 'SCE'}, **p1, **p4, 'annual_kwh_estimate': annual_kwh_estimate, 'annual_cost_estimate': annual_cost_estimate, 'avg_rate': avg_rate, 'monthly_avg_bill': bill_amount, 'usage_basis': usage_basis, 'page1_used': page1.get('page_no'), 'page4_used': page4.get('page_no'), 'template': 'sce'}

def solar_estimate(data):
    annual_kwh = data['annual_kwh_estimate'] or ((data['current_kwh'] or 0) * 12)
    target_kwh = annual_kwh * 1.10 if annual_kwh else None
    target_rate = data['avg_rate'] * 0.75 if data.get('avg_rate') else None
    fixed_monthly = (target_kwh / 12) * target_rate if target_kwh and target_rate else None
    system_kw = target_kwh / (365 * 5 * 0.8) if target_kwh else None
    return {'target_kwh': target_kwh, 'target_rate': target_rate, 'fixed_monthly': fixed_monthly, 'system_kw': system_kw}

def save_lead(row):
    df = pd.DataFrame([row])
    if os.path.exists(LEADS_CSV):
        df.to_csv(LEADS_CSV, mode='a', index=False, header=False)
    else:
        df.to_csv(LEADS_CSV, index=False)

def make_pdf(data, solar):
    path = 'solar_report.pdf'
    doc = SimpleDocTemplate(path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [Paragraph('Solar Savings Report', styles['Title']), Spacer(1, 0.12*inch)]
    rows = [
        ['Homeowner', data.get('name') or ''], ['Address', data.get('address') or ''], ['Utility', data['utility']],
        ['Report Template', data.get('template') or ''], ['Page 1 used', str(data.get('page1_used'))],
        ['History page used', str(data.get('page4_used') or data.get('page3_used'))], ['Bill Amount', f"${data['bill_amount']:.2f}" if data.get('bill_amount') is not None else ''],
        ['Current kWh', f"${data['current_kwh']:.0f}" if data.get('current_kwh') is not None else ''], ['12-mo estimate basis', data['usage_basis']],
        ['Annual kWh estimate', f"${data['annual_kwh_estimate']:.0f}" if data['annual_kwh_estimate'] else ''], ['Annual cost estimate', f"${data['annual_cost_estimate']:.2f}" if data['annual_cost_estimate'] else ''],
        ['Avg rate', f"${data['avg_rate']:.4f}/kWh" if data.get('avg_rate') else ''], ['Proposed system', f"${solar['system_kw']:.2f} kW" if solar['system_kw'] else ''],
        ['Target fixed monthly', f"${solar['fixed_monthly']:.2f}" if solar['fixed_monthly'] else ''], ['Scheduling link', CALENDLY_LINK],
    ]
    tbl = Table(rows, colWidths=[1.8*inch, 4.8*inch])
    tbl.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.25, colors.grey), ('VALIGN', (0,0), (-1,-1), 'TOP'), ('FONTSIZE', (0,0), (-1,-1), 9)]))
    story += [tbl, Spacer(1, 0.18*inch), Paragraph('Next step: review this estimate and schedule a consultation using the link above.', styles['BodyText'])]
    doc.build(story)
    with open(path, 'rb') as f:
        return f.read()

st.title('Solar Bill Analyzer')
st.write('Upload bill pages. Page numbers in the top-right corner determine which page is summary and which is usage history.')
files = st.file_uploader('Upload bill pages', type=['jpg', 'jpeg', 'png', 'pdf'], accept_multiple_files=True)

if files:
    pages = load_bill_pages(files)
    data = parse_bill(pages)
    solar = solar_estimate(data)

    st.subheader('Parsed bill')
    st.info(f"Detected: {data.get('utility_badge', 'Unknown Utility')}")
    cols = st.columns(3)
    cols[0].metric('Utility', data['utility'])
    cols[1].metric('Bill amount', f"${data['bill_amount']:.2f}" if data.get('bill_amount') else 'n/a')
    cols[2].metric('Usage basis', data['usage_basis'])

    cols = st.columns(3)
    cols[0].metric('Current kWh', f"{data['current_kwh']:.0f}" if data.get('current_kwh') else 'n/a')
    cols[1].metric('Avg rate', f"${data['avg_rate']:.4f}/kWh" if data.get('avg_rate') else 'n/a')
    cols[2].metric('Annual kWh estimate', f"{data['annual_kwh_estimate']:.0f}" if data.get('annual_kwh_estimate') else 'n/a')

    cols = st.columns(3)
    cols[0].metric('Proposed system', f"{solar['system_kw']:.2f} kW" if solar['system_kw'] else 'n/a')
    cols[1].metric('Target rate', f"${solar['target_rate']:.4f}/kWh" if solar['target_rate'] else 'n/a')
    cols[2].metric('Fixed monthly', f"${solar['fixed_monthly']:.2f}" if solar['fixed_monthly'] else 'n/a')

    contact = st.text_input('Phone or email for report delivery')
    if st.button('Generate report'):
        pdf = make_pdf(data, solar)
        st.download_button('Download PDF report', pdf, file_name='solar_report.pdf', mime='application/pdf')
        save_lead({
            'name': data.get('name'), 'address': data.get('address'), 'utility': data['utility'], 'template': data.get('template'),
            'bill_amount': data.get('bill_amount'), 'current_kwh': data.get('current_kwh'), 'avg_rate': data.get('avg_rate'),
            'annual_kwh_estimate': data.get('annual_kwh_estimate'), 'annual_cost_estimate': data.get('annual_cost_estimate'),
            'system_kw': solar['system_kw'], 'fixed_monthly': solar['fixed_monthly'], 'contact': contact, 'usage_basis': data['usage_basis'],
            'page1_used': data.get('page1_used'), 'page4_used': data.get('page4_used'), 'page3_used': data.get('page3_used'), 'billing_frequency': data.get('billing_frequency', 'monthly')
        })
        st.success('Report created and lead saved to CSV.')
