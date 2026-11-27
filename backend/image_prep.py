"""Downscale photos before vision calls to keep token use low."""

from io import BytesIO

_MAX_EDGE = 1024
_JPEG_QUALITY = 70


def downscale_image(data: bytes, content_type: str = "image/jpeg") -> tuple[bytes, str]:
    try:
        from PIL import Image
    except ImportError:
        return data, content_type or "image/jpeg"
    try:
        image = Image.open(BytesIO(data))
    except Exception:
        return data, content_type or "image/jpeg"
    image = image.convert("RGB")
    image.thumbnail((_MAX_EDGE, _MAX_EDGE), Image.Resampling.LANCZOS)
    out = BytesIO()
    image.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return out.getvalue(), "image/jpeg"