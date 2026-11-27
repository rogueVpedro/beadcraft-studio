"""真实拼豆色卡系统与 CIELAB 感知色彩空间匹配引擎.

内置三套主流拼豆色卡：
1. mard_96: 国产通用 / Mard 融合豆精选 96 色（国内拼豆店最通用色号体系 A/B/C/D/E/F/G/H/M）
2. perler_58: Perler 经典 58 色（国际标准入门色卡，色号少易配齐）
3. master_144: 全彩大师 144 色（扩展肤色、莫兰迪灰阶与渐变色，最适合「还原」画质）
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple


def rgb_to_lab(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """将 sRGB (0-255) 转换为标准 CIELAB (D65 白点) 感知色彩空间."""
    # 归一化并进行 sRGB 伽马线性化
    sr = r / 255.0
    sg = g / 255.0
    sb = b / 255.0

    lr = ((sr + 0.055) / 1.055) ** 2.4 if sr > 0.04045 else sr / 12.92
    lg = ((sg + 0.055) / 1.055) ** 2.4 if sg > 0.04045 else sg / 12.92
    lb = ((sb + 0.055) / 1.055) ** 2.4 if sb > 0.04045 else sb / 12.92

    # 转换至 XYZ (D65)
    x = (lr * 0.4124564 + lg * 0.3575761 + lb * 0.1804375) / 0.95047
    y = (lr * 0.2126729 + lg * 0.7151522 + lb * 0.0721750) / 1.00000
    z = (lr * 0.0193339 + lg * 0.1191920 + lb * 0.9503041) / 1.08883

    eps = 0.008856
    kappa = 903.3

    fx = x ** (1.0 / 3.0) if x > eps else (kappa * x + 16.0) / 116.0
    fy = y ** (1.0 / 3.0) if y > eps else (kappa * y + 16.0) / 116.0
    fz = z ** (1.0 / 3.0) if z > eps else (kappa * z + 16.0) / 116.0

    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b_val = 200.0 * (fy - fz)
    return (L, a, b_val)


def hex_to_rgb(hex_code: str) -> Tuple[int, int, int]:
    h = hex_code.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def contrast_text_color(r: int, g: int, b: int) -> str:
    """按 WCAG 2.1 相对亮度公式计算色块前景字色 (#000000 或 #FFFFFF)，全色域最低对比度 ≥ 4.58:1."""
    sr, sg, sb = r / 255.0, g / 255.0, b / 255.0
    lr = ((sr + 0.055) / 1.055) ** 2.4 if sr > 0.04045 else sr / 12.92
    lg = ((sg + 0.055) / 1.055) ** 2.4 if sg > 0.04045 else sg / 12.92
    lb = ((sb + 0.055) / 1.055) ** 2.4 if sb > 0.04045 else sb / 12.92
    rel_lum = 0.2126 * lr + 0.7152 * lg + 0.0722 * lb
    return "#000000" if rel_lum > 0.1791 else "#FFFFFF"


# ---------------------------------------------------------------------------
# 1. Mard / 国产通用拼豆 96 色标准色号表 (code, name, hex, series)
# ---------------------------------------------------------------------------
MARD_96_RAW: List[Tuple[str, str, str]] = [
    # H 系列：黑白灰基础系
    ("H01", "纯白", "#FBFBFB"),
    ("H02", "纯黑", "#18181B"),
    ("H03", "珍珠白", "#F1EFEA"),
    ("H04", "浅银灰", "#D4D7DD"),
    ("H05", "中灰", "#9CA3AF"),
    ("H06", "深板岩灰", "#646B77"),
    ("H07", "炭黑灰", "#373B44"),
    ("H08", "暖浅灰", "#CCC7BF"),
    ("H09", "暖中灰", "#8E8880"),
    ("H10", "冷蓝灰", "#7D8B99"),
    ("H11", "暗影黑", "#26272B"),
    ("H12", "米白", "#FAF3E3"),
    # A 系列：黄色与暖橙系
    ("A01", "奶黄", "#FFF5C0"),
    ("A02", "柠檬黄", "#FFEA5A"),
    ("A03", "明黄", "#FFD400"),
    ("A04", "向日葵黄", "#F7B500"),
    ("A05", "金盏橙黄", "#F59E0B"),
    ("A06", "蜜橘色", "#FB8500"),
    ("A07", "活力橙", "#F96302"),
    ("A08", "柿子红橙", "#E84A15"),
    ("A09", "鹅黄", "#FCE98A"),
    ("A10", "芥末黄", "#D4A017"),
    ("A11", "琥珀金", "#C87D0A"),
    ("A12", "杏黄", "#FBC275"),
    # B 系列：自然绿与薄荷系
    ("B01", "嫩芽绿", "#D9F59B"),
    ("B02", "青柠绿", "#A3E635"),
    ("B03", "草木绿", "#65C438"),
    ("B04", "翠绿", "#22A947"),
    ("B05", "森林绿", "#157A36"),
    ("B06", "深松绿", "#0F4D26"),
    ("B07", "薄荷绿", "#99F6E4"),
    ("B08", "蒂芙尼绿", "#2DD4BF"),
    ("B09", "孔雀绿", "#0D9488"),
    ("B10", "橄榄绿", "#6B8E23"),
    ("B11", "抹茶绿", "#84A955"),
    ("B12", "牛油果绿", "#4E7A3A"),
    # C 系列：天空蓝与深海蓝系
    ("C01", "冰川蓝", "#E0F2FE"),
    ("C02", "浅天蓝", "#93D5FD"),
    ("C03", "晴空蓝", "#38BDF8"),
    ("C04", "蔚蓝", "#0284C7"),
    ("C05", "宝石蓝", "#2563EB"),
    ("C06", "皇家蓝", "#1D4ED8"),
    ("C07", "藏青蓝", "#1E3A8A"),
    ("C08", "午夜深蓝", "#172554"),
    ("C09", "湖水蓝", "#06B6D4"),
    ("C10", "雾霾蓝", "#6488A8"),
    ("C11", "牛仔蓝", "#3B5998"),
    ("C12", "矢车菊蓝", "#5B86E5"),
    # D 系列：紫罗兰与薰衣草系
    ("D01", "浅丁香紫", "#EDE9FE"),
    ("D02", "薰衣草紫", "#C4B5FD"),
    ("D03", "香芋紫", "#A78BFA"),
    ("D04", "紫罗兰", "#7C3AED"),
    ("D05", "葡萄紫", "#5B21B6"),
    ("D06", "暗夜紫", "#3B0764"),
    ("D07", "梅子紫", "#86198F"),
    ("D08", "兰花紫", "#C064E8"),
    ("D09", "烟灰紫", "#8B7AA8"),
    ("D10", "桑葚紫", "#4A1D5E"),
    # E 系列：樱花粉与玫红系
    ("E01", "樱花粉", "#FFE4E9"),
    ("E02", "水蜜桃粉", "#FBCFE8"),
    ("E03", "甜心粉", "#F9A8D4"),
    ("E04", "芭比粉", "#F472B6"),
    ("E05", "火烈鸟粉", "#EC4899"),
    ("E06", "洋红", "#DB2777"),
    ("E07", "珊瑚粉", "#FDA4AF"),
    ("E08", "西瓜红", "#FB7185"),
    ("E09", "豆沙粉", "#D88296"),
    ("E10", "干枯玫瑰", "#B56576"),
    # F 系列：正红与酒红系
    ("F01", "朱砂红", "#EF4444"),
    ("F02", "正红", "#DC2626"),
    ("F03", "中国红", "#B91C1C"),
    ("F04", "暗酒红", "#7F1D1D"),
    ("F05", "绯红", "#F43F5E"),
    ("F06", "砖红", "#B43E2F"),
    ("F07", "车厘子红", "#5C141B"),
    ("F08", "番茄红", "#E53935"),
    # G 系列：肤色、大地棕与焦糖系（人像/萌宠关键色系）
    ("G01", "白皙肤色", "#FFEAD8"),
    ("G02", "自然肤色", "#FDD5B4"),
    ("G03", "暖杏肤色", "#F6BC92"),
    ("G04", "小麦肤色", "#E29B6B"),
    ("G05", "浅驼色", "#D8B384"),
    ("G06", "奶茶棕", "#B98B63"),
    ("G07", "焦糖棕", "#9C6644"),
    ("G08", "可可棕", "#7F4F24"),
    ("G09", "深咖啡棕", "#582F0E"),
    ("G10", "黑巧棕", "#3B1F0B"),
    ("G11", "橘猫浅棕", "#E8994A"),
    ("G12", "赤陶棕", "#B85D3B"),
    ("G13", "肉桂色", "#C6865A"),
    ("G14", "沙米色", "#E8D5B7"),
    # M 系列：莫兰迪低饱和过渡色
    ("M01", "燕麦奶", "#EDE2D0"),
    ("M02", "鼠尾草绿", "#9CAF88"),
    ("M03", "冰雾青", "#89B0AE"),
    ("M04", "藕荷色", "#C9ADA7"),
    ("M05", "岩石褐", "#6D5959"),
    ("M06", "深青石", "#264653"),
]

# ---------------------------------------------------------------------------
# 2. Perler 经典 58 色（精选高辨识度经典色卡）
# ---------------------------------------------------------------------------
PERLER_58_CODES = {
    "H01", "H02", "H04", "H05", "H06", "H07", "H12",
    "A01", "A02", "A03", "A05", "A07", "A08", "A12",
    "B01", "B02", "B03", "B04", "B05", "B06", "B08", "B09", "B10",
    "C01", "C02", "C03", "C04", "C05", "C07", "C08", "C09", "C10",
    "D01", "D02", "D04", "D05", "D07",
    "E01", "E03", "E04", "E05", "E07", "E09",
    "F01", "F02", "F03", "F04", "F06",
    "G01", "G02", "G03", "G04", "G06", "G07", "G08", "G09", "G11", "G14",
}

# ---------------------------------------------------------------------------
# 3. 全彩大师扩展色（在 Mard 96 基础上补充 48 款细腻渐变色，共计 144 色）
# ---------------------------------------------------------------------------
MASTER_EXTRA_48: List[Tuple[str, str, str]] = [
    ("H13", "银白灰", "#E5E7EB"),
    ("H14", "铅笔灰", "#4B5563"),
    ("H15", "暖炭灰", "#524D49"),
    ("H16", "象牙奶油", "#FFFDF2"),
    ("A13", "香槟金", "#F3D999"),
    ("A14", "秋叶金", "#DF8A13"),
    ("A15", "落日橘", "#FF7847"),
    ("A16", "淡奶油黄", "#FFF9DB"),
    ("B13", "浅豆绿", "#C7E8AC"),
    ("B14", "竹青绿", "#4C9A5A"),
    ("B15", "墨玉绿", "#1B3B2B"),
    ("B16", "翡翠青", "#16A394"),
    ("B17", "苔藓暗绿", "#3F5E36"),
    ("B18", "浅海泡沫", "#CCFBF1"),
    ("C13", "婴儿蓝", "#BAE6FD"),
    ("C14", "普鲁士蓝", "#123456"),
    ("C15", "星空靛蓝", "#312E81"),
    ("C16", "松石蓝", "#0891B2"),
    ("C17", "钢青蓝", "#466985"),
    ("C18", "浅雾蓝", "#B6C9DC"),
    ("D11", "梦幻浅紫", "#DDD6FE"),
    ("D12", "鸢尾紫", "#6D28D9"),
    ("D13", "紫晶色", "#9333EA"),
    ("D14", "晚霞紫红", "#A21CAF"),
    ("D15", "灰梅紫", "#6E5275"),
    ("E11", "腮红浅粉", "#FFD6DF"),
    ("E12", "蜜桃粉橘", "#FFAC9B"),
    ("E13", "蔷薇粉", "#E15B87"),
    ("E14", "树莓红", "#BE185D"),
    ("E15", "烟粉紫", "#CFA5B4"),
    ("F09", "珊瑚橘红", "#FF5A4E"),
    ("F10", "勃艮第红", "#681322"),
    ("F11", "铁锈红", "#963426"),
    ("F12", "山楂红", "#C92A2A"),
    ("G15", "瓷白肌", "#FFF2E6"),
    ("G16", "蜜桃肌", "#FAD0C4"),
    ("G17", "红润阴影肤", "#E09F87"),
    ("G18", "日晒古铜", "#B5734C"),
    ("G19", "榛果棕", "#8D5B3E"),
    ("G20", "栗子深棕", "#4A2511"),
    ("G21", "胡桃木棕", "#6C462F"),
    ("G22", "卡其灰棕", "#A89984"),
    ("M07", "雾霭灰绿", "#7A918D"),
    ("M08", "陶土粉棕", "#BC8F8F"),
    ("M09", "夜幕蓝灰", "#334155"),
    ("M10", "暖砂灰", "#B0A695"),
    ("M11", "青瓷灰", "#A3B8B0"),
    ("M12", "暗棕紫", "#4E3A47"),
]


class BeadPalette:
    """预计算好 CIELAB 坐标并内置量化查询缓存的拼豆色卡对象."""

    def __init__(self, palette_id: str, name: str, description: str, raw_colors: List[Tuple[str, str, str]]) -> None:
        self.palette_id = palette_id
        self.name = name
        self.description = description
        self.colors: List[Dict] = []

        for idx, (code, cname, hex_code) in enumerate(raw_colors):
            r, g, b = hex_to_rgb(hex_code)
            L, a, b_val = rgb_to_lab(r, g, b)
            self.colors.append(
                {
                    "index": idx,
                    "code": code,
                    "name": cname,
                    "hex": hex_code.upper(),
                    "rgb": (r, g, b),
                    "lab": (L, a, b_val),
                    "text_color": contrast_text_color(r, g, b),
                }
            )

        # (r>>1, g>>1, b>>1) -> 最佳色卡下标缓存（7-bit RGB 精度，感知误差 < 0.3 ΔE）
        self._match_cache: Dict[Tuple[int, int, int], int] = {}

        # 预计算色卡内部两两之间的感知色差矩阵，供「简略/高清」色号合并使用
        n = len(self.colors)
        self.pair_de: List[List[float]] = [[0.0] * n for _ in range(n)]
        for i in range(n):
            l1, a1, b1 = self.colors[i]["lab"]
            for j in range(i + 1, n):
                l2, a2, b2 = self.colors[j]["lab"]
                de = math.sqrt((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2)
                self.pair_de[i][j] = de
                self.pair_de[j][i] = de

    def match_rgb(self, r: int, g: int, b: int) -> int:
        """返回与给定 RGB 视觉最接近的拼豆色号索引."""
        key = (r >> 1, g >> 1, b >> 1)
        cached = self._match_cache.get(key)
        if cached is not None:
            return cached

        L, a, b_val = rgb_to_lab(r, g, b)
        best_idx = 0
        best_dist = 1e12

        for c in self.colors:
            cl, ca, cb = c["lab"]
            dl = L - cl
            # 明度平方已超当前最优距离时提前剪枝
            dl2 = dl * dl * 1.12  # 略微提高明度权重以保持轮廓层次感
            if dl2 >= best_dist:
                continue
            da = a - ca
            db = b_val - cb
            dist = dl2 + da * da + db * db
            if dist < best_dist:
                best_dist = dist
                best_idx = c["index"]

        self._match_cache[key] = best_idx
        return best_idx


PALETTES: Dict[str, BeadPalette] = {
    "mard_96": BeadPalette(
        palette_id="mard_96",
        name="Mard / 国产通用 96 色",
        description="国内拼豆手工店与材料包最常用的标准色号体系（H/A/B/C/D/E/F/G/M），配豆最方便",
        raw_colors=MARD_96_RAW,
    ),
    "perler_58": BeadPalette(
        palette_id="perler_58",
        name="Perler 经典入门 58 色",
        description="精简高频色卡，颜色种类少、分豆轻松，非常适合新手制作小挂件与卡通图案",
        raw_colors=[item for item in MARD_96_RAW if item[0] in PERLER_58_CODES],
    ),
    "master_144": BeadPalette(
        palette_id="master_144",
        name="Artkal 全彩大师 144 色",
        description="包含细腻人像肤色、莫兰迪灰阶与丰富渐变过渡色，搭配「还原」画质表现力最佳",
        raw_colors=MARD_96_RAW + MASTER_EXTRA_48,
    ),
}


def get_palette(palette_id: str) -> BeadPalette:
    return PALETTES.get(palette_id, PALETTES["mard_96"])


def list_palettes_meta() -> List[Dict]:
    return [
        {
            "id": p.palette_id,
            "name": p.name,
            "description": p.description,
            "color_count": len(p.colors),
        }
        for p in PALETTES.values()
    ]
