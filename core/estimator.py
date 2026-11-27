"""科学拼豆时长预估模型 (Assembly Time & Complexity Estimator).

综合考虑真实拼豆制作过程中的四大耗时维度：
1. 准备与分豆找色耗时：取决于使用的色号种类数 (unique_colors)
2. 连片色块摆豆耗时：横向连续同色豆可用镊子连夹，速度最快
3. 团簇与换色摆豆耗时：小色块区域的常规摆豆与视线切换损耗
4. 散点豆（孤立单颗豆）对位惩罚：需反复数行列坐标核对图纸，单颗耗时显著增加
5. 拼板美纹纸固定、扎孔与双面熨烫定型耗时：取决于覆盖的 29×29 标准大模板数量
"""

from __future__ import annotations

import math
from typing import Dict, List


def format_duration_cn(total_seconds: float) -> str:
    """格式化秒数为自然中文时长描述（如 '48 分钟' 或 '2 小时 35 分钟'）."""
    minutes = max(1, int(round(total_seconds / 60.0)))
    if minutes < 60:
        return f"{minutes} 分钟"
    hours = minutes // 60
    rem_min = minutes % 60
    if rem_min == 0:
        return f"{hours} 小时"
    return f"{hours} 小时 {rem_min} 分钟"


def estimate_assembly_time(grid: List[List[int]], unique_colors: int) -> Dict:
    """根据二维拼豆矩阵分析空间复杂度并预估各阶段制作时长."""
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0

    total_beads = 0
    fast_run_beads = 0      # 横向连续 >= 3 颗同色（可镊子连取快速盲摆）
    cluster_beads = 0       # 有相邻同色豆但非长连排
    isolated_beads = 0      # 上下左右全无同色邻居的「散点豆」（最费眼力数格子）
    row_transitions = 0     # 行内换色次数

    for r in range(height):
        row = grid[r]
        c = 0
        prev_color = -2
        while c < width:
            val = row[c]
            if val < 0:
                prev_color = -1
                c += 1
                continue

            # 统计同色横向连排长度
            run_end = c + 1
            while run_end < width and row[run_end] == val:
                run_end += 1
            run_len = run_end - c

            if prev_color >= 0 and prev_color != val:
                row_transitions += 1
            prev_color = val

            total_beads += run_len
            if run_len >= 3:
                fast_run_beads += run_len
            else:
                # 逐颗检查是否为孤立散点豆（上下左右四个正交方向均不同色）
                for k in range(c, run_end):
                    has_same_neighbor = False
                    if k > 0 and row[k - 1] == val:
                        has_same_neighbor = True
                    elif k + 1 < width and row[k + 1] == val:
                        has_same_neighbor = True
                    elif r > 0 and grid[r - 1][k] == val:
                        has_same_neighbor = True
                    elif r + 1 < height and grid[r + 1][k] == val:
                        has_same_neighbor = True

                    if has_same_neighbor:
                        cluster_beads += 1
                    else:
                        isolated_beads += 1

            c = run_end

    if total_beads == 0:
        return {
            "total_beads": 0,
            "boards_29": {"cols": 0, "rows": 0, "total": 0},
            "boards_50": {"cols": 0, "rows": 0, "total": 0},
            "spatial_stats": {
                "fast_run_beads": 0,
                "cluster_beads": 0,
                "isolated_beads": 0,
                "scattered_ratio": 0.0,
                "contiguity_ratio": 100.0,
            },
            "difficulty": {"score": 1, "label": "空白画布"},
            "profiles": {
                k: {
                    "label": lbl,
                    "total_seconds": 0,
                    "total_minutes": 0,
                    "formatted": "0 分钟",
                    "speed_beads_per_min": 0,
                    "breakdown_minutes": {"prep": 0, "placing": 0, "detail": 0, "ironing": 0},
                }
                for k, lbl in [("beginner", "新手入门"), ("standard", "日常玩家"), ("pro", "拼豆老手")]
            },
            "recommended_Formatted": "0 分钟",
            "session_advice": "请先上传图片生成拼豆图纸",
        }

    # 计算实际非空区域包围盒以准确评估所需拼板数
    min_r, max_r = height, -1
    min_c, max_c = width, -1
    for r in range(height):
        for c in range(width):
            if grid[r][c] >= 0:
                if r < min_r:
                    min_r = r
                if r > max_r:
                    max_r = r
                if c < min_c:
                    min_c = c
                if c > max_c:
                    max_c = c

    eff_w = max(1, max_c - min_c + 1)
    eff_h = max(1, max_r - min_r + 1)

    b29_cols = math.ceil(eff_w / 29)
    b29_rows = math.ceil(eff_h / 29)
    b29_total = b29_cols * b29_rows

    b50_cols = math.ceil(eff_w / 50)
    b50_rows = math.ceil(eff_h / 50)
    b50_total = b50_cols * b50_rows

    # --- 日常玩家 (standard, 基准系数 1.0) 各分项秒数 ---
    # 1. 找豆与分装色盒时间：基础准备 50s + 每种色号分装核对 32s
    base_prep_sec = 50.0 + unique_colors * 32.0

    # 2. 主体摆豆时间：连排豆约 2.1s/颗，普通团簇豆约 2.95s/颗，散点基础摆豆 2.95s/颗 + 换色视线切换 0.45s
    base_placing_sec = (
        fast_run_beads * 2.10
        + (cluster_beads + isolated_beads) * 2.95
        + row_transitions * 0.45
    )

    # 3. 散点细节数格定位额外耗时：孤立豆每颗需额外核对行列坐标约 2.85s
    base_detail_sec = isolated_beads * 2.85

    # 4. 美纹纸贴合、扎孔排气与双面熨烫定型时间
    base_ironing_sec = 160.0 + b29_total * 78.0

    scattered_ratio = round((isolated_beads / total_beads) * 100.0, 1)
    contiguity_ratio = round(((fast_run_beads + cluster_beads) / total_beads) * 100.0, 1)

    # 综合难度星级 (1~5)
    complexity_val = (
        (total_beads / 1800.0) * 1.6
        + (unique_colors / 22.0) * 1.1
        + (scattered_ratio / 18.0) * 1.1
    )
    if complexity_val < 1.3:
        diff_score, diff_label = 1, "轻松入门"
    elif complexity_val < 2.4:
        diff_score, diff_label = 2, "休闲治愈"
    elif complexity_val < 3.8:
        diff_score, diff_label = 3, "适中耐玩"
    elif complexity_val < 5.6:
        diff_score, diff_label = 4, "进阶精细"
    else:
        diff_score, diff_label = 5, "大师挑战"

    skill_specs = [
        ("beginner", "新手入门", 1.42, 1.25),   # (key, label, 摆豆系数, 准备/熨烫系数)
        ("standard", "日常玩家", 1.00, 1.00),
        ("pro", "拼豆老手", 0.68, 0.78),
    ]

    profiles = {}
    for key, label, place_mult, aux_mult in skill_specs:
        prep_s = base_prep_sec * aux_mult
        place_s = base_placing_sec * place_mult
        detail_s = base_detail_sec * place_mult
        iron_s = base_ironing_sec * aux_mult
        tot_s = prep_s + place_s + detail_s + iron_s

        # 等效净摆豆速度（颗/分钟）
        active_craft_min = max(0.5, (place_s + detail_s) / 60.0)
        beads_per_min = int(round(total_beads / active_craft_min))

        profiles[key] = {
            "label": label,
            "total_seconds": int(round(tot_s)),
            "total_minutes": max(1, int(round(tot_s / 60.0))),
            "formatted": format_duration_cn(tot_s),
            "speed_beads_per_min": beads_per_min,
            "breakdown_minutes": {
                "prep": max(1, int(round(prep_s / 60.0))),
                "placing": max(1, int(round(place_s / 60.0))),
                "detail": int(round(detail_s / 60.0)),
                "ironing": max(2, int(round(iron_s / 60.0))),
            },
        }

    std_minutes = profiles["standard"]["total_minutes"]
    if std_minutes <= 60:
        advice = "约一杯下午茶的时光即可一气呵成，非常适合做成钥匙扣或包包挂件！"
    elif std_minutes <= 180:
        advice = f"适合周末半天沉浸式手作，建议使用 {b29_cols}×{b29_rows} 块标准 29 格板拼接，中途记得活动肩颈。"
    elif std_minutes <= 420:
        sessions = max(2, round(std_minutes / 120))
        advice = f"细节丰富，建议分 {sessions} 次完成；可开启右侧「单色高亮跟拼」按色号逐批平铺效率更高。"
    else:
        sessions = max(3, round(std_minutes / 150))
        advice = f"殿堂级大幅作品！建议按拼板分区、分 {sessions} 次制作，每拼满一板先贴美纹纸防碰散。"

    return {
        "total_beads": total_beads,
        "effective_size": {"width": eff_w, "height": eff_h},
        "boards_29": {"cols": b29_cols, "rows": b29_rows, "total": b29_total},
        "boards_50": {"cols": b50_cols, "rows": b50_rows, "total": b50_total},
        "spatial_stats": {
            "fast_run_beads": fast_run_beads,
            "cluster_beads": cluster_beads,
            "isolated_beads": isolated_beads,
            "scattered_ratio": scattered_ratio,
            "contiguity_ratio": contiguity_ratio,
        },
        "difficulty": {
            "score": diff_score,
            "label": diff_label,
        },
        "profiles": profiles,
        "recommended_formatted": profiles["standard"]["formatted"],
        "session_advice": advice,
    }
