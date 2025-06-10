import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
import re
from datetime import datetime, timedelta
import locale
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os

BASE_URL = "https://www.jobs.cz/prace/?q%5B%5D=e-shop&q%5B%5D=ecommerce&date=7d&page={page}"

def get_max_page(base_url):
    resp = requests.get(base_url.format(page=1))
    soup = BeautifulSoup(resp.text, "html.parser")
    pagination = soup.find("ul", class_="Pagination")
    if not pagination:
        return 1
    page_links = pagination.find_all("a", class_="Pagination__link")
    pages = [int(a.get_text(strip=True)) for a in page_links if a.get_text(strip=True).isdigit()]
    return max(pages) if pages else 1

def parse_offer(card):
    title_tag = card.find("a", class_="SearchResultCard__titleLink")
    title = title_tag.get_text(strip=True) if title_tag else ""
    url = title_tag["href"] if title_tag else ""
    if url and not url.startswith("http"):
        url = "https://www.jobs.cz" + url

    company_tag = card.find("span", translate="no")
    company = company_tag.get_text(strip=True) if company_tag else ""

    location_tag = card.find("li", {"data-test": "serp-locality"})
    location = location_tag.get_text(strip=True) if location_tag else ""

    date_tag = card.find("div", class_="SearchResultCard__status")
    date = date_tag.get_text(strip=True) if date_tag else ""

    salary_tag = card.find("span", class_="Tag--success")
    salary = salary_tag.get_text(strip=True) if salary_tag else ""

    tags = [t.get_text(strip=True) for t in card.find_all("span", class_="Tag--neutral")]

    # Určení typu nabídky podle textu v date_tag
    offer_type = ""
    if date.lower().startswith("přidáno"):
        offer_type = "pridano"
    elif date.lower().startswith("aktualizováno"):
        offer_type = "aktualizovano"

    return {
        "title": title,
        "company": company,
        "location": location,
        "date": date,
        "salary": salary,
        "tags": ", ".join(tags),
        "url": url,
        "type": offer_type  # Přidání typu nabídky
    }

def scrape_all_offers(base_url=None):
    if base_url is None:
        base_url = BASE_URL
    offers = []
    max_page = get_max_page(base_url)
    for page in range(1, max_page + 1):
        print(f"Scraping page {page}/{max_page}")
        resp = requests.get(base_url.format(page=page))
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all("article", class_="SearchResultCard")
        for card in cards:
            offer = parse_offer(card)
            offers.append(offer)
    # Deduplicitace podle URL (některé nabídky se opakují na více stránkách)
    unique_offers = list({o['url']: o for o in offers}.values())
    print(f"Celkem nabídek (včetně duplicit): {len(offers)}")
    print(f"Celkem unikátních nabídek: {len(unique_offers)}")
    return unique_offers

def parse_czech_date(date_str):
    date_str = date_str.strip().lower()
    today = datetime.today()
    if date_str.startswith('přidáno'):
        datum = date_str.replace('přidáno', '').strip()
    elif date_str.startswith('aktualizováno'):
        datum = date_str.replace('aktualizováno', '').strip()
    else:
        datum = date_str
    if datum.startswith('před'):
        # např. 'před 3 hodinami', 'před 15 minutami'
        match = re.search(r'(\d+)', datum)
        if 'hodin' in datum and match:
            hours = int(match.group(1))
            return today - timedelta(hours=hours)
        elif 'minut' in datum and match:
            minutes = int(match.group(1))
            return today - timedelta(minutes=minutes)
    if datum == 'dnes':
        return today.replace(hour=0, minute=0, second=0, microsecond=0)
    if datum == 'včera':
        return (today - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    mesice = {
        'ledna': 1, 'února': 2, 'března': 3, 'dubna': 4, 'května': 5, 'června': 6,
        'července': 7, 'srpna': 8, 'září': 9, 'října': 10, 'listopadu': 11, 'prosince': 12
    }
    parts = datum.split()
    if len(parts) == 2:
        try:
            den = int(parts[0].replace('.', ''))
            mesic = mesice.get(parts[1], today.month)
            rok = today.year
            if mesic > today.month:
                rok -= 1
            return datetime(rok, mesic, den)
        except Exception:
            return today
    return today

def save_offers_to_pdf(offers, filename="jobs.pdf"):
    from fpdf import XPos, YPos
    # Rozdělení nabídek podle typu
    offers_pridano = [o for o in offers if o.get('type', '').lower() == 'pridano']
    offers_aktualizovano = [o for o in offers if o.get('type', '').lower() == 'aktualizovano']
    # Seřazení od nejnovější po nejstarší
    offers_pridano_sorted = sorted(offers_pridano, key=lambda o: parse_czech_date(o['date']), reverse=True)
    offers_aktualizovano_sorted = sorted(offers_aktualizovano, key=lambda o: parse_czech_date(o['date']), reverse=True)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font("DejaVu", "", os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", os.path.join(os.path.dirname(__file__), "DejaVuSans-Bold.ttf"))
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 12, "Přidáno", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("DejaVu", size=12)
    for idx, offer in enumerate(offers_pridano_sorted, 1):
        pdf.set_font("DejaVu", "B", 12)
        # Odstranění pouze emoji, ale zachování českých znaků a interpunkce
        clean_title = ''.join(ch for ch in offer['title'] if ord(ch) < 128 or ch.isalpha() or ch in ' .,;:!?()[]-–—"\'')
        pdf.cell(0, 10, f"{idx}. {clean_title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("DejaVu", "", 11)
        pdf.cell(0, 8, f"Firma: {offer['company']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 8, f"Lokalita: {offer['location']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if offer['salary']:
            pdf.cell(0, 8, f"Plat: {offer['salary']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if offer['tags']:
            clean_tags = ''.join(ch for ch in offer['tags'] if ord(ch) < 128 or ch.isalpha() or ch in ' .,;:!?()[]-–—"\'')
            pdf.cell(0, 8, f"Tagy: {clean_tags}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 8, f"Datum: {offer['date']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 255)
        pdf.cell(0, 8, offer['url'], new_x=XPos.LMARGIN, new_y=YPos.NEXT, link=offer['url'])
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 12, "Aktualizováno", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("DejaVu", size=12)
    for idx, offer in enumerate(offers_aktualizovano_sorted, 1):
        pdf.set_font("DejaVu", "B", 12)
        clean_title = ''.join(ch for ch in offer['title'] if ord(ch) < 128 or ch.isalpha() or ch in ' .,;:!?()[]-–—"\'')
        pdf.cell(0, 10, f"{idx}. {clean_title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("DejaVu", "", 11)
        pdf.cell(0, 8, f"Firma: {offer['company']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 8, f"Lokalita: {offer['location']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if offer['salary']:
            pdf.cell(0, 8, f"Plat: {offer['salary']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if offer['tags']:
            clean_tags = ''.join(ch for ch in offer['tags'] if ord(ch) < 128 or ch.isalpha() or ch in ' .,;:!?()[]-–—"\'')
            pdf.cell(0, 8, f"Tagy: {clean_tags}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 8, f"Datum: {offer['date']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 255)
        pdf.cell(0, 8, offer['url'], new_x=XPos.LMARGIN, new_y=YPos.NEXT, link=offer['url'])
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)
    # --- Sekce pro staré nabídky ---
    old_offers = [o for o in offers if parse_czech_date(o['date']) < (datetime.today() - timedelta(days=2))]
    if old_offers:
        old_offers_sorted = sorted(old_offers, key=lambda o: parse_czech_date(o['date']))
        pdf.set_font("DejaVu", "B", 14)
        pdf.cell(0, 12, "Starší nabídky", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("DejaVu", size=12)
        for idx, offer in enumerate(old_offers_sorted, 1):
            pdf.set_font("DejaVu", "B", 12)
            clean_title = ''.join(ch for ch in offer['title'] if ord(ch) < 128 or ch.isalpha() or ch in ' .,;:!?()[]-–—"\'')
            pdf.cell(0, 10, f"{idx}. {clean_title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("DejaVu", "", 11)
            pdf.cell(0, 8, f"Firma: {offer['company']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 8, f"Lokalita: {offer['location']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if offer['salary']:
                pdf.cell(0, 8, f"Plat: {offer['salary']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if offer['tags']:
                clean_tags = ''.join(ch for ch in offer['tags'] if ord(ch) < 128 or ch.isalpha() or ch in ' .,;:!?()[]-–—"\'')
                pdf.cell(0, 8, f"Tagy: {clean_tags}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 8, f"Datum: {offer['date']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 255)
            pdf.cell(0, 8, offer['url'], new_x=XPos.LMARGIN, new_y=YPos.NEXT, link=offer['url'])
            pdf.set_text_color(0, 0, 0)
            pdf.ln(4)
    pdf.output(filename)
    print(f"PDF uložen jako {filename}")
    return filename

def send_email(pdf_filename, recipient_emails):
    sender_email = os.environ.get("SMTP_USER")
    sender_password = os.environ.get("SMTP_PASSWORD")
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.seznam.cz")
    smtp_port = int(os.environ.get("SMTP_PORT", 465))
    subject = f"Pracovní nabídky - {datetime.now().strftime('%Y-%m-%d')}"
    body = "V příloze najdete aktuální pracovní nabídky z jobs.cz.\n\nTento e-mail byl vygenerován automaticky."

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = ", ".join(recipient_emails)
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with open(pdf_filename, "rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename= {os.path.basename(pdf_filename)}"
    )
    msg.attach(part)

    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_emails, msg.as_string())
        server.quit()
        print("E-mail úspěšně odeslán")
        return True
    except Exception as e:
        print(f"Chyba při odesílání e-mailu: {e}")
        return False

if __name__ == "__main__":
    offers = scrape_all_offers()
    pdf_file = save_offers_to_pdf(offers)
    recipient_emails = ["Solidet@seznam.cz", "Kniha4U@seznam.cz"]  # Nahraď seznamem e-mailů
    send_email(pdf_file, recipient_emails)
