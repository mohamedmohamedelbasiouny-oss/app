"""توليد أيقونة البرنامج (icon.ico + icon.png) بـ Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, S - 16, S - 16), radius=110, fill=(28, 28, 31, 255),
                    outline=(60, 60, 66, 255), width=6)
levels = [0.62, 0.62, 0.5, 0.5, 0.42, 0.42, 0.3, 0.3, 0.42, 0.5, 0.5, 0.62, 0.62]
pts = []
n = len(levels) - 1
for i in range(n):
    x0 = 80 + i * (S - 160) / n
    x1 = 80 + (i + 1) * (S - 160) / n
    pts += [(x0, levels[i] * S), (x1, levels[i] * S)]
d.line(pts, fill=(90, 169, 255, 255), width=26, joint="curve")
d.ellipse((S * 0.5 - 30, S * 0.76 - 30, S * 0.5 + 30, S * 0.76 + 30),
          outline=(242, 242, 244, 255), width=12)
d.line((S * 0.5 - 30, S * 0.56, S * 0.5 - 30, S * 0.76), fill=(242, 242, 244, 255), width=12)
img.save(HERE / "icon.png")
img.save(HERE / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                   (128, 128), (256, 256)])
print("icon ok")
