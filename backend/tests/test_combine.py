from app.text_extract import combine


def test_combine_all_files_fit() -> None:
    parts = [("a.txt", "hello world"), ("b.txt", "second file")]
    context, truncated = combine(parts, limit=1000)

    assert truncated == []
    assert "hello world" in context
    assert "second file" in context


def test_combine_partial_cut_at_paragraph_boundary() -> None:
    name = "a.txt"
    text = "Первый абзац.\n\nВторой абзац который не поместится совсем."
    header = f"### {name}\n"
    first_paragraph_end = len(header) + len("Первый абзац.")
    # лимит: чуть дальше первого абзаца, но раньше конца файла
    limit = first_paragraph_end + 3

    context, truncated = combine([(name, text)], limit=limit)

    assert context == header + "Первый абзац."
    assert len(truncated) == 1
    assert truncated[0].filename == name
    assert truncated[0].reason == "partial"
    assert "\n\nВторой" not in context


def test_combine_drops_file_after_cutoff() -> None:
    parts = [
        ("a.txt", "x" * 50),
        ("b.txt", "nolinebreakhere"),
        ("c.txt", "third file content"),
    ]
    chunk_a = f"### a.txt\n{'x' * 50}"
    limit = len(chunk_a)  # a укладывается ровно, на b и c уже не остаётся места

    context, truncated = combine(parts, limit=limit)

    assert context == chunk_a
    assert [(t.filename, t.reason) for t in truncated] == [
        ("b.txt", "dropped"),
        ("c.txt", "dropped"),
    ]


def test_combine_drops_file_without_paragraph_boundary() -> None:
    name = "a.txt"
    text = "some content without a blank line separator anywhere"
    header = f"### {name}\n"
    limit = len(header) + 5  # укладывается только начало первого абзаца, без \n\n

    context, truncated = combine([(name, text)], limit=limit)

    assert context == ""
    assert [(t.filename, t.reason) for t in truncated] == [(name, "dropped")]
