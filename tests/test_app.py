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
        self.client = app_module.app.test_client()
        self.client.post("/login", data={"uid": app_module.LOGIN_USER, "password": app_module.LOGIN_PASS})

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

    def test_admin_data_page_has_delete_buttons(self):
        response = self.client.get("/admin/data")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Delete", response.data)
        self.assertIn(b"Action", response.data)

    def test_delete_admin_data_record(self):
        # Create a test log record
        from data_store import save_document_log, list_document_logs, delete_document_log
        save_document_log(
            "employment_offer",
            {"employee_name": "Test Delete Candidate", "email": "delete_me@example.com"},
            admin_user="test-admin",
            filename="Test_Delete.pdf"
        )
        logs = list_document_logs("employment_offer")
        target = next((r for r in logs if r.get("email") == "delete_me@example.com"), None)
        self.assertIsNotNone(target)
        rec_id = target["record_id"]

        # Call delete endpoint via AJAX
        res = self.client.post(
            f"/admin/data/delete/{rec_id}",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))

        # Verify record no longer exists
        remaining = [r for r in list_document_logs() if r.get("record_id") == rec_id]
        self.assertEqual(len(remaining), 0)


if __name__ == "__main__":
    unittest.main()
