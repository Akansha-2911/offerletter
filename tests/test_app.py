import io
import os
import unittest
import zipfile
from unittest.mock import patch

os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["LOGIN_UID"] = "test-admin"
os.environ["LOGIN_PASS"] = "test-password"

import app as app_module


FORM_DATA = {
    "candidate_name": "Sana Ismail Shaikh",
    "email": "sana@example.com",
    "domain": "Artificial Intelligence",
    "start_date": "2026-02-05",
    "end_date": "2026-05-05",
    "issue_date": "2026-05-10",
    "duration_months": "3",
    "progress_percent": "78",
    "mode": "Online",
    "verification_url": "lms.aparaitech.org",
}


class AppCertificateTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()
        self.client.post("/login", data={"uid": "test-admin", "password": "test-password"})

    def test_certificate_page_is_available_after_login(self):
        response = self.client.get("/certificates")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Generate All 3 Certificates", response.data)

    @patch.object(app_module, "send_certificate_bundle_email")
    def test_web_form_downloads_three_pdf_zip(self, mocked_email):
        response = self.client.post("/generate-certificates", data=FORM_DATA)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Email-Status"], "sent")
        self.assertEqual(response.mimetype, "application/zip")
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 3)
            self.assertTrue(all(name.endswith(".pdf") for name in names))
            self.assertTrue(all(archive.read(name).startswith(b"%PDF") for name in names))
        mocked_email.assert_called_once()

if __name__ == "__main__":
    unittest.main()
