# Aparaitech Document and Certificate Generator

This Flask app creates employment offers, live-project offers, and a three-document internship certificate bundle directly from the admin web dashboard.

## New certificate automation

The **All 3 Certificates** dashboard option opens a web form similar to the existing Offer Letter form. One submission generates:

- Internship Experience Letter
- Live Project Progress Certificate
- Internship Completion Certificate

All three PDFs use the same credential ID. After submission, the app:

1. Generates the three certificates.
2. Emails the three PDF attachments to the candidate.
3. Downloads one ZIP containing all three PDFs for the admin.

No Google Form or Apps Script is required.

## Run locally

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open `http://127.0.0.1:5000` and log in using the values configured in `.env`.

## Configure email

Complete the SMTP fields in `.env`. For Gmail, use an app password instead of the normal account password. Never commit `.env` to GitHub.

## Generate demo PDFs

```bash
python generate_demo_certificates.py
```

The three demo files are written to `sample_output/`.

## Run certificate tests

```bash
python -m unittest discover -s tests -v
```

## Deploy

The included `vercel.json` supports Vercel deployment. Add all values from `.env.example` as deployment environment variables. The same project can also run on Render with:

```bash
gunicorn app:app
```

## Admin data storage and Excel export

The admin portal now automatically logs every generated Employment Offer, BDA Offer, Live Project Offer, Certificate Bundle, and Software Developer document bundle.

Recommended production storage is MongoDB. Add these values to `.env`:

```env
MONGO_URI=mongodb+srv://YOUR_USER:YOUR_PASSWORD@YOUR_CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME=aparaitech_document_portal
```

If `MONGO_URI` is not configured or MongoDB is temporarily unavailable, the app safely falls back to `data/document_logs.json` so document generation is not blocked.

Admin data pages:
- `/admin/data` — view all sections and records
- `/admin/data?type=employment_offer`
- `/admin/data?type=bda_offer`
- `/admin/data?type=live_project_offer`
- `/admin/data?type=certificates`
- `/admin/data?type=software_developer`
- `/admin/data/export?type=all` — download an Excel workbook with separate sheets per document type
