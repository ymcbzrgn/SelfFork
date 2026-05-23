"""Image preprocessing for the M5 vision pipeline (ADR-005 §M5-B).

Knobs:

* **Resize** to a target long-edge keeping aspect ratio; rounds to multiples
  of 48 (Gemma 4 patch density rule, Datature CV guide).
* **ROI crop** by ``(x, y, w, h)`` for sub-image inference.
* **Token budget** preset (70 / 140 / 280 / 560 / 1120) — caller passes this
  through to ``mlx_vlm.server`` ``--num-image-tokens``.
* **Delta image** between before/after frames for state-change verification.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "PreprocessConfig",
    "TokenBudget",
    "delta_image",
    "preprocess",
]


TokenBudget = Literal[70, 140, 280, 560, 1120]


@dataclass(frozen=True, slots=True)
class PreprocessConfig:
    target_long_edge: int = 1024
    token_budget: TokenBudget = 280
    roi: tuple[int, int, int, int] | None = None
    output_format: Literal["png", "jpeg"] = "png"
    multiple_of: int = 48


def _round_to_multiple(value: int, multiple: int) -> int:
    if multiple <= 0:
        return value
    return max(multiple, (value // multiple) * multiple)


def preprocess(image_bytes: bytes, cfg: PreprocessConfig | None = None) -> bytes:
    """Resize / crop ``image_bytes`` per ``cfg``, return PNG/JPEG bytes."""
    cfg = cfg or PreprocessConfig()
    if not image_bytes:
        raise ValueError("image_bytes must be non-empty")
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "preprocess() requires Pillow; install via `uv pip install Pillow`."
        ) from exc

    # ``Image.open`` returns an :class:`ImageFile` subclass; subsequent
    # ``crop`` / ``resize`` / ``convert`` return the base :class:`Image`
    # class. Annotate the variable as the base so reassignments type
    # cleanly. ``Image.LANCZOS`` is the legacy alias still present on
    # Pillow >= 9.1; modern code prefers
    # :class:`Image.Resampling.LANCZOS` but stubs ship only the new
    # location, so we read via ``getattr`` for forward/back compat.
    img: Any = Image.open(io.BytesIO(image_bytes))
    lanczos = getattr(Image, "Resampling", Image).LANCZOS
    if cfg.roi is not None:
        x, y, w, h = cfg.roi
        if w <= 0 or h <= 0:
            raise ValueError(f"invalid ROI dims: {cfg.roi!r}")
        img = img.crop((x, y, x + w, y + h))

    long_edge = max(img.size)
    if cfg.target_long_edge and long_edge > cfg.target_long_edge:
        scale = cfg.target_long_edge / long_edge
        new_w = _round_to_multiple(int(img.size[0] * scale), cfg.multiple_of)
        new_h = _round_to_multiple(int(img.size[1] * scale), cfg.multiple_of)
        img = img.resize((new_w, new_h), lanczos)

    out = io.BytesIO()
    save_format = "PNG" if cfg.output_format == "png" else "JPEG"
    save_kwargs: dict[str, object] = {"optimize": True}
    if save_format == "JPEG":
        save_kwargs["quality"] = 92
        if img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")
    img.save(out, format=save_format, **save_kwargs)
    return out.getvalue()


def delta_image(before: bytes, after: bytes, *, threshold: int = 10) -> bytes:
    """Return a PNG highlighting per-pixel delta regions between two frames.

    Pixels with channel difference >= ``threshold`` are highlighted in red on
    the ``after`` background; rest grayscale. Used for verification ("did the
    UI react to my action?").
    """
    try:
        from PIL import Image, ImageChops
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("delta_image() requires Pillow") from exc

    a: Any = Image.open(io.BytesIO(before)).convert("RGB")
    b: Any = Image.open(io.BytesIO(after)).convert("RGB")
    lanczos = getattr(Image, "Resampling", Image).LANCZOS
    if a.size != b.size:
        b = b.resize(a.size, lanczos)
    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    if bbox is None:
        # No change — return after as grayscale to make this obvious.
        gray = b.convert("L").convert("RGB")
        out = io.BytesIO()
        gray.save(out, format="PNG", optimize=True)
        return out.getvalue()

    # Composite: gray background, highlight diff region with red overlay.
    base = b.convert("L").convert("RGB")
    overlay = Image.new("RGB", b.size, (255, 0, 0))
    mask = diff.convert("L").point(lambda v: 255 if v >= threshold else 0)
    composed = Image.composite(overlay, base, mask)
    out = io.BytesIO()
    composed.save(out, format="PNG", optimize=True)
    return out.getvalue()
