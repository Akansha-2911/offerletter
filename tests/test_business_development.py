import io
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import fitz

import app as app_module
from businessdevelopment_templates import (
    build_business_development_template_bundle,
    normalize_data,
)
from bda_offer import build_bda_pdf
from live_project import build_live_project_pdf

BASE_DIR = Path(__file__).resolve().parents[1]


class BusinessDevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.sample = {
            "candidate_name": "Ansh Madanpuriya",
            "email": "ansh@example.com",
            "role": "Business Development Intern",
            "domain": "Business Development",
            "start_date": "2026-03-01",
            "end_date": "2026-07-01",
            "issue_date": "2026-07-05",
        }
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()
        self.client.post("/login", data={"uid": app_module.LOGIN_USER, "password": app_module.LOGIN_PASS})

    def test_normalization_and_stable_credential(self):
        d1 = normalize_data(self.sample)
        d2 = normalize_data(self.sample)
        self.assertEqual(d1["credential_id"], d2["credential_id"])
        self.assertTrue(d1["credential_id"].startswith("APAR2607"))
        self.assertEqual(d1["role"], "Business Development Intern")
        self.assertEqual(d1["location"], "Baramati, Pune")

    def test_bundle_generation_and_baramati_pune_address(self):
        data, files = build_business_development_template_bundle(self.sample, BASE_DIR)
        self.assertEqual(set(files.keys()), {"completion", "experience", "lor"})

        for key, (filename, content) in files.items():
            self.assertTrue(filename.endswith(".pdf"))
            self.assertTrue(content.startswith(b"%PDF"))
            doc = fitz.open(stream=content, filetype="pdf")
            self.assertEqual(doc.page_count, 1)
            text = doc[0].get_text()
            self.assertIn("Ansh Madanpuriya", text)
            # Verify Baramati, Pune address is included
            self.assertIn("Baramati, Pune", text)
            doc.close()

    def test_web_route_availability(self):
        res = self.client.get("/business-development-templates")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Business Development Internship Certificates", res.data)
        self.assertIn(b"Baramati, Pune", res.data)

    @patch("app.send_business_development_template_email")
    def test_web_route_generate_bundle(self, mock_email):
        res = self.client.post("/generate-business-development-templates", data=self.sample)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["X-Email-Status"], "sent")
        self.assertEqual(res.mimetype, "application/zip")
        with zipfile.ZipFile(io.BytesIO(res.data)) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 3)
            self.assertTrue(all(name.endswith(".pdf") for name in names))
        mock_email.assert_called_once()

    def test_offer_letters_have_hinjewadi_phase_2_411057_address(self):
        captured_text = {}
        orig_open = fitz.open

        def mock_open(*args, **kwargs):
            doc = orig_open(*args, **kwargs)
            if 'stream' in kwargs and kwargs.get('filetype') == 'pdf':
                t = ''.join(p.get_text() for p in doc)
                if t:
                    captured_text['last'] = t
            return doc

        with patch('fitz.open', side_effect=mock_open):
            # 1. General Employment Offer Letter
            captured_text.clear()
            app_module.build_pdf({
                "employee_name": "Test Employee",
                "joining_date": "2026-04-01",
                "training_end_date": "2026-08-01",
                "position": "Software Engineer",
            })
            text_emp = captured_text.get('last', '')
            self.assertIn("Hinjewadi Phase 2", text_emp)
            self.assertIn("411057", text_emp)

            # 2. BDA Offer Letter
            captured_text.clear()
            build_bda_pdf({
                "employee_name": "Test BDA",
                "joining_date": "2026-04-01",
                "training_end_date": "2026-08-01",
                "reporting_to": "BD Head",
                "work_mode": "On-site",
            }, base_dir=str(BASE_DIR))
            text_bda = captured_text.get('last', '')
            self.assertIn("Hinjewadi Phase 2", text_bda)
            self.assertIn("411057", text_bda)

            # 3. Live Project Offer Letter
            captured_text.clear()
            build_live_project_pdf({
                "candidate_name": "Test Candidate",
                "domain": "Web Development",
                "start_date": "2026-04-01",
                "end_date": "2026-07-01",
                "location": "122, Gera Imperial Rise, Hinjewadi Phase 2, Pune - 411057",
            })
            text_lp = captured_text.get('last', '')
            self.assertIn("Hinjewadi Phase 2", text_lp)
            self.assertIn("411057", text_lp)


if __name__ == "__main__":
    unittest.main()
