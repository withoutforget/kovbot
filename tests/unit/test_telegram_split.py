from kov.rag.search.telegram import split_telegram


def test_split_telegram_single_part():
    parts = split_telegram("hello", safe_limit_chars=10, max_parts=3)
    assert len(parts) == 1
    assert parts[0].part == 1 and parts[0].total_parts == 1


def test_split_telegram_multiple_parts_respects_limit():
    text = "a" * 50
    parts = split_telegram(text, safe_limit_chars=20, max_parts=3)
    assert 1 < len(parts) <= 3
    assert all(len(p.text) <= 20 for p in parts)
    assert parts[-1].total_parts == len(parts)

