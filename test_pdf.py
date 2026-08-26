import traceback
from report_generator import generate_pdf_report

def test():
    scan_result = {
        "score": 50,
        "verdict": "Partial Compliance",
        "url": "https://example.com",
        "timestamp": "2026-06-27T10:00:00Z",
        "ai_available": False,
        "privacy_policy_found": True,
        "cookie_banner_found": False
    }
    try:
        pdf_bytes = generate_pdf_report(scan_result, "This is a dummy privacy policy for testing.")
        print(f"Successfully generated PDF of {len(pdf_bytes)} bytes.")
    except Exception as e:
        print("ERROR DURING GENERATION:")
        traceback.print_exc()

if __name__ == "__main__":
    test()
