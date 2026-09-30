#!/usr/bin/env python3
import argparse
import json
import math
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CANVAS_WIDTH = 4400
BACKGROUND = "#FFFFFF"
INK = "#202020"
ROOT_FILL = "#3F51B5"
BRANCH_FILL = "#F1F1F1"
CHILD_FILL = "#FFFFFF"
FONT_REGULAR = Path("/System/Library/Fonts/STHeiti Light.ttc")
FONT_BOLD = Path("/System/Library/Fonts/STHeiti Medium.ttc")


def load_root_topic(xmind_path: Path) -> dict:
    with zipfile.ZipFile(xmind_path) as archive:
        content = json.loads(archive.read("content.json").decode("utf-8"))
    if not content or "rootTopic" not in content[0]:
        raise ValueError(f"XMind缺少rootTopic：{xmind_path}")
    return content[0]["rootTopic"]


def children_of(topic: dict) -> list[dict]:
    return list(topic.get("children", {}).get("attached", []) or [])


def font(size: int, bold: bool = False):
    path = FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(str(path), size=size)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, text_font, max_width: int) -> list[str]:
    lines = []
    current = ""
    for char in str(text):
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + char
        width = draw.textbbox((0, 0), candidate, font=text_font)[2]
        if current and width > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current or not lines:
        lines.append(current)
    return lines


def text_height(draw, lines, text_font, line_gap=10):
    box = draw.textbbox((0, 0), "国Ag", font=text_font)
    line_height = box[3] - box[1]
    return len(lines) * line_height + max(0, len(lines) - 1) * line_gap


def draw_centered_text(draw, rect, text, text_font, fill, padding=28, line_gap=10):
    x1, y1, x2, y2 = rect
    lines = wrap_text(draw, text, text_font, max(40, x2 - x1 - padding * 2))
    height = text_height(draw, lines, text_font, line_gap)
    y = y1 + (y2 - y1 - height) / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=text_font)
        width = bbox[2] - bbox[0]
        draw.text((x1 + (x2 - x1 - width) / 2, y), line, font=text_font, fill=fill)
        y += bbox[3] - bbox[1] + line_gap


def required_box_height(draw, text, text_font, width, padding=24, minimum=92):
    lines = wrap_text(draw, text, text_font, width - padding * 2)
    return max(minimum, text_height(draw, lines, text_font, 9) + padding * 2)


def cubic_points(start, end, steps=40):
    x1, y1 = start
    x2, y2 = end
    control_dx = (x2 - x1) * 0.55
    c1 = (x1 + control_dx, y1)
    c2 = (x2 - control_dx, y2)
    points = []
    for index in range(steps + 1):
        t = index / steps
        u = 1 - t
        x = u**3 * x1 + 3 * u**2 * t * c1[0] + 3 * u * t**2 * c2[0] + t**3 * x2
        y = u**3 * y1 + 3 * u**2 * t * c1[1] + 3 * u * t**2 * c2[1] + t**3 * y2
        points.append((round(x), round(y)))
    return points


def measure_branch(draw, topic, branch_width, child_width, branch_font, child_font):
    branch_height = required_box_height(draw, topic.get("title", ""), branch_font, branch_width, minimum=118)
    child_heights = [
        required_box_height(draw, child.get("title", ""), child_font, child_width, minimum=90)
        for child in children_of(topic)
    ]
    children_height = sum(child_heights) + max(0, len(child_heights) - 1) * 16
    return {
        "topic": topic,
        "branch_height": branch_height,
        "child_heights": child_heights,
        "height": max(branch_height, children_height),
    }


def render_xmind(xmind_path: Path, output_path: Path):
    root = load_root_topic(xmind_path)
    topics = children_of(root)
    if not topics:
        raise ValueError(f"XMind没有一级分支：{xmind_path}")

    scratch = Image.new("RGB", (CANVAS_WIDTH, 1200), BACKGROUND)
    scratch_draw = ImageDraw.Draw(scratch)
    root_font = font(60, bold=True)
    branch_font = font(42, bold=True)
    child_font = font(31)

    branch_width = 500
    child_width = 930
    measured = [measure_branch(scratch_draw, topic, branch_width, child_width, branch_font, child_font) for topic in topics]
    right_count = len(measured) // 2
    right_items = measured[:right_count]
    left_items = measured[right_count:]
    block_gap = 58

    def side_height(items):
        return sum(item["height"] for item in items) + max(0, len(items) - 1) * block_gap

    canvas_height = max(2200, math.ceil(max(side_height(left_items), side_height(right_items)) + 280))
    image = Image.new("RGB", (CANVAS_WIDTH, canvas_height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    root_width = 1120
    root_height = required_box_height(draw, root.get("title", ""), root_font, root_width, padding=46, minimum=260)
    root_left = (CANVAS_WIDTH - root_width) // 2
    root_rect = (
        root_left,
        (canvas_height - root_height) // 2,
        root_left + root_width,
        (canvas_height + root_height) // 2,
    )

    left_child_x = 70
    left_branch_x = 1120
    right_branch_x = 2780
    right_child_x = 3400

    def layout_side(items, side):
        total = side_height(items)
        cursor_y = (canvas_height - total) / 2
        layouts = []
        for item in items:
            block_top = cursor_y
            block_bottom = block_top + item["height"]
            branch_y = (block_top + block_bottom - item["branch_height"]) / 2
            if side == "left":
                branch_rect = (left_branch_x, branch_y, left_branch_x + branch_width, branch_y + item["branch_height"])
                child_x = left_child_x
            else:
                branch_rect = (right_branch_x, branch_y, right_branch_x + branch_width, branch_y + item["branch_height"])
                child_x = right_child_x
            child_total = sum(item["child_heights"]) + max(0, len(item["child_heights"]) - 1) * 16
            child_y = block_top + (item["height"] - child_total) / 2
            child_rects = []
            for height in item["child_heights"]:
                child_rects.append((child_x, child_y, child_x + child_width, child_y + height))
                child_y += height + 16
            layouts.append((item, branch_rect, child_rects))
            cursor_y = block_bottom + block_gap
        return layouts

    layouts = [("left", *layout) for layout in layout_side(left_items, "left")]
    layouts += [("right", *layout) for layout in layout_side(right_items, "right")]

    root_center_y = (root_rect[1] + root_rect[3]) / 2
    for side, item, branch_rect, child_rects in layouts:
        branch_center_y = (branch_rect[1] + branch_rect[3]) / 2
        if side == "left":
            root_point = (root_rect[0], root_center_y)
            branch_root_point = (branch_rect[2], branch_center_y)
            branch_child_point = (branch_rect[0], branch_center_y)
            child_points = [(rect[2], (rect[1] + rect[3]) / 2) for rect in child_rects]
        else:
            root_point = (root_rect[2], root_center_y)
            branch_root_point = (branch_rect[0], branch_center_y)
            branch_child_point = (branch_rect[2], branch_center_y)
            child_points = [(rect[0], (rect[1] + rect[3]) / 2) for rect in child_rects]
        draw.line(cubic_points(root_point, branch_root_point), fill=INK, width=7)
        for child_point in child_points:
            draw.line(cubic_points(branch_child_point, child_point), fill=INK, width=5)

    draw.rounded_rectangle(root_rect, radius=32, fill=ROOT_FILL, outline=INK, width=7)
    draw_centered_text(draw, root_rect, root.get("title", ""), root_font, "#FFFFFF", padding=50, line_gap=14)

    for _, item, branch_rect, child_rects in layouts:
        draw.rounded_rectangle(branch_rect, radius=22, fill=BRANCH_FILL, outline=INK, width=6)
        draw_centered_text(draw, branch_rect, item["topic"].get("title", ""), branch_font, INK, padding=24)
        for child, rect in zip(children_of(item["topic"]), child_rects):
            draw.rounded_rectangle(rect, radius=14, fill=CHILD_FILL, outline=INK, width=4)
            draw_centered_text(draw, rect, child.get("title", ""), child_font, INK, padding=22, line_gap=9)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG", optimize=True, dpi=(180, 180))
    return image.size


def main():
    parser = argparse.ArgumentParser(description="从XMind content.json确定性渲染高清思维导图")
    parser.add_argument("xmind", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    size = render_xmind(args.xmind, args.output)
    print(json.dumps({"source": str(args.xmind), "output": str(args.output), "size": size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
