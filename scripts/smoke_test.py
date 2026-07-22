"""End-to-end smoke test: generates a synthetic résumé PDF, uploads it,
creates an analysis, waits for extraction, confirms the extraction review
step with no corrections, waits for scoring, and prints the published
report. Exercises the full ingest->extract->score->publish loop against a
running `docker compose up` stack.

Usage: python scripts/smoke_test.py [API_URL]  (default http://localhost:8000)
"""
from __future__ import annotations

import sys
import time
import uuid

import fitz
import requests

API_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
TIMEOUT_SECONDS = 180


def make_test_resume_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    text = (
        "Jordan Smith\n"
        "jordan.smith@example.com | (555) 123-4567\n\n"
        "SUMMARY\n"
        "Computer science student seeking a software engineering internship.\n\n"
        "EXPERIENCE\n"
        "Software Engineering Intern, Acme Corp\n"
        "- Built a dashboard for the analytics team\n"
        "- Helped fix bugs in the payments service\n"
        "- Worked with teammates on a new feature\n\n"
        "EDUCATION\n"
        "B.S. Computer Science, State University, Expected 2027\n\n"
        "SKILLS\n"
        "Python, JavaScript, SQL, Git, React\n"
    )
    page.insert_text((72, 72), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def main() -> None:
    pdf_bytes = make_test_resume_pdf()
    print(f"Generated test PDF ({len(pdf_bytes)} bytes)")

    resp = requests.post(
        f"{API_URL}/v1/uploads",
        json={"filename": "resume.pdf", "mime_type": "application/pdf", "byte_size": len(pdf_bytes)},
    )
    resp.raise_for_status()
    upload = resp.json()
    print(f"Created upload {upload['upload_id']}")

    resp = requests.put(upload["upload_url"], data=pdf_bytes)
    resp.raise_for_status()
    print("Uploaded bytes, file validated")

    resp = requests.post(
        f"{API_URL}/v1/analyses",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "goal_profile": {
                "target_role": "Software Engineer Intern",
                "seniority": "intern",
                "geography": "United States",
                "outcome": "Land a summer internship",
                "job_description": None,
            },
            "upload_ids": [upload["upload_id"]],
        },
    )
    resp.raise_for_status()
    analysis = resp.json()
    analysis_id = analysis["analysis_id"]
    print(f"Created analysis {analysis_id}, status={analysis['status']}")

    deadline = time.time() + TIMEOUT_SECONDS
    reviewed = False
    while time.time() < deadline:
        resp = requests.get(f"{API_URL}/v1/analyses/{analysis_id}")
        resp.raise_for_status()
        state = resp.json()
        print(f"  status={state['status']} stage={state['current_stage']}")

        if state["status"] == "needs_review" and not reviewed:
            resp = requests.get(f"{API_URL}/v1/analyses/{analysis_id}/extraction")
            resp.raise_for_status()
            extraction = resp.json()
            print(
                f"  extraction: {len(extraction['fields'])} fields, "
                f"covered={extraction['required_sections_covered']}, "
                f"missing={extraction['required_sections_missing']}, "
                f"mean_confidence={extraction['mean_confidence']}"
            )
            resp = requests.patch(
                f"{API_URL}/v1/analyses/{analysis_id}/extraction", json={"corrections": []}
            )
            resp.raise_for_status()
            reviewed = True
            print("  confirmed extraction with no corrections")

        if state["status"] == "completed":
            report = state["report"]
            print("\n=== REPORT ===")
            print(f"Total score: {report['total_score']} ({report['confidence_band']} confidence)")
            for item in report["dimension_scores"]:
                print(f"  {item['dimension']}: {item['score']} — {item['reasoning_summary']}")
            print(f"\n{len(report['recommendations'])} recommendation(s):")
            for rec in report["recommendations"]:
                print(f"  [{rec['audit_status']}] {rec['proposed_rewrite']}")
            print("\nSMOKE TEST PASSED")
            return

        if state["status"] == "failed":
            print(f"\nSMOKE TEST FAILED: {state['error_code']} — {state['error_message']}")
            sys.exit(1)

        time.sleep(3)

    print("\nSMOKE TEST TIMED OUT")
    sys.exit(1)


if __name__ == "__main__":
    main()
