"""内置高品质示例图案生成器（无需外部素材即可一键体验简略/高清/还原三档效果差异）."""

from __future__ import annotations

import io
import math
from typing import Dict, List

from PIL import Image, ImageDraw


SAMPLE_ITEMS: List[Dict[str, str]] = [
    {"id": "orange_cat", "name": "橘猫铃铛", "tag": "萌宠头像 · 纯色背景可抠图"},
    {"id": "magic_mushroom", "name": "奇幻蘑菇", "tag": "童话徽章 · 鲜明色块对比"},
    {"id": "sunset_fuji", "name": "樱花晚霞", "tag": "风景渐变 · 最显三档细节差距"},
    {"id": "astro_bear", "name": "星际小熊", "tag": "潮玩公仔 · 丰富高光阴影"},
]


def _draw_radial_gradient(
    img: Image.Image,
    center: tuple[int, int],
    radius: int,
    inner_rgb: tuple[int, int, int],
    outer_rgb: tuple[int, int, int],
) -> None:
    w, h = img.size
    px = img.load()
    cx, cy = center
    for y in range(max(0, cy - radius), min(h, cy + radius)):
        for x in range(max(0, cx - radius), min(w, cx + radius)):
            d = math.hypot(x - cx, y - cy) / max(1.0, float(radius))
            if d <= 1.0:
                t = d * d * (3 - 2 * d)
                r = int(inner_rgb[0] * (1 - t) + outer_rgb[0] * t)
                g = int(inner_rgb[1] * (1 - t) + outer_rgb[1] * t)
                b = int(inner_rgb[2] * (1 - t) + outer_rgb[2] * t)
                px[x, y] = (r, g, b, 255)


def build_sample_png(sample_id: str) -> bytes:
    """绘制 360×360 的精致示例图并返回 PNG 字节流."""
    size = 360
    img = Image.new("RGBA", (size, size), (250, 244, 232, 255))
    draw = ImageDraw.Draw(img)

    if sample_id == "orange_cat":
        # 温暖米白纯色底（方便测试「智能去背景」一键抠出猫咪主体）
        draw.rectangle([0, 0, size, size], fill=(250, 245, 235, 255))
        # 双耳
        draw.polygon([(78, 145), (95, 52), (165, 102)], fill=(235, 138, 48), outline=(72, 40, 20), width=5)
        draw.polygon([(282, 145), (265, 52), (195, 102)], fill=(235, 138, 48), outline=(72, 40, 20), width=5)
        draw.polygon([(95, 132), (105, 72), (150, 105)], fill=(252, 182, 188))
        draw.polygon([(265, 132), (255, 72), (210, 105)], fill=(252, 182, 188))
        # 圆润猫脸与渐变立体毛色
        draw.ellipse([66, 92, 294, 288], fill=(246, 158, 58), outline=(72, 40, 20), width=6)
        draw.ellipse([86, 112, 274, 276], fill=(252, 182, 88))
        # 额头虎斑纹
        for dx in (-26, 0, 26):
            draw.rounded_rectangle([174 + dx, 98, 186 + dx, 138], radius=6, fill=(196, 98, 26))
        # 白色嘴套与粉嫩腮红
        draw.ellipse([116, 198, 244, 274], fill=(255, 250, 242))
        draw.ellipse([84, 196, 126, 224], fill=(253, 154, 168))
        draw.ellipse([234, 196, 276, 224], fill=(253, 154, 168))
        # 翡翠绿大眼睛 + 双高光
        for ex in (132, 228):
            draw.ellipse([ex - 25, 156, ex + 25, 206], fill=(34, 139, 87), outline=(36, 24, 18), width=4)
            draw.ellipse([ex - 13, 166, ex + 13, 196], fill=(22, 26, 32))
            draw.ellipse([ex - 15, 163, ex - 4, 174], fill=(255, 255, 255))
            draw.ellipse([ex + 5, 184, ex + 11, 190], fill=(200, 255, 230))
        # 粉色小鼻头与微笑嘴
        draw.polygon([(170, 208), (190, 208), (180, 220)], fill=(238, 102, 130))
        draw.arc([152, 214, 180, 238], start=10, end=170, fill=(72, 40, 20), width=4)
        draw.arc([180, 214, 208, 238], start=10, end=170, fill=(72, 40, 20), width=4)
        # 红色项圈与金色铃铛
        draw.rounded_rectangle([108, 274, 252, 298], radius=12, fill=(220, 38, 38), outline=(72, 40, 20), width=4)
        draw.ellipse([162, 282, 198, 318], fill=(255, 212, 0), outline=(120, 68, 12), width=4)
        draw.ellipse([175, 298, 185, 308], fill=(120, 68, 12))

    elif sample_id == "magic_mushroom":
        # 透明背景徽章风奇幻蘑菇
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # 草地底座
        draw.ellipse([78, 268, 282, 326], fill=(76, 175, 80, 255), outline=(27, 77, 46, 255), width=5)
        draw.ellipse([96, 276, 264, 312], fill=(139, 214, 92, 255))
        # 蘑菇柄（带暖色阴影）
        draw.polygon([(136, 188), (224, 188), (242, 292), (118, 292)], fill=(246, 232, 208, 255), outline=(88, 47, 14, 255), width=5)
        draw.polygon([(146, 194), (206, 194), (218, 286), (132, 286)], fill=(255, 248, 235, 255))
        # 可爱表情
        draw.ellipse([152, 228, 166, 244], fill=(35, 30, 36, 255))
        draw.ellipse([194, 228, 208, 244], fill=(35, 30, 36, 255))
        draw.ellipse([154, 230, 160, 236], fill=(255, 255, 255, 255))
        draw.ellipse([196, 230, 202, 236], fill=(255, 255, 255, 255))
        draw.ellipse([138, 244, 154, 254], fill=(255, 152, 172, 255))
        draw.ellipse([206, 244, 222, 254], fill=(255, 152, 172, 255))
        draw.arc([170, 238, 190, 254], start=15, end=165, fill=(88, 47, 14, 255), width=3)
        # 红色大伞盖 + 高光圆斑
        draw.chord([46, 56, 314, 262], start=180, end=360, fill=(225, 38, 52, 255), outline=(88, 20, 28, 255), width=6)
        draw.ellipse([48, 142, 312, 182], fill=(225, 38, 52, 255), outline=(88, 20, 28, 255), width=5)
        for bx, by, br in [(180, 96, 26), (112, 126, 22), (246, 128, 20), (154, 150, 15), (214, 154, 14)]:
            draw.ellipse([bx - br, by - br, bx + br, by + br], fill=(255, 249, 236, 255))

    elif sample_id == "sunset_fuji":
        # 渐变晚霞富士山与樱花（最能展现简略/高清/还原在渐变天空上的巨大差异）
        px = img.load()
        stops = [
            (0.0, (49, 46, 129)),
            (0.32, (162, 28, 175)),
            (0.62, (249, 115, 22)),
            (0.85, (253, 224, 71)),
            (1.0, (254, 240, 138)),
        ]
        for y in range(size):
            t = y / float(size - 1)
            for idx in range(len(stops) - 1):
                t0, c0 = stops[idx]
                t1, c1 = stops[idx + 1]
                if t0 <= t <= t1:
                    lt = (t - t0) / (t1 - t0)
                    rc = int(c0[0] + (c1[0] - c0[0]) * lt)
                    gc = int(c0[1] + (c1[1] - c0[1]) * lt)
                    bc = int(c0[2] + (c1[2] - c0[2]) * lt)
                    for x in range(size):
                        px[x, y] = (rc, gc, bc, 255)
                    break
        # 落日圆盘
        draw.ellipse([130, 72, 230, 172], fill=(255, 245, 190))
        # 远山与雪顶富士山
        draw.polygon([(20, 285), (180, 128), (340, 285)], fill=(30, 58, 138))
        draw.polygon([(128, 179), (180, 128), (232, 179), (212, 192), (195, 176), (180, 194), (164, 177), (148, 190)], fill=(248, 250, 252))
        # 湖面倒影深蓝与波光
        draw.rectangle([0, 282, size, size], fill=(23, 37, 84))
        for wy in range(294, 350, 12):
            wlen = 90 - (wy - 294)
            draw.line([(180 - wlen // 2, wy), (180 + wlen // 2, wy)], fill=(251, 146, 60), width=4)
        # 前景樱花枝
        draw.line([(0, 65), (118, 92), (156, 76)], fill=(68, 34, 28), width=6)
        for sx, sy in [(42, 62), (82, 84), (118, 68), (148, 86), (298, 56), (324, 92)]:
            draw.ellipse([sx - 16, sy - 16, sx + 16, sy + 16], fill=(251, 182, 206))
            draw.ellipse([sx - 6, sy - 6, sx + 6, sy + 6], fill=(236, 72, 153))

    else:
        # 星际小熊宇航员
        _draw_radial_gradient(img, (180, 180), 250, (37, 56, 118), (15, 23, 42))
        draw = ImageDraw.Draw(img)
        # 星星与环状星球
        for sx, sy, sr in [(48, 56, 4), (310, 62, 5), (62, 290, 3), (308, 278, 4), (288, 140, 3)]:
            draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(254, 240, 138))
        draw.ellipse([258, 36, 322, 100], fill=(56, 189, 248))
        draw.arc([240, 54, 340, 88], start=160, end=380, fill=(253, 224, 71), width=4)
        # 宇航服身体
        draw.rounded_rectangle([108, 226, 252, 336], radius=34, fill=(241, 245, 249), outline=(71, 85, 105), width=5)
        draw.rounded_rectangle([146, 256, 214, 296], radius=8, fill=(59, 130, 246))
        draw.ellipse([156, 268, 172, 284], fill=(239, 68, 68))
        draw.ellipse([184, 268, 200, 284], fill=(34, 197, 94))
        # 头盔外圈与小熊耳朵
        draw.ellipse([86, 76, 138, 128], fill=(180, 118, 72), outline=(71, 85, 105), width=5)
        draw.ellipse([222, 76, 274, 128], fill=(180, 118, 72), outline=(71, 85, 105), width=5)
        draw.ellipse([78, 76, 282, 264], fill=(248, 250, 252), outline=(71, 85, 105), width=6)
        draw.ellipse([96, 96, 264, 246], fill=(30, 41, 59))
        # 仓内棕色小熊脸
        draw.ellipse([116, 114, 244, 232], fill=(196, 132, 82))
        draw.ellipse([148, 176, 212, 220], fill=(250, 228, 202))
        draw.ellipse([142, 152, 160, 170], fill=(24, 24, 27))
        draw.ellipse([200, 152, 218, 170], fill=(24, 24, 27))
        draw.ellipse([172, 182, 188, 194], fill=(88, 47, 14))
        # 头盔玻璃高光弧
        draw.arc([108, 106, 246, 226], start=200, end=255, fill=(186, 230, 253), width=7)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
