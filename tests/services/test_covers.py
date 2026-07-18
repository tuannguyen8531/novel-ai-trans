"""Tests for uploaded cover normalization."""

from io import BytesIO

import pytest
from PIL import Image

from src.services.covers import MAX_COVER_SIZE, normalize_cover


def _image_bytes(*, size: tuple[int, int] = (120, 180), mode: str = "RGB", format_name: str = "PNG") -> bytes:
    image = Image.new(mode, size, (255, 0, 0, 128) if mode == "RGBA" else "red")
    output = BytesIO()
    image.save(output, format=format_name)
    return output.getvalue()


def test_normalize_cover_outputs_metadata_free_rgb_jpeg() -> None:
    result = normalize_cover(_image_bytes(mode="RGBA"))

    with Image.open(BytesIO(result)) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (120, 180)
        assert not image.getexif()


def test_normalize_cover_preserves_ratio_and_limits_dimensions() -> None:
    result = normalize_cover(_image_bytes(size=(1800, 2700)))

    with Image.open(BytesIO(result)) as image:
        assert image.size == MAX_COVER_SIZE


@pytest.mark.parametrize("data", [b"", b"not an image"])
def test_normalize_cover_rejects_invalid_input(data: bytes) -> None:
    with pytest.raises(ValueError):
        normalize_cover(data)
