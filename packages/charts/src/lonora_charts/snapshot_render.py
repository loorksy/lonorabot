"""Rasterize only our server-generated SVG primitives; no SVG scripts or external resources."""

from io import BytesIO
from math import isfinite
from xml.etree.ElementTree import fromstring

from lonora_core.user_error import LonoraError
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin


def png_snapshot(svg: str) -> bytes:
    root = fromstring(svg)
    width, height = int(root.attrib["width"]), int(root.attrib["height"])
    if not (1 <= width <= 1920 and 1 <= height <= 2048):
        raise LonoraError("chart_snapshot_too_large", 413)
    image = Image.new("RGB", (width, height), "#111215")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 13)
    except OSError:
        font = ImageFont.load_default(size=13)
    labels: list[str] = []

    def number(value: str) -> float:
        parsed = float(value)
        if not isfinite(parsed):
            raise LonoraError("chart_snapshot_invalid", 409)
        return parsed

    for element in root:
        kind = element.tag.rsplit("}", 1)[-1]
        attrs = element.attrib
        if kind == "rect":
            if attrs.get("width") == "100%":
                continue
            x, y = number(attrs["x"]), number(attrs["y"])
            draw.rectangle(
                (x, y, x + number(attrs["width"]), y + number(attrs["height"])), fill=attrs["fill"]
            )
        elif kind == "line":
            draw.line(
                (
                    number(attrs["x1"]),
                    number(attrs["y1"]),
                    number(attrs["x2"]),
                    number(attrs["y2"]),
                ),
                fill=attrs["stroke"],
                width=1,
            )
        elif kind == "polyline":
            points = [
                tuple(number(value) for value in point.split(","))
                for point in attrs["points"].split()
            ]
            if len(points) >= 2:
                draw.line(points, fill=attrs["stroke"], width=2)
        elif kind == "text":
            text = element.text or ""
            labels.append(text)
            draw.text(
                (number(attrs["x"]), number(attrs["y"]) - 13), text, font=font, fill=attrs["fill"]
            )
        else:
            raise LonoraError("chart_snapshot_invalid", 409)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_itxt("Description", "\n".join(labels))
    output = BytesIO()
    image.save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()
