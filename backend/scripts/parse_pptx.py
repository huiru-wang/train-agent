#!/usr/bin/env python3
"""
PPTX 风格数据提取库
职责：解析 PPTX，输出纯结构化数据 (dict)
不包含任何 prompt 文本，prompt 模板与数据完全分离

用法:
    from scripts.parse_pptx import parse_pptx
    data = parse_pptx("/path/to/file.pptx", "/tmp/output")
"""

import json
import os
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn


# ============================================================
# 辅助函数
# ============================================================
def emu_to_inches(emu):
    return round(emu / 914400, 2) if emu else None


def rgb_to_hex(rgb):
    return f"#{str(rgb)}" if rgb else None


# ============================================================
# PPTX 解析
# ============================================================
def extract_theme_info(pptx_path):
    theme = {"colors": {}, "fonts": {}}
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    try:
        with zipfile.ZipFile(pptx_path, "r") as z:
            theme_files = [f for f in z.namelist() if "theme" in f.lower() and f.endswith(".xml")]
            if not theme_files:
                return theme
            root = ET.fromstring(z.read(theme_files[0]))
            clr_scheme = root.find(".//a:clrScheme", ns)
            if clr_scheme is not None:
                for child in clr_scheme:
                    tag = child.tag.split("}")[-1]
                    srgb = child.find("a:srgbClr", ns)
                    sys_clr = child.find("a:sysClr", ns)
                    if srgb is not None:
                        theme["colors"][tag] = f"#{srgb.get('val')}"
                    elif sys_clr is not None:
                        theme["colors"][tag] = f"#{sys_clr.get('lastClr', '')}"
            font_scheme = root.find(".//a:fontScheme", ns)
            if font_scheme is not None:
                for role, key in [("majorFont", "major"), ("minorFont", "minor")]:
                    elem = font_scheme.find(f"a:{role}", ns)
                    if elem is not None:
                        latin = elem.find("a:latin", ns)
                        ea = elem.find("a:ea", ns)
                        theme["fonts"][f"{key}_latin"] = latin.get("typeface") if latin is not None else None
                        theme["fonts"][f"{key}_ea"] = ea.get("typeface") if ea is not None else None
    except Exception as e:
        print(f"  [WARN] 主题提取失败: {e}")
    return theme


def collect_shape_style(shape, text_colors, fonts, font_sizes, fill_colors, shape_types):
    shape_types[str(shape.shape_type)] += 1
    try:
        fill = shape.fill
        if fill.type == 1 and fill.fore_color and fill.fore_color.rgb:
            fill_colors[rgb_to_hex(fill.fore_color.rgb)] += 1
    except Exception:
        pass
    try:
        grad = shape._element.find(".//" + qn("a:gradFill"))
        if grad is not None:
            for gs in grad.findall(".//" + qn("a:gs")):
                srgb = gs.find(qn("a:srgbClr"))
                if srgb is not None:
                    fill_colors[f"#{srgb.get('val')}"] += 1
    except Exception:
        pass
    if shape.has_text_frame:
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                if run.font.name:
                    fonts[run.font.name] += 1
                if run.font.size:
                    font_sizes[run.font.size.pt] += 1
                try:
                    if run.font.color and run.font.color.rgb:
                        text_colors[rgb_to_hex(run.font.color.rgb)] += 1
                except Exception:
                    pass
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for sub in shape.shapes:
            collect_shape_style(sub, text_colors, fonts, font_sizes, fill_colors, shape_types)


def analyze_layout(shapes):
    positions = []
    sw, sh = 9144000, 5143500
    for s in shapes:
        try:
            positions.append({
                "l": round(s.left / sw * 100, 1) if s.left else 0,
                "t": round(s.top / sh * 100, 1) if s.top else 0,
                "w": round(s.width / sw * 100, 1) if s.width else 0,
                "h": round(s.height / sh * 100, 1) if s.height else 0,
            })
        except Exception:
            pass
    if not positions:
        return "empty"
    for p in positions:
        if p["w"] > 80 and p["h"] > 80:
            return "full_bleed"
    if sum(1 for p in positions if p["l"] < 40) >= 2 and sum(1 for p in positions if p["l"] > 50) >= 2:
        return "split_horizontal"
    if sum(1 for p in positions if p["t"] < 30) >= 2 and sum(1 for p in positions if p["t"] > 50) >= 2:
        return "split_vertical"
    if sum(1 for p in positions if 20 < p["l"] < 60) >= len(positions) * 0.6:
        return "centered"
    return "mixed"


def parse_pptx_statistics(prs):
    text_colors, fill_colors, fonts, font_sizes, shape_types = Counter(), Counter(), Counter(), Counter(), Counter()
    slide_summaries = []
    for idx, slide in enumerate(prs.slides):
        shapes = list(slide.shapes)
        for shape in shapes:
            collect_shape_style(shape, text_colors, fonts, font_sizes, fill_colors, shape_types)
        slide_summaries.append({
            "index": idx + 1,
            "shape_count": len(shapes),
            "has_image": any(s.shape_type == MSO_SHAPE_TYPE.PICTURE for s in shapes),
            "has_table": any(hasattr(s, "has_table") and s.has_table for s in shapes),
            "has_chart": any(hasattr(s, "has_chart") and s.has_chart for s in shapes),
            "layout_type": analyze_layout(shapes),
        })
    return {
        "text_colors": [{"color": c, "count": n} for c, n in text_colors.most_common(15)],
        "fill_colors": [{"color": c, "count": n} for c, n in fill_colors.most_common(15)],
        "fonts": [{"name": f, "count": n} for f, n in fonts.most_common(10)],
        "font_sizes": [{"size_pt": s, "count": n} for s, n in font_sizes.most_common(15)],
        "shape_types": [{"type": t, "count": n} for t, n in shape_types.most_common(10)],
        "layout_distribution": dict(Counter(s["layout_type"] for s in slide_summaries)),
        "slides_with_images": sum(1 for s in slide_summaries if s["has_image"]),
        "slides_with_tables": sum(1 for s in slide_summaries if s["has_table"]),
        "slides_with_charts": sum(1 for s in slide_summaries if s["has_chart"]),
        "slide_summaries": slide_summaries,
    }


# ============================================================
# 图片提取与主色分析
# ============================================================
def extract_images(prs, images_dir):
    count = 0
    for slide_idx, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    image = shape.image
                    ext = "png"
                    ct = getattr(image, "content_type", "")
                    if "jpeg" in ct:
                        ext = "jpg"
                    elif "webp" in ct:
                        ext = "webp"
                    with open(os.path.join(images_dir, f"slide{slide_idx+1}_img{count}.{ext}"), "wb") as f:
                        f.write(image.blob)
                    count += 1
                except Exception:
                    pass
    return count


def extract_background_images(pptx_path, bg_images_dir):
    count = 0
    with zipfile.ZipFile(pptx_path, "r") as z:
        for f in z.namelist():
            if "media" in f and f.endswith((".png", ".jpg", ".jpeg")):
                info = z.getinfo(f)
                if info.file_size > 100000:
                    with open(os.path.join(bg_images_dir, os.path.basename(f)), "wb") as out:
                        out.write(z.read(f))
                    count += 1
    return count


def extract_image_colors(image_path, top_n=6):
    try:
        img = Image.open(image_path).convert("RGB")
        img.thumbnail((150, 150))
        pixels = list(img.getdata())
        quantized = [(r // 32 * 32, g // 32 * 32, b // 32 * 32) for r, g, b in pixels]
        return [{"color": f"#{r:02X}{g:02X}{b:02X}", "pct": round(c / len(pixels) * 100, 1)}
                for (r, g, b), c in Counter(quantized).most_common(top_n)]
    except Exception:
        return []


def get_image_dimensions(image_path):
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return (0, 0)


def analyze_images(images_dir, bg_images_dir):
    # 背景图
    bg_list = []
    if os.path.exists(bg_images_dir):
        for f in sorted(os.listdir(bg_images_dir)):
            fpath = os.path.join(bg_images_dir, f)
            fsize = os.path.getsize(fpath)
            dims = get_image_dimensions(fpath)
            colors = extract_image_colors(fpath)
            slide_num = None
            for part in f.replace("-", " ").replace(".", " ").split():
                if part.isdigit():
                    slide_num = int(part)
                    break
            bg_list.append({
                "filename": f, "slide": slide_num,
                "dimensions": f"{dims[0]}x{dims[1]}",
                "size_kb": round(fsize / 1024),
                "dominant_colors": colors,
            })
    # 去重合并相同背景图
    unique_bg = {}
    for bg in bg_list:
        key = bg["dimensions"] + str(bg["size_kb"])
        if key not in unique_bg:
            unique_bg[key] = {**bg, "used_in_slides": []}
        unique_bg[key]["used_in_slides"].append(bg["slide"])
    bg_result = []
    for v in unique_bg.values():
        v.pop("slide", None)
        bg_result.append(v)

    # 小图标
    icon_count = 0
    icon_sizes = []
    if os.path.exists(images_dir):
        for f in os.listdir(images_dir):
            fsize = os.path.getsize(os.path.join(images_dir, f))
            if fsize < 5000:
                icon_count += 1
                icon_sizes.append(fsize)

    return {
        "background_images": bg_result,
        "icon_count": icon_count,
        "icon_avg_size_bytes": round(sum(icon_sizes) / len(icon_sizes)) if icon_sizes else 0,
    }


# ============================================================
# 主函数
# ============================================================
def parse_pptx(pptx_path: str, output_dir: str) -> dict:
    """
    解析 PPTX 文件，返回结构化风格数据。

    Args:
        pptx_path: PPTX 文件的绝对路径
        output_dir: 临时图片输出目录（images/ 和 background_images/ 子目录）

    Returns:
        包含 file_info, theme, style_summary, image_analysis 的结构化 dict
    """
    images_dir = os.path.join(output_dir, "images")
    bg_images_dir = os.path.join(output_dir, "background_images")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(bg_images_dir, exist_ok=True)

    prs = Presentation(pptx_path)

    w_in = emu_to_inches(prs.slide_width)
    h_in = emu_to_inches(prs.slide_height)
    stats = parse_pptx_statistics(prs)
    theme = extract_theme_info(pptx_path)
    extract_images(prs, images_dir)
    extract_background_images(pptx_path, bg_images_dir)
    image_analysis = analyze_images(images_dir, bg_images_dir)

    return {
        "file_info": {
            "slide_count": len(prs.slides),
            "width_inches": w_in,
            "height_inches": h_in,
            "aspect_ratio": round(w_in / h_in, 2) if h_in else None,
        },
        "theme": theme,
        "style_summary": stats,
        "image_analysis": image_analysis,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python parse_pptx.py <pptx_path> [output_dir]")
        sys.exit(1)
    pptx_file = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(pptx_file)
    result = parse_pptx(pptx_file, out_dir)
    json_path = os.path.join(out_dir, "style_data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"完成: {json_path}")
