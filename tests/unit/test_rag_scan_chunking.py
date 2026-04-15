from kov.rag.scan.chunking import simple_chunk_text


def test_simple_chunk_text_max_chars():
    page_texts = ["line " * 200]
    chunks = simple_chunk_text(page_texts=page_texts, max_chars=200, overlap_chars=0)
    assert chunks
    assert all(len(c.text) <= 200 for c in chunks)

