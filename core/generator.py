"""拼豆图案内容感知生成引擎（支持简略 / 高清 / 还原三档画质）.

核心流程：
1. 预处理与内容感知主体提取：支持透明通道保留、四角连通域智能纯色背景剔除与主体自动裁切对焦
2. 分档重采样与画质增强：
   - 简略 (simple): 长边默认 32 颗，高对比度轮廓强化 + 区域均值采样 + 强力近色合并 + 孤立噪点消除
   - 高清 (hd):     长边默认 58 颗（2×2 块 29 格标准板），Lanczos 锐利重采样 + 适度近色收敛 + 微噪点净化
   - 还原 (faithful): 长边默认 100 颗（2×2 块 50 格大板），高精度采样 + 受控 Floyd-Steinberg 感知误差扩散抖动
3. 统计色号用量清单 (BOM) 并联动科学拼豆时长预估模型
"""

from __future__ import annotations

from collections import Counter, deque
import io
import math
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from core.estimator import estimate_assembly_time
from core.palettes import BeadPalette, get_palette, rgb_to_lab


QUALITY_PRESETS: Dict[str, Dict] = {
    "simple": {
        "id": "simple",
        "name": "简略",
        "badge": "萌系挂件级",
        "default_max_side": 32,
        "min_side": 20,
        "max_side": 44,
        "description": "提炼核心色块与主体轮廓，自动精简相近色号，豆量少、极易上手",
        "contrast": 1.14,
        "saturation": 1.16,
        "sharpness": 1.28,
        "dither_strength": 0.0,
        "merge_de": 13.8,
        "min_color_ratio": 0.0085,
        "max_colors_hint": 15,
        "denoise_passes": 2,
    },
    "hd": {
        "id": "hd",
        "name": "高清",
        "badge": "标准摆件级",
        "default_max_side": 58,
        "min_side": 45,
        "max_side": 76,
        "description": "契合 2×2 块标准拼板尺寸，兼顾五官神态细节与合理的配豆种类",
        "contrast": 1.06,
        "saturation": 1.07,
        "sharpness": 1.15,
        "dither_strength": 0.0,
        "merge_de": 7.2,
        "min_color_ratio": 0.0020,
        "max_colors_hint": 32,
        "denoise_passes": 1,
    },
    "faithful": {
        "id": "faithful",
        "name": "还原",
        "badge": "大师画框级",
        "default_max_side": 100,
        "min_side": 78,
        "max_side": 128,
        "description": "高密度网格配合自适应感知抖动算法，细腻还原光影渐变与原画质感",
        "contrast": 1.02,
        "saturation": 1.03,
        "sharpness": 1.06,
        "dither_strength": 0.26,
        "merge_de": 3.2,
        "min_color_ratio": 0.0003,
        "max_colors_hint": 96,
        "denoise_passes": 0,
    },
}


def load_normalized_rgba(image_bytes: bytes, max_working_dim: int = 720) -> Image.Image:
    """加载图片、修正 EXIF 旋转并限制工作分辨率以保证毫秒级响应."""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGBA")
    w, h = img.size
    if max(w, h) > max_working_dim:
        scale = max_working_dim / float(max(w, h))
        img = img.resize(
            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
            Image.Resampling.LANCZOS,
        )
    return img


def remove_corner_background(img: Image.Image, tolerance_de: float = 18.5) -> Image.Image:
    """智能识别四角连通的纯色/近似纯色背景并转为透明（仅剔除外围背景，不误伤主体内部同色区域）."""
    # 先缩放至适中工作尺寸做连通域抠图，提升速度且边缘更平滑
    work = img.copy()
    w, h = work.size
    px = work.load()

    # 若原图已有超过 8% 的透明像素，说明本身就是带透明通道的抠图素材，直接返回
    transparent_cnt = 0
    step = max(1, (w * h) // 4000)
    sampled = 0
    for y in range(0, h, max(1, int(math.sqrt(step)))):
        for x in range(0, w, max(1, int(math.sqrt(step)))):
            sampled += 1
            if px[x, y][3] < 115:
                transparent_cnt += 1
    if sampled > 0 and (transparent_cnt / sampled) > 0.08:
        return work

    # 采集四角及四边中点作为候选背景种子色
    seed_coords = [
        (0, 0),
        (w - 1, 0),
        (0, h - 1),
        (w - 1, h - 1),
        (w // 2, 0),
        (0, h // 2),
        (w - 1, h // 2),
    ]
    seed_labs: List[Tuple[float, float, float]] = []
    for sx, sy in seed_coords:
        r, g, b, a = px[sx, sy]
        if a >= 115:
            seed_labs.append(rgb_to_lab(r, g, b))

    if len(seed_labs) < 2:
        return work

    # 判断四角颜色是否具有一致性（至少存在一对角点色差 < tolerance_de * 1.2，否则说明是满幅风景图不应强抠四角）
    primary_seed = None
    best_cluster_count = 0
    for sl in seed_labs:
        cnt = sum(
            1
            for other in seed_labs
            if math.sqrt((sl[0] - other[0]) ** 2 + (sl[1] - other[1]) ** 2 + (sl[2] - other[2]) ** 2)
            <= tolerance_de * 1.15
        )
        if cnt > best_cluster_count:
            best_cluster_count = cnt
            primary_seed = sl

    if primary_seed is None or best_cluster_count < 3:
        # 四周边缘色彩差异极大（如完整风景照），保留轻微四角检测以免破坏画面
        return work

    lab_cache: Dict[Tuple[int, int, int], Tuple[float, float, float]] = {}
    tol_sq = tolerance_de * tolerance_de
    sl0, sa0, sb0 = primary_seed

    def is_bg_pixel(x: int, y: int) -> bool:
        r, g, b, a = px[x, y]
        if a < 115:
            return True
        key = (r >> 2, g >> 2, b >> 2)
        lab = lab_cache.get(key)
        if lab is None:
            lab = rgb_to_lab(r, g, b)
            lab_cache[key] = lab
        dist_sq = (lab[0] - sl0) ** 2 + (lab[1] - sa0) ** 2 + (lab[2] - sb0) ** 2
        return dist_sq <= tol_sq

    visited = bytearray(w * h)
    queue: deque[Tuple[int, int]] = deque()

    # 从四条边界上的匹配像素开始向内洪泛
    for x in range(w):
        for y in (0, h - 1):
            idx = y * w + x
            if not visited[idx] and is_bg_pixel(x, y):
                visited[idx] = 1
                queue.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            idx = y * w + x
            if not visited[idx] and is_bg_pixel(x, y):
                visited[idx] = 1
                queue.append((x, y))

    while queue:
        cx, cy = queue.popleft()
        r, g, b, _ = px[cx, cy]
        px[cx, cy] = (r, g, b, 0)

        if cx > 0:
            ni = cy * w + (cx - 1)
            if not visited[ni] and is_bg_pixel(cx - 1, cy):
                visited[ni] = 1
                queue.append((cx - 1, cy))
        if cx + 1 < w:
            ni = cy * w + (cx + 1)
            if not visited[ni] and is_bg_pixel(cx + 1, cy):
                visited[ni] = 1
                queue.append((cx + 1, cy))
        if cy > 0:
            ni = (cy - 1) * w + cx
            if not visited[ni] and is_bg_pixel(cx, cy - 1):
                visited[ni] = 1
                queue.append((cx, cy - 1))
        if cy + 1 < h:
            ni = (cy + 1) * w + cx
            if not visited[ni] and is_bg_pixel(cx, cy + 1):
                visited[ni] = 1
                queue.append((cx, cy + 1))

    return work


def crop_to_content(img: Image.Image) -> Image.Image:
    """自动裁切四周完全透明的空白边缘，让有效图案最大化利用拼豆网格."""
    alpha = img.getchannel("A")
    # 将 alpha >= 100 视为有效内容
    mask = alpha.point(lambda a: 255 if a >= 100 else 0)
    bbox = mask.getbbox()
    if not bbox:
        return img
    # 保留 1px 安全呼吸边距防止贴边裁切伪影
    w, h = img.size
    left = max(0, bbox[0] - 1)
    top = max(0, bbox[1] - 1)
    right = min(w, bbox[2] + 1)
    bottom = min(h, bbox[3] + 1)
    return img.crop((left, top, right, bottom))


def _consolidate_colors(
    grid: List[List[int]],
    palette: BeadPalette,
    merge_de: float,
    min_color_ratio: float,
    max_colors_hint: int,
) -> List[List[int]]:
    """根据画质档位智能合并极少量的杂色与肉眼难辨的近色，减少不必要的配豆负担."""
    counts: Counter = Counter()
    total_beads = 0
    for row in grid:
        for val in row:
            if val >= 0:
                counts[val] += 1
                total_beads += 1

    if total_beads == 0 or len(counts) <= 2:
        return grid

    min_count = max(2, int(round(total_beads * min_color_ratio)))
    # 按用量从多到少排序活跃色号
    sorted_colors = [cid for cid, _ in counts.most_common()]
    remap: Dict[int, int] = {cid: cid for cid in sorted_colors}

    kept_colors: List[int] = []
    pair_de = palette.pair_de

    for cid in sorted_colors:
        cnt = counts[cid]
        if not kept_colors:
            kept_colors.append(cid)
            continue

        # 寻找已保留主色中最接近的色号
        nearest_kept = min(kept_colors, key=lambda k: pair_de[cid][k])
        dist = pair_de[cid][nearest_kept]

        should_merge = False
        # 条件 1: 两色极其接近，合并后视觉几乎无差
        if dist <= merge_de:
            should_merge = True
        # 条件 2: 用量极少的零星杂色，只要与已有主色不是截然相反的补色即可合并
        elif cnt < min_count and dist <= merge_de * 1.95:
            should_merge = True
        # 条件 3: 超过该档位建议色数上限时，适度放宽合并阈值
        elif len(kept_colors) >= max_colors_hint and dist <= merge_de * 1.75:
            should_merge = True

        if should_merge:
            remap[cid] = nearest_kept
        else:
            kept_colors.append(cid)

    if all(k == v for k, v in remap.items()):
        return grid

    h = len(grid)
    w = len(grid[0])
    return [[remap[grid[r][c]] if grid[r][c] >= 0 else -1 for c in range(w)] for r in range(h)]


def _clean_isolated_speckles(grid: List[List[int]], palette: BeadPalette, passes: int, max_de: float) -> List[List[int]]:
    """消除简略/高清模式下的单像素孤立噪点（保留高对比度眼睛高光点，仅平滑相近色杂点）."""
    if passes <= 0:
        return grid

    h = len(grid)
    w = len(grid[0]) if h > 0 else 0
    pair_de = palette.pair_de
    cur = [row[:] for row in grid]

    for _ in range(passes):
        nxt = [row[:] for row in cur]
        for r in range(h):
            for c in range(w):
                val = cur[r][c]
                if val < 0:
                    continue
                neighbors = []
                if r > 0 and cur[r - 1][c] >= 0:
                    neighbors.append(cur[r - 1][c])
                if r + 1 < h and cur[r + 1][c] >= 0:
                    neighbors.append(cur[r + 1][c])
                if c > 0 and cur[r][c - 1] >= 0:
                    neighbors.append(cur[r][c - 1])
                if c + 1 < w and cur[r][c + 1] >= 0:
                    neighbors.append(cur[r][c + 1])

                if len(neighbors) < 3 or val in neighbors:
                    continue

                # 统计周围出现最多的颜色
                dom_color, dom_cnt = Counter(neighbors).most_common(1)[0]
                # 若周围至少 3 颗同色，且色差未超过高光保护阈值（避免把黑色眼珠里的白色高光抹掉！）
                if dom_cnt >= 3 and pair_de[val][dom_color] <= max_de:
                    nxt[r][c] = dom_color
        cur = nxt

    return cur


def generate_bead_pattern(
    img_rgba: Image.Image,
    quality: str = "hd",
    palette_id: str = "mard_96",
    remove_bg: bool = False,
    custom_max_side: Optional[int] = None,
    bg_tolerance: float = 18.5,
) -> Dict:
    """对输入 RGBA 图像生成指定画质档位的完整拼豆图纸数据及拼豆时长预估."""
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["hd"])
    palette = get_palette(palette_id)

    work = img_rgba.copy()
    if remove_bg:
        work = remove_corner_background(work, tolerance_de=bg_tolerance)
        work = crop_to_content(work)
    else:
        # 即使未开启主动抠背景，若原图本身是透明 PNG 贴纸，也自动裁掉多余透明外框
        alpha_extrema = work.getchannel("A").getextrema()
        if alpha_extrema and alpha_extrema[0] < 100:
            work = crop_to_content(work)

    src_w, src_h = work.size
    target_max = custom_max_side if custom_max_side is not None else preset["default_max_side"]
    target_max = max(12, min(160, int(target_max)))

    if src_w >= src_h:
        grid_w = target_max
        grid_h = max(1, int(round(src_h * (target_max / float(src_w)))))
    else:
        grid_h = target_max
        grid_w = max(1, int(round(src_w * (target_max / float(src_h)))))

    # 为避免透明边缘缩放时产生黑边/灰边（Premultiplied Alpha 污染），先将透明像素填充邻近均值色，再单独缩放 Alpha 通道
    alpha_chan = work.getchannel("A")
    rgb_bg = Image.new("RGB", work.size, (250, 250, 250))
    rgb_bg.paste(work.convert("RGB"), mask=alpha_chan)

    # 针对大图做轻度保边去噪（高清档消除 JPG 噪点块）
    if quality == "hd" and max(src_w, src_h) > grid_w * 3:
        rgb_bg = rgb_bg.filter(ImageFilter.MedianFilter(size=3))

    # 应用画质档位专属的色彩与锐度增强
    if preset["contrast"] != 1.0:
        rgb_bg = ImageEnhance.Contrast(rgb_bg).enhance(preset["contrast"])
    if preset["saturation"] != 1.0:
        rgb_bg = ImageEnhance.Color(rgb_bg).enhance(preset["saturation"])
    if preset["sharpness"] != 1.0:
        rgb_bg = ImageEnhance.Sharpness(rgb_bg).enhance(preset["sharpness"])

    resample_method = Image.Resampling.BOX if quality == "simple" else Image.Resampling.LANCZOS
    small_rgb = rgb_bg.resize((grid_w, grid_h), resample_method)
    small_alpha = alpha_chan.resize((grid_w, grid_h), Image.Resampling.BILINEAR)

    rgb_px = small_rgb.load()
    alpha_px = small_alpha.load()

    dither_strength = preset["dither_strength"]
    grid: List[List[int]] = [[-1] * grid_w for _ in range(grid_h)]

    if dither_strength <= 0.001:
        # 无抖动直接感知匹配（简略 & 高清模式：色块干净利落）
        for y in range(grid_h):
            row = grid[y]
            for x in range(grid_w):
                if alpha_px[x, y] < 118:
                    row[x] = -1
                else:
                    r, g, b = rgb_px[x, y]
                    row[x] = palette.match_rgb(r, g, b)
    else:
        # 受控 Floyd-Steinberg 误差扩散（还原模式：平滑还原人像肤色与天空渐变，同时限制最大误差防止脏点）
        buf_r = [[float(rgb_px[x, y][0]) for x in range(grid_w)] for y in range(grid_h)]
        buf_g = [[float(rgb_px[x, y][1]) for x in range(grid_w)] for y in range(grid_h)]
        buf_b = [[float(rgb_px[x, y][2]) for x in range(grid_w)] for y in range(grid_h)]

        for y in range(grid_h):
            # 蛇形扫描减少单向斜纹伪影
            x_range = range(grid_w) if (y % 2 == 0) else range(grid_w - 1, -1, -1)
            step_dir = 1 if (y % 2 == 0) else -1
            for x in x_range:
                if alpha_px[x, y] < 118:
                    grid[y][x] = -1
                    continue

                cr = max(0, min(255, int(round(buf_r[y][x]))))
                cg = max(0, min(255, int(round(buf_g[y][x]))))
                cb = max(0, min(255, int(round(buf_b[y][x]))))

                p_idx = palette.match_rgb(cr, cg, cb)
                grid[y][x] = p_idx

                pr, pg, pb = palette.colors[p_idx]["rgb"]
                # 限制单步量化误差并乘上柔和扩散系数，杜绝纯色面产生麻点
                er = max(-38.0, min(38.0, (cr - pr))) * dither_strength
                eg = max(-38.0, min(38.0, (cg - pg))) * dither_strength
                eb = max(-38.0, min(38.0, (cb - pb))) * dither_strength

                nx = x + step_dir
                if 0 <= nx < grid_w and alpha_px[nx, y] >= 118:
                    buf_r[y][nx] += er * (7.0 / 16.0)
                    buf_g[y][nx] += eg * (7.0 / 16.0)
                    buf_b[y][nx] += eb * (7.0 / 16.0)
                if y + 1 < grid_h:
                    bx = x - step_dir
                    if 0 <= bx < grid_w and alpha_px[bx, y + 1] >= 118:
                        buf_r[y + 1][bx] += er * (3.0 / 16.0)
                        buf_g[y + 1][bx] += eg * (3.0 / 16.0)
                        buf_b[y + 1][bx] += eb * (3.0 / 16.0)
                    if alpha_px[x, y + 1] >= 118:
                        buf_r[y + 1][x] += er * (5.0 / 16.0)
                        buf_g[y + 1][x] += eg * (5.0 / 16.0)
                        buf_b[y + 1][x] += eb * (5.0 / 16.0)
                    fx = x + step_dir
                    if 0 <= fx < grid_w and alpha_px[fx, y + 1] >= 118:
                        buf_r[y + 1][fx] += er * (1.0 / 16.0)
                        buf_g[y + 1][fx] += eg * (1.0 / 16.0)
                        buf_b[y + 1][fx] += eb * (1.0 / 16.0)

    # 近色精简与孤立杂点清理
    grid = _consolidate_colors(
        grid=grid,
        palette=palette,
        merge_de=preset["merge_de"],
        min_color_ratio=preset["min_color_ratio"],
        max_colors_hint=preset["max_colors_hint"],
    )
    if preset["denoise_passes"] > 0:
        max_speckle_de = 34.0 if quality == "simple" else 22.0
        grid = _clean_isolated_speckles(
            grid=grid,
            palette=palette,
            passes=preset["denoise_passes"],
            max_de=max_speckle_de,
        )

    # 汇总色号材料清单 (BOM)
    usage = Counter()
    for row in grid:
        for val in row:
            if val >= 0:
                usage[val] += 1

    total_beads = sum(usage.values())
    bom: List[Dict] = []
    for p_idx, count in usage.most_common():
        cinfo = palette.colors[p_idx]
        bom.append(
            {
                "palette_index": p_idx,
                "code": cinfo["code"],
                "name": cinfo["name"],
                "hex": cinfo["hex"],
                "text_color": cinfo["text_color"],
                "count": count,
                "percentage": round((count / max(1, total_beads)) * 100.0, 1),
            }
        )

    # 预估制作时长
    time_estimate = estimate_assembly_time(grid=grid, unique_colors=len(bom))

    # 计算成品物理尺寸（2.6mm mini 融合豆 vs 5.0mm 标准大豆）
    eff_w = time_estimate.get("effective_size", {}).get("width", grid_w)
    eff_h = time_estimate.get("effective_size", {}).get("height", grid_h)

    return {
        "quality": quality,
        "quality_name": preset["name"],
        "quality_badge": preset["badge"],
        "quality_description": preset["description"],
        "palette_id": palette.palette_id,
        "palette_name": palette.name,
        "grid_width": grid_w,
        "grid_height": grid_h,
        "total_beads": total_beads,
        "unique_colors": len(bom),
        "remove_bg": remove_bg,
        "physical_size_cm": {
            "mini_26mm": {
                "width": round(eff_w * 0.26, 1),
                "height": round(eff_h * 0.26, 1),
            },
            "standard_50mm": {
                "width": round(eff_w * 0.50, 1),
                "height": round(eff_h * 0.50, 1),
            },
        },
        "grid": grid,
        "bom": bom,
        "palette_lookup": {
            str(c["index"]): {
                "code": c["code"],
                "name": c["name"],
                "hex": c["hex"],
                "text_color": c["text_color"],
            }
            for c in palette.colors
        },
        "time_estimate": time_estimate,
    }


def generate_all_tiers_summary(
    img_rgba: Image.Image,
    palette_id: str = "mard_96",
    remove_bg: bool = False,
    bg_tolerance: float = 18.5,
) -> Dict[str, Dict]:
    """一次性计算简略、高清、还原三档结果，用于同屏直观对比各档拼豆数与预估时长."""
    results: Dict[str, Dict] = {}
    for q in ("simple", "hd", "faithful"):
        results[q] = generate_bead_pattern(
            img_rgba=img_rgba,
            quality=q,
            palette_id=palette_id,
            remove_bg=remove_bg,
            bg_tolerance=bg_tolerance,
        )
    return results
