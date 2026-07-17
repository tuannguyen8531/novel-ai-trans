from src.services.importing.extractor import EpubSection
from src.services.importing.selection import select_processed_chapters


def test_selection_falls_back_to_reading_order_for_unnumbered_titles() -> None:
    sections = [
        section(1, "해방노예인데 주인이 집착한다", text="Author: a\nTags: b\nSynopsis\n..."),
        section(2, "Notice: 르노아 일러스트 모음"),
        section(3, "해방된 노예가 집착할 리 없잖아"),
        section(4, "주인은 노예 해방에 목숨 거는 거 아니었냐고"),
    ]

    chapters = select_processed_chapters(sections)

    assert [chapter.number for chapter in chapters] == [1, 2]
    assert [chapter.section.title for chapter in chapters] == [
        "해방된 노예가 집착할 리 없잖아",
        "주인은 노예 해방에 목숨 거는 거 아니었냐고",
    ]


def test_notice_chapter_markers_do_not_disable_fallback() -> None:
    sections = [
        section(1, "cover"),
        section(2, "Demo Book", text="Author: a\nTags: b\nSynopsis\n..."),
        section(3, "Notice: 550화까지 왔습니다!!"),
        section(4, "Notice: 259화 삽화 추가되었습니다!!!"),
        section(5, "1.[첫 번째 이야기]"),
        section(6, "2.[두 번째 이야기]"),
    ]

    chapters = select_processed_chapters(sections)

    assert [chapter.number for chapter in chapters] == [1, 2]
    assert [chapter.section.title for chapter in chapters] == ["1.[첫 번째 이야기]", "2.[두 번째 이야기]"]


def section(index: int, title: str, text: str = "body") -> EpubSection:
    return EpubSection(
        index=index,
        source_path=f"section-{index}.xhtml",
        title=title,
        text=text,
    )
