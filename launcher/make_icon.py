"""生成拼豆工坊 Windows 原生多分辨率 .ico 图标."""

from pathlib import Path
from PIL import Image, ImageDraw


def build_ico(out_path: Path) -> None:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角深色底座
    draw.rounded_rectangle([8, 8, 248, 248], radius=54, fill=(22, 28, 42, 255), outline=(56, 189, 248, 255), width=6)

    # 四颗高光立体圆环拼豆
    beads = [
        (82, 82, (251, 113, 133)),   # 珊瑚粉红
        (174, 82, (250, 204, 21)),   # 明黄
        (82, 174, (56, 189, 248)),   # 晴空蓝
        (174, 174, (74, 222, 128)),  # 嫩翠绿
    ]
    r_outer = 38
    r_inner = 15
    for cx, cy, col in beads:
        draw.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], fill=col + (255,))
        draw.arc(
            [cx - r_outer + 7, cy - r_outer + 7, cx + r_outer - 7, cy + r_outer - 7],
            start=195,
            end=315,
            fill=(255, 255, 255, 190),
            width=6,
        )
        draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner], fill=(22, 28, 42, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="ICO", sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])


if __name__ == "__main__":
    build_ico(Path(__file__).resolve().parent / "app.ico")
    print("Icon generated successfully.")
