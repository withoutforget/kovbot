from kov.rag.scan.pdf import detect_pdf_type


def test_detect_pdf_type_text():
    assert detect_pdf_type(["hello", "world"]) == "text"


def test_detect_pdf_type_scanned():
    assert detect_pdf_type(["", "  "]) == "scanned"

