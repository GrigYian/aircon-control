"""Generate the Windows application icon without storing a binary source asset."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


OUTPUT = Path(__file__).with_name("AirConControl.ico")
SIZE = 256


def main() -> None:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(SIZE):
        for x in range(SIZE):
            dx = x - SIZE / 2
            dy = y - SIZE / 2
            distance = min(1.0, (dx * dx + dy * dy) ** 0.5 / (SIZE * 0.72))
            pixels[x, y] = (
                int(38 - 12 * distance),
                int(166 - 58 * distance),
                int(247 - 12 * distance),
                255,
            )

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((7, 7, 249, 249), radius=58, outline=(255, 255, 255, 75), width=4)
    center = (128, 121)
    radius = 61
    line = (255, 255, 255, 245)
    draw.arc((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), 42, 318, fill=line, width=17)
    draw.rounded_rectangle((120, 46, 136, 124), radius=8, fill=line)
    draw.ellipse((113, 106, 143, 136), fill=(34, 143, 237, 255))
    draw.ellipse((120, 113, 136, 129), fill=line)
    image.save(OUTPUT, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
