from flask import Flask, request, send_file, jsonify, render_template
from scrape import scrape_all_offers, save_offers_to_pdf, send_email
import tempfile
import os

app = Flask(__name__)

@app.route('/generate', methods=['POST'])
def generate_pdf():
    data = request.get_json()
    keyword = data.get('keyword', '').strip()
    if not keyword:
        return jsonify({'error': 'Chybí klíčové slovo.'}), 400
    # Vytvoření BASE_URL podle klíčového slova
    search = keyword.replace(' ', '+')
    base_url = f"https://www.jobs.cz/prace/?q%5B%5D={search}&date=7d&page={{page}}"
    offers = scrape_all_offers(base_url)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        pdf_path = tmp.name
    save_offers_to_pdf(offers, filename=pdf_path)
    return send_file(pdf_path, as_attachment=True, download_name=f"jobs_{keyword}.pdf")

@app.route('/send_email', methods=['POST'])
def send_email_api():
    data = request.get_json()
    keyword = data.get('keyword', '').strip()
    email = data.get('email', '').strip()
    if not keyword or not email:
        return jsonify({'error': 'Chybí klíčové slovo nebo e-mail.'}), 400
    search = keyword.replace(' ', '+')
    base_url = f"https://www.jobs.cz/prace/?q%5B%5D={search}&date=7d&page={{page}}"
    offers = scrape_all_offers(base_url)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        pdf_path = tmp.name
    save_offers_to_pdf(offers, filename=pdf_path)
    success = send_email(pdf_path, [email])
    os.remove(pdf_path)
    if success:
        return jsonify({'message': 'PDF bylo odesláno na e‑mail.'})
    else:
        return jsonify({'error': 'Nepodařilo se odeslat e‑mail.'}), 500

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
