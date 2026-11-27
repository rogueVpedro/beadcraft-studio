"""高清拼豆施工图纸 (PNG) 与色号采购清单 (Excel .xlsx) 导出模块."""

from __future__ import annotations

import io
import math
import os
from typing import Dict, List

from PIL import Image, ImageDraw, ImageFont
import xlsxwriter


def _load_cjk_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """优先加载 Windows 系统内置微软雅黑/黑体以清晰渲染中文与色号."""
    candidates = (
        [
            r"C:\Windows\Fonts\msyhbd.ttc",
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
        ]
        if bold
        else [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\simsun.ttc",
        ]
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def export_blueprint_png(pattern: Dict, skill_level: str = "standard", bead_style: str = "code_block") -> bytes:
    """生成带坐标轴、29×29 分板辅助线、每格色号标注、预估时长及底部材料表的可打印高清 PNG 图纸."""
    grid: List[List[int]] = pattern["grid"]
    gw: int = pattern["grid_width"]
    gh: int = pattern["grid_height"]
    bom: List[Dict] = pattern["bom"]
    lookup: Dict[str, Dict] = pattern["palette_lookup"]
    est: Dict = pattern["time_estimate"]
    prof = est["profiles"].get(skill_level, est["profiles"]["standard"])

    # 根据网格大小自适应单颗格子的像素尺寸，保证文字锐利可读且图片尺寸合理
    cell = 28 if max(gw, gh) <= 44 else (24 if max(gw, gh) <= 68 else 20)
    ruler_margin = 36
    side_pad = 36
    header_h = 128

    board_px_w = gw * cell
    board_px_h = gh * cell
    min_canvas_w = 960
    canvas_w = max(min_canvas_w, board_px_w + ruler_margin * 2 + side_pad * 2)

    # 计算底部色号清单排布（每行排 4~6 列）
    bom_cols = max(3, min(6, (canvas_w - side_pad * 2) // 175))
    bom_rows = max(1, math.ceil(len(bom) / bom_cols))
    bom_row_h = 38
    legend_h = 80 + bom_rows * bom_row_h + 36

    canvas_h = header_h + ruler_margin * 2 + board_px_h + legend_h
    img = Image.new("RGB", (canvas_w, canvas_h), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    font_title = _load_cjk_font(26, bold=True)
    font_sub = _load_cjk_font(15, bold=False)
    font_tag = _load_cjk_font(14, bold=True)
    font_ruler = _load_cjk_font(max(9, cell // 2 - 2), bold=False)
    font_code = _load_cjk_font(max(8, int(cell * 0.40)), bold=True)
    font_bom = _load_cjk_font(13, bold=False)
    font_bom_b = _load_cjk_font(13, bold=True)

    # 1. 绘制顶部深色信息抬头栏
    draw.rectangle([0, 0, canvas_w, header_h - 14], fill=(24, 28, 38))
    title_text = f"拼豆工坊 · 施工图纸  [{pattern['quality_name']}画质 · {pattern['quality_badge']}]"
    draw.text((side_pad, 20), title_text, fill=(255, 255, 255), font=font_title)

    mini_sz = pattern["physical_size_cm"]["mini_26mm"]
    std_sz = pattern["physical_size_cm"]["standard_50mm"]
    meta_line1 = (
        f"网格尺寸: {gw} × {gh} 格   |   总用豆量: {pattern['total_beads']:,} 颗   |   "
        f"色号种类: {pattern['unique_colors']} 色   |   色卡: {pattern['palette_name']}"
    )
    meta_line2 = (
        f"预估拼豆时长 ({prof['label']}): {prof['formatted']} "
        f"(分色 {prof['breakdown_minutes']['prep']}m + 摆豆 {prof['breakdown_minutes']['placing'] + prof['breakdown_minutes']['detail']}m + 熨烫 {prof['breakdown_minutes']['ironing']}m)   |   "
        f"成品约 {mini_sz['width']}×{mini_sz['height']}cm (2.6mm小豆) / {std_sz['width']}×{std_sz['height']}cm (5mm大豆)"
    )
    draw.text((side_pad, 60), meta_line1, fill=(203, 213, 225), font=font_sub)
    draw.text((side_pad, 84), meta_line2, fill=(125, 211, 252), font=font_sub)

    # 2. 计算图纸居中起始坐标
    origin_x = (canvas_w - board_px_w) // 2
    origin_y = header_h + ruler_margin

    # 绘制网格白底与柔和阴影外框
    draw.rectangle(
        [origin_x - 2, origin_y - 2, origin_x + board_px_w + 2, origin_y + board_px_h + 2],
        fill=(255, 255, 255),
        outline=(148, 163, 184),
        width=2,
    )

    # 3. 绘制每一颗拼豆与内部色号文字
    for r in range(gh):
        y0 = origin_y + r * cell
        y1 = y0 + cell
        row = grid[r]
        for c in range(gw):
            x0 = origin_x + c * cell
            x1 = x0 + cell
            val = row[c]
            if val < 0:
                # 透明无豆格：绘制极淡棋盘小圆点示意空针位
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(226, 232, 240))
                continue

            cinfo = lookup[str(val)]
            hex_col = cinfo["hex"]
            rgb = (int(hex_col[1:3], 16), int(hex_col[3:5], 16), int(hex_col[5:7], 16))
            txt_col = (15, 20, 28) if cinfo["text_color"] in ("#000000", "#0F141C", "#1A1D24") else (255, 255, 255)

            if bead_style == "bead_ring":
                # 圆环拼豆立体样式
                pad = max(1, cell // 14)
                draw.ellipse([x0 + pad, y0 + pad, x1 - pad, y1 - pad], fill=rgb, outline=(30, 41, 59, 60))
                hole_r = max(2, int(cell * 0.20))
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                draw.ellipse([cx - hole_r, cy - hole_r, cx + hole_r, cy + hole_r], fill=(248, 250, 252))
            elif bead_style == "flat_pixel":
                # 熨烫融合平面像素样式（无字纯净色块）
                draw.rectangle([x0, y0, x1, y1], fill=rgb)
            else:
                # 施工色号方块样式（最适合对照实操摆豆）
                draw.rectangle([x0, y0, x1, y1], fill=rgb)
                code_str = cinfo["code"]
                bbox = draw.textbbox((0, 0), code_str, font=font_code)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                tx = x0 + (cell - tw) / 2.0
                ty = y0 + (cell - th) / 2.0 - 1
                draw.text((tx, ty), code_str, fill=txt_col, font=font_code)

    # 4. 绘制细网格线、5格辅助线与 29×29 拼板粗红蓝分界线
    for c in range(gw + 1):
        x = origin_x + c * cell
        if c > 0 and c < gw and c % 29 == 0:
            draw.line([(x, origin_y), (x, origin_y + board_px_h)], fill=(239, 68, 68), width=3)
        elif c % 5 == 0:
            draw.line([(x, origin_y), (x, origin_y + board_px_h)], fill=(100, 116, 139), width=1)
        else:
            draw.line([(x, origin_y), (x, origin_y + board_px_h)], fill=(203, 213, 225), width=1)

    for r in range(gh + 1):
        y = origin_y + r * cell
        if r > 0 and r < gh and r % 29 == 0:
            draw.line([(origin_x, y), (origin_x + board_px_w, y)], fill=(239, 68, 68), width=3)
        elif r % 5 == 0:
            draw.line([(origin_x, y), (origin_x + board_px_w, y)], fill=(100, 116, 139), width=1)
        else:
            draw.line([(origin_x, y), (origin_x + board_px_w, y)], fill=(203, 213, 225), width=1)

    # 5. 绘制四周行列坐标尺（每格或每2格标注，清晰对位）
    col_step = 1 if gw <= 60 else 2
    for c in range(0, gw, col_step):
        num = str(c + 1)
        cx = origin_x + c * cell + cell // 2
        bbox = draw.textbbox((0, 0), num, font=font_ruler)
        tw = bbox[2] - bbox[0]
        col_fill = (220, 38, 38) if ((c + 1) % 29 == 0) else ((30, 41, 59) if (c + 1) % 5 == 0 else (100, 116, 139))
        draw.text((cx - tw / 2, origin_y - 20), num, fill=col_fill, font=font_ruler)
        draw.text((cx - tw / 2, origin_y + board_px_h + 6), num, fill=col_fill, font=font_ruler)

    row_step = 1 if gh <= 60 else 2
    for r in range(0, gh, row_step):
        num = str(r + 1)
        cy = origin_y + r * cell + cell // 2
        bbox = draw.textbbox((0, 0), num, font=font_ruler)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        row_fill = (220, 38, 38) if ((r + 1) % 29 == 0) else ((30, 41, 59) if (r + 1) % 5 == 0 else (100, 116, 139))
        draw.text((origin_x - tw - 8, cy - th / 2 - 1), num, fill=row_fill, font=font_ruler)
        draw.text((origin_x + board_px_w + 8, cy - th / 2 - 1), num, fill=row_fill, font=font_ruler)

    # 6. 绘制底部色号材料核对清单 (Color Legend & BOM)
    legend_top = origin_y + board_px_h + ruler_margin + 14
    draw.line([(side_pad, legend_top), (canvas_w - side_pad, legend_top)], fill=(203, 213, 225), width=2)
    draw.text(
        (side_pad, legend_top + 12),
        f"色号材料用量清单（共 {len(bom)} 种色号，合计 {pattern['total_beads']:,} 颗 · 红线代表 29×29 标准大模板分界）",
        fill=(15, 23, 42),
        font=font_tag,
    )

    col_w = (canvas_w - side_pad * 2) // bom_cols
    start_y = legend_top + 46
    for idx, item in enumerate(bom):
        r_idx = idx // bom_cols
        c_idx = idx % bom_cols
        bx = side_pad + c_idx * col_w
        by = start_y + r_idx * bom_row_h

        # 复选框 + 色块 + 色号名称 + 颗数
        draw.rectangle([bx, by + 6, bx + 14, by + 20], outline=(148, 163, 184), width=1, fill=(255, 255, 255))
        hc = item["hex"]
        srgb = (int(hc[1:3], 16), int(hc[3:5], 16), int(hc[5:7], 16))
        draw.rounded_rectangle([bx + 20, by + 2, bx + 56, by + 25], radius=4, fill=srgb, outline=(100, 116, 139))

        txt_c = (15, 20, 28) if item["text_color"] in ("#000000", "#0F141C", "#1A1D24") else (255, 255, 255)
        cbbox = draw.textbbox((0, 0), item["code"], font=font_bom_b)
        cw = cbbox[2] - cbbox[0]
        draw.text((bx + 20 + (36 - cw) / 2, by + 4), item["code"], fill=txt_c, font=font_bom_b)

        label_str = f"{item['name']}  ×{item['count']}"
        draw.text((bx + 64, by + 4), label_str, fill=(30, 41, 59), font=font_bom)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def export_bom_xlsx(pattern: Dict) -> bytes:
    """导出包含真实色块底色、色号、建议备豆量（+5%防丢余量）与时长拆解的 Excel 采购表."""
    out = io.BytesIO()
    wb = xlsxwriter.Workbook(out, {"in_memory": True})

    ws = wb.add_worksheet("拼豆材料与时长清单")
    ws.set_column("A:A", 10)
    ws.set_column("B:B", 12)
    ws.set_column("C:C", 16)
    ws.set_column("D:D", 14)
    ws.set_column("E:E", 18)
    ws.set_column("F:F", 12)

    title_fmt = wb.add_format({"bold": True, "font_size": 14, "font_color": "#0F172A"})
    meta_fmt = wb.add_format({"font_size": 10, "font_color": "#475569"})
    hdr_fmt = wb.add_format(
        {"bold": True, "bg_color": "#1E293B", "font_color": "#FFFFFF", "border": 1, "align": "center"}
    )
    cell_fmt = wb.add_format({"border": 1, "align": "center"})

    est = pattern["time_estimate"]
    std_prof = est["profiles"]["standard"]

    ws.write("A1", f"拼豆工坊材料清单 - {pattern['quality_name']}模式 ({pattern['grid_width']}×{pattern['grid_height']})", title_fmt)
    ws.write(
        "A2",
        f"色卡: {pattern['palette_name']} | 总豆数: {pattern['total_beads']} 颗 | 色号数: {pattern['unique_colors']} 种 | 预估时长(日常玩家): {std_prof['formatted']}",
        meta_fmt,
    )

    headers = ["颜色预览", "色号", "颜色名称", "图纸净用量(颗)", "建议备豆量(+5%)", "占比(%)"]
    for col_i, h_text in enumerate(headers):
        ws.write(3, col_i, h_text, hdr_fmt)

    for row_i, item in enumerate(pattern["bom"], start=4):
        swatch_fmt = wb.add_format(
            {
                "bg_color": item["hex"],
                "font_color": item["text_color"],
                "bold": True,
                "border": 1,
                "align": "center",
            }
        )
        safe_cnt = max(item["count"] + 2, int(math.ceil(item["count"] * 1.05)))
        ws.write(row_i, 0, item["hex"], swatch_fmt)
        ws.write(row_i, 1, item["code"], cell_fmt)
        ws.write(row_i, 2, item["name"], cell_fmt)
        ws.write(row_i, 3, item["count"], cell_fmt)
        ws.write(row_i, 4, safe_cnt, cell_fmt)
        ws.write(row_i, 5, f"{item['percentage']}%", cell_fmt)

    wb.close()
    return out.getvalue()
