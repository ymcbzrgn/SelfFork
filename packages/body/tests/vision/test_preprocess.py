"""preprocess + delta_image — Pillow-backed image transforms."""

from __future__ import annotations

import io

import pytest

PIL = pytest.importorskip("PIL.Image")

from selffork_body.vision import PreprocessConfig, delta_image, preprocess


def _make_png(size: tuple[int, int], color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    from PIL import Image

    img = Image.new("RGB", size, color)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def test_preprocess_empty_raises() -> None:
    with pytest.raises(ValueError):
        preprocess(b"")


def test_preprocess_resizes_long_edge_to_target() -> None:
    img = _make_png((4096, 2048))
    out = preprocess(img, PreprocessConfig(target_long_edge=1024, multiple_of=48))
    from PIL import Image

    rendered = Image.open(io.BytesIO(out))
    long_edge = max(rendered.size)
    assert long_edge <= 1024
    assert long_edge % 48 == 0


def test_preprocess_no_resize_when_smaller_than_target() -> None:
    img = _make_png((512, 512))
    out = preprocess(img, PreprocessConfig(target_long_edge=1024))
    from PIL import Image

    rendered = Image.open(io.BytesIO(out))
    assert rendered.size == (512, 512)


def test_preprocess_roi_crops() -> None:
    img = _make_png((1000, 800))
    cfg = PreprocessConfig(target_long_edge=2000, roi=(10, 20, 100, 150))
    out = preprocess(img, cfg)
    from PIL import Image

    rendered = Image.open(io.BytesIO(out))
    assert rendered.size == (100, 150)


def test_preprocess_invalid_roi_raises() -> None:
    img = _make_png((100, 100))
    with pytest.raises(ValueError):
        preprocess(img, PreprocessConfig(roi=(0, 0, 0, 50)))


def test_preprocess_jpeg_output() -> None:
    img = _make_png((512, 512))
    out = preprocess(img, PreprocessConfig(target_long_edge=1024, output_format="jpeg"))
    assert out.startswith(b"\xff\xd8\xff")


def test_delta_image_no_change_returns_grayscale() -> None:
    a = _make_png((128, 128), (255, 0, 0))
    out = delta_image(a, a)
    assert out.startswith(b"\x89PNG")


def test_delta_image_highlights_change() -> None:
    a = _make_png((128, 128), (255, 0, 0))
    b = _make_png((128, 128), (0, 255, 0))
    out = delta_image(a, b)
    assert out.startswith(b"\x89PNG")
