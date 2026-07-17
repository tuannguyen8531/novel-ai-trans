from src.services.importing.extractor import TextExtractor


def test_text_extractor_keeps_image_position_between_paragraphs() -> None:
    extractor = TextExtractor()
    extractor.feed('<p>Before image.</p><img src="image.jpg"/><p>After image.</p>')
    extractor.close()

    assert extractor.get_text() == "Before image.\n\n[[EPUB_IMAGE:1]]\n\nAfter image."
