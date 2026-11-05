from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
SCALE = 4
SIZE = 256
canvas = Image.new("RGBA", (SIZE * SCALE, SIZE * SCALE), (0, 0, 0, 0))
draw = ImageDraw.Draw(canvas)


def box(coords):
    return tuple(int(v * SCALE) for v in coords)


for y in range(SIZE * SCALE):
    t = y / (SIZE * SCALE - 1)
    top = (39, 30, 54)
    bottom = (12, 14, 22)
    color = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3)) + (255,)
    draw.line((0, y, SIZE * SCALE, y), fill=color)
draw.rounded_rectangle(box((8, 8, 248, 248)), radius=54 * SCALE, outline=(232, 164, 203, 230), width=3 * SCALE)

font_path = Path("C:/Windows/Fonts/segoeuib.ttf")
font = ImageFont.truetype(str(font_path), 106 * SCALE) if font_path.exists() else ImageFont.truetype("arialbd.ttf", 106 * SCALE)
draw.text((39 * SCALE, 67 * SCALE), "GP", font=font, fill=(250, 248, 255, 255), stroke_width=0)

# Accent string and note mark make the monogram recognizable at small sizes.
draw.rounded_rectangle(box((37, 41, 42, 74)), radius=3 * SCALE, fill=(232, 164, 203, 255))
draw.ellipse(box((31, 68, 47, 81)), fill=(232, 164, 203, 255))
draw.line((59 * SCALE, 197 * SCALE, 198 * SCALE, 197 * SCALE), fill=(169, 139, 231, 220), width=4 * SCALE)

image = canvas.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
image.save(ROOT / "gpbridge.ico", format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
image.save(ROOT / "gpbridge-icon.png")
