from src.services.importing.changes import ChapterImportChange, calculate_changes, classify_chapter


def test_change_calculation_preserves_all_result_categories(tmp_path) -> None:
    unchanged_path = tmp_path / "chapter.txt"
    unchanged_path.write_text("same\n", encoding="utf-8")

    assert classify_chapter(tmp_path / "missing.txt", "new\n") == "added"
    assert classify_chapter(unchanged_path, "same\n") == "unchanged"
    assert classify_chapter(unchanged_path, "different\n") == "overwritten"

    changes = calculate_changes(
        {1, 2, 3},
        {2, 3, 4},
        keep_existing=False,
        unchanged=[2],
        overwritten=[ChapterImportChange(3, "Chapter 3")],
        added=[4],
    )

    assert changes.retained == ()
    assert changes.unchanged == (2,)
    assert changes.overwritten == (ChapterImportChange(3, "Chapter 3"),)
    assert changes.added == (4,)
    assert changes.removed == (1,)
