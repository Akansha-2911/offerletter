"""Create the three demo PDFs used to verify certificate rendering."""

from pathlib import Path

from certificates import build_certificate_bundle


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "sample_output"


def main():
    sample = {
        "candidate_name": "Sana Ismail Shaikh",
        "email": "sana@example.com",
        "domain": "Artificial Intelligence",
        "start_date": "2026-02-05",
        "end_date": "2026-05-05",
        "issue_date": "2026-05-10",
        "duration_months": "3",
        "progress_percent": "78",
        "mode": "Online",
        "credential_id": "APAR0226015",
        "verification_url": "lms.aparaitech.org",
    }
    _, files = build_certificate_bundle(sample, BASE_DIR)
    OUTPUT_DIR.mkdir(exist_ok=True)
    for _, (filename, content) in files.items():
        (OUTPUT_DIR / filename).write_bytes(content)
        print(f"Created {filename}")


if __name__ == "__main__":
    main()
