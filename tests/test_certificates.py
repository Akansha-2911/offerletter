import tempfile
import unittest
from pathlib import Path

import fitz

from certificates import build_certificate_bundle, normalize_certificate_data


BASE_DIR = Path(__file__).resolve().parents[1]


class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.sample = {
            "candidate_name": "Sana Ismail Shaikh",
            "email": "sana@example.com",
            "domain": "Artificial Intelligence",
            "start_date": "2026-02-05",
            "end_date": "2026-05-05",
            "issue_date": "2026-05-10",
            "duration_months": "3",
            "progress_percent": "78",
            "mode": "Online",
        }

    def test_normalization_generates_stable_credential(self):
        first = normalize_certificate_data(self.sample)
        second = normalize_certificate_data(self.sample)
        self.assertEqual(first["credential_id"], second["credential_id"])
        self.assertTrue(first["credential_id"].startswith("APAR2605"))

    def test_bundle_contains_three_valid_single_page_pdfs(self):
        data, files = build_certificate_bundle(self.sample, BASE_DIR)
        self.assertEqual(set(files), {"experience", "progress", "completion"})
        for filename, content in files.values():
            self.assertTrue(filename.endswith(".pdf"))
            self.assertTrue(content.startswith(b"%PDF"))
            document = fitz.open(stream=content, filetype="pdf")
            self.assertEqual(document.page_count, 1)
            text = document[0].get_text()
            self.assertIn("Sana Ismail Shaikh", text)
            self.assertIn(data["credential_id"], text)
            document.close()

    def test_rejects_invalid_dates(self):
        invalid = dict(self.sample, start_date="2026-06-01", end_date="2026-05-01")
        with self.assertRaises(ValueError):
            normalize_certificate_data(invalid)


if __name__ == "__main__":
    unittest.main()
