#!/usr/bin/env python3
"""Plot preview images from the KiCad board and the Onshape STEP case.

These are geometry plots of the design files, not photographs and not
KiCad screenshots. KiCad 10 is not required to run this script.

    pip install pillow
    python3 scripts/render_previews.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.stderr.write("Pillow is required: pip install pillow\n")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
PCB_PATH = ROOT / "PCB FILES" / "keyboard.kicad_pcb"
STEP_PATH = ROOT / "Case Files" / "keeb - Part 579.step"
OUT_DIR = ROOT / "docs" / "images"

FONT_REGULAR = (
    "/usr/share/fonts/truetype/macos/Inter-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
FONT_MEDIUM = (
    "/usr/share/fonts/truetype/macos/Inter-Medium.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
FONT_BOLD = (
    "/usr/share/fonts/truetype/macos/Inter-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
FONT_MONO = (
    "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Medium.ttf",
    "/usr/share/fonts/truetype/macos/JetBrainsMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)


def parse_sexpr(text: str) -> list:
    tokens = re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', text)

    def rec(i: int):
        node: list = []
        while i < len(tokens):
            token = tokens[i]
            if token == "(":
                child, i = rec(i + 1)
                node.append(child)
            elif token == ")":
                return node, i + 1
            else:
                if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
                    token = token[1:-1]
                node.append(token)
                i += 1
        return node, i

    tree, _ = rec(1)
    return tree


def child(node: list, name: str):
    for item in node:
        if isinstance(item, list) and item and item[0] == name:
            return item
    return None


def children(node: list, name: str):
    return [item for item in node if isinstance(item, list) and item and item[0] == name]


def prop(node: list, key: str):
    for item in node:
        if isinstance(item, list) and len(item) > 2 and item[0] == "property" and item[1] == key:
            return item[2]
    return None


def font(paths: tuple[str, ...], size: int) -> ImageFont.ImageFont:
    for path in paths:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=face)
    return box[2] - box[0], box[3] - box[1]


def rounded(draw, xy, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def load_board():
    tree = parse_sexpr(PCB_PATH.read_text(encoding="utf-8"))
    outline = None
    keys = []
    segments = []
    pads = []
    pico = None
    for node in tree:
        if not isinstance(node, list):
            continue
        if node[0] == "gr_rect":
            layer = child(node, "layer")
            if layer and layer[1] == "Edge.Cuts":
                start = child(node, "start")
                end = child(node, "end")
                outline = (float(start[1]), float(start[2]), float(end[1]), float(end[2]))
        elif node[0] == "segment":
            start = child(node, "start")
            end = child(node, "end")
            layer = child(node, "layer")
            segments.append(
                (float(start[1]), float(start[2]), float(end[1]), float(end[2]), layer[1])
            )
        elif node[0] == "footprint":
            at = child(node, "at")
            ref = prop(node, "Reference") or ""
            fx, fy = float(at[1]), float(at[2])
            if "Cherry_MX" in node[1] and ref.startswith("SW"):
                match = re.search(r"([\d.]+)u$", node[1])
                unit = float(match.group(1)) if match else 1.0
                keys.append({"ref": ref, "x": fx, "y": fy, "unit": unit})
            if "RaspberryPi_Pico" in node[1]:
                pico = {"x": fx, "y": fy}
            for pad in children(node, "pad"):
                pat = child(pad, "at")
                size = child(pad, "size")
                drill = child(pad, "drill")
                drill_d = float(drill[1]) if drill and len(drill) > 1 and drill[1] != "oval" else 0.0
                pads.append(
                    {
                        "x": fx + float(pat[1]),
                        "y": fy + float(pat[2]),
                        "w": float(size[1]),
                        "h": float(size[2]),
                        "drill": drill_d,
                        "kind": pad[2],
                    }
                )
    if outline is None or pico is None or len(keys) != 64:
        raise SystemExit("Board geometry did not match the expected keyboard")
    return {"outline": outline, "keys": keys, "segments": segments, "pads": pads, "pico": pico}


def arrow_refs(keys: list[dict]) -> dict[str, str]:
    """Name the right-hand 1u cluster from its geometry.

    Four 1u keys sit to the right of the alpha block. The upper one is
    the up arrow. The lower three, left to right, are left, down, right.
    """
    cluster = [key for key in keys if key["unit"] == 1.0 and key["x"] > 260]
    if len(cluster) != 4:
        return {}
    upper = min(cluster, key=lambda key: key["y"])
    lower = sorted((key for key in cluster if key is not upper), key=lambda key: key["x"])
    return {upper["ref"]: "↑", lower[0]["ref"]: "←", lower[1]["ref"]: "↓", lower[2]["ref"]: "→"}


def make_canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), "#0c0f12")
    return image, ImageDraw.Draw(image)


def draw_header(draw, title: str, subtitle: str, width: int):
    title_font = font(FONT_BOLD, 34)
    sub_font = font(FONT_REGULAR, 18)
    draw.text((48, 32), title, font=title_font, fill="#f4f7f8")
    draw.text((48, 74), subtitle, font=sub_font, fill="#9aa6b2")
    draw.line((48, 112, width - 48, 112), fill="#22282e", width=1)


def draw_footer(draw, text: str, width: int, height: int):
    face = font(FONT_REGULAR, 15)
    tw, _ = text_size(draw, text, face)
    draw.text(((width - tw) / 2, height - 36), text, font=face, fill="#7f8b96")


def render_layout(board: dict, path: Path):
    x0, y0, x1, y1 = board["outline"]
    left, top, right, bottom = min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
    # USB plug extends past the number-row edge (smaller KiCad Y).
    view = (left - 6, top - 14, right + 8, bottom + 8)
    width, height = 1920, 980
    image, draw = make_canvas(width, height)
    draw_header(
        draw,
        "Keeb Keyboard",
        "64-key layout plotted from the KiCad PCB  ·  number row at the top",
        width,
    )
    plot = (48, 140, width - 48, height - 78)
    span_x = view[2] - view[0]
    span_y = view[3] - view[1]
    scale = min((plot[2] - plot[0]) / span_x, (plot[3] - plot[1]) / span_y)
    used_w = span_x * scale
    used_h = span_y * scale
    origin_x = plot[0] + ((plot[2] - plot[0]) - used_w) / 2
    origin_y = plot[1] + ((plot[3] - plot[1]) - used_h) / 2

    def px(x, y):
        return origin_x + (x - view[0]) * scale, origin_y + (y - view[1]) * scale

    def rect_from_center(cx, cy, w, h):
        ax, ay = px(cx - w / 2, cy - h / 2)
        bx, by = px(cx + w / 2, cy + h / 2)
        return [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)]

    board_box = [px(left, top)[0], px(left, top)[1], px(right, bottom)[0], px(right, bottom)[1]]
    board_box = [min(board_box[0], board_box[2]), min(board_box[1], board_box[3]), max(board_box[0], board_box[2]), max(board_box[1], board_box[3])]
    shadow = [board_box[0] + 5, board_box[1] + 8, board_box[2] + 5, board_box[3] + 8]
    draw.rectangle(shadow, fill="#070809")
    draw.rectangle(board_box, fill="#14643f", outline="#d5e0d8", width=2)

    arrows = arrow_refs(board["keys"])
    label_font = font(FONT_MEDIUM, 18)
    arrow_font = font(FONT_BOLD, 28)
    for key in sorted(board["keys"], key=lambda item: (item["y"], item["x"])):
        cap_w = key["unit"] * 19.05 - 1.05
        cap_h = 18.05
        box = rect_from_center(key["x"], key["y"], cap_w, cap_h)
        glyph = arrows.get(key["ref"])
        if glyph:
            fill, top_fill, ink = "#d4652f", "#e48755", "#fff8f3"
        elif key["unit"] > 1.01:
            fill, top_fill, ink = "#2a3140", "#3a4354", "#d5dbe3"
        else:
            fill, top_fill, ink = "#1c222c", "#2a3140", "#c5ccd6"
        radius = max(5, int(1.6 * scale))
        draw.rounded_rectangle(box, radius=radius, fill=fill)
        inset = max(2, int(0.9 * scale))
        face = [box[0] + inset, box[1] + inset, box[2] - inset, box[3] - int(1.7 * scale)]
        if face[2] > face[0] and face[3] > face[1]:
            draw.rounded_rectangle(face, radius=max(3, radius - 2), fill=top_fill)
        if glyph:
            face_to_use = arrow_font
            text = glyph
        elif key["unit"] > 1.01:
            face_to_use = label_font
            text = f"{key['unit']:g}u"
        else:
            continue
        tw, th = text_size(draw, text, face_to_use)
        draw.text(((box[0] + box[2] - tw) / 2, (box[1] + box[3] - th) / 2 - 2), text, font=face_to_use, fill=ink)

    pico = board["pico"]
    body = rect_from_center(pico["x"], pico["y"], 21.0, 51.0)
    draw.rounded_rectangle(body, radius=6, fill="#141816", outline="#9aab9f", width=2)
    # USB-C leaves the negative-Y end of the module, past the board edge.
    usb_cx, usb_cy = pico["x"], pico["y"] - 25.5 - 3.2
    usb = rect_from_center(usb_cx, usb_cy, 9.0, 7.4)
    draw.rounded_rectangle(usb, radius=3, fill="#d7dbe0", outline="#8e979e", width=1)
    tongue = rect_from_center(usb_cx, usb_cy, 6.2, 2.2)
    draw.rounded_rectangle(tongue, radius=1, fill="#8b939a")
    pin1 = rect_from_center(pico["x"] - 8.89, pico["y"] - 24.13, 1.5, 1.5)
    draw.ellipse(pin1, fill="#f4f7f2")
    pico_font = font(FONT_BOLD, 18)
    tw, th = text_size(draw, "Pico", pico_font)
    draw.text(((body[0] + body[2] - tw) / 2, (body[1] + body[3] - th) / 2 - 2), "Pico", font=pico_font, fill="#e7eee8")

    legend_font = font(FONT_REGULAR, 15)
    legend_y = height - 64
    samples = [
        ((28, 34, 44), "1u key"),
        ((42, 49, 64), "stabilized key"),
        ((212, 101, 47), "arrow cluster"),
        ((20, 100, 63), "PCB"),
    ]
    lx = 48
    for color, label in samples:
        draw.rounded_rectangle((lx, legend_y, lx + 18, legend_y + 14), radius=3, fill=color)
        draw.text((lx + 26, legend_y - 2), label, font=legend_font, fill="#c5ced6")
        lx += 26 + text_size(draw, label, legend_font)[0] + 28
    draw_footer(
        draw,
        "Geometry plot of PCB FILES/keyboard.kicad_pcb  ·  not a photograph",
        width,
        height,
    )
    image.save(path, "PNG", optimize=True)


def render_copper(board: dict, path: Path):
    x0, y0, x1, y1 = board["outline"]
    left, top, right, bottom = min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
    view = (left - 4, top - 8, right + 4, bottom + 4)
    width, height = 1920, 860
    image, draw = make_canvas(width, height)
    draw_header(
        draw,
        "PCB copper",
        "Front traces in gold, back traces in dark green  ·  0.2 mm traces drawn heavier so they stay visible",
        width,
    )
    plot = (40, 136, width - 40, height - 56)
    scale = min((plot[2] - plot[0]) / (view[2] - view[0]), (plot[3] - plot[1]) / (view[3] - view[1]))
    used_w = (view[2] - view[0]) * scale
    used_h = (view[3] - view[1]) * scale
    origin_x = plot[0] + ((plot[2] - plot[0]) - used_w) / 2
    origin_y = plot[1] + ((plot[3] - plot[1]) - used_h) / 2

    def px(x, y):
        return origin_x + (x - view[0]) * scale, origin_y + (y - view[1]) * scale

    board_box = [px(left, top), px(right, bottom)]
    flat = [min(board_box[0][0], board_box[1][0]), min(board_box[0][1], board_box[1][1]), max(board_box[0][0], board_box[1][0]), max(board_box[0][1], board_box[1][1])]
    draw.rectangle(flat, fill="#0f5a38", outline="#e3ece6", width=2)

    for x1s, y1s, x2s, y2s, layer in board["segments"]:
        color = "#0a3a28" if layer == "B.Cu" else "#e6c36a"
        width_px = 3 if layer == "F.Cu" else 2
        draw.line((px(x1s, y1s), px(x2s, y2s)), fill=color, width=width_px)

    for pad in board["pads"]:
        box_w = max(pad["w"], 0.6)
        box_h = max(pad["h"], 0.6)
        ax, ay = px(pad["x"] - box_w / 2, pad["y"] - box_h / 2)
        bx, by = px(pad["x"] + box_w / 2, pad["y"] + box_h / 2)
        box = [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)]
        if pad["kind"] == "smd":
            draw.rectangle(box, fill="#f0d48a")
        else:
            draw.ellipse(box, fill="#f0d48a")
        if pad["drill"] > 0:
            ax, ay = px(pad["x"] - pad["drill"] / 2, pad["y"] - pad["drill"] / 2)
            bx, by = px(pad["x"] + pad["drill"] / 2, pad["y"] + pad["drill"] / 2)
            hole = [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)]
            draw.ellipse(hole, fill="#08110d")

    draw_footer(
        draw,
        "Every trace and pad comes from keyboard.kicad_pcb  ·  trace width on screen is exaggerated  ·  not a photograph",
        width,
        height,
    )
    image.save(path, "PNG", optimize=True)


def load_case():
    text = STEP_PATH.read_text(encoding="utf-8", errors="replace")
    raw = re.findall(
        r"CARTESIAN_POINT\([^)]*\(([-\d.E]+),([-\d.E]+),([-\d.E]+)\)\)",
        text,
    )
    points = [(float(x) * 1000, float(y) * 1000, float(z) * 1000) for x, y, z in raw]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    minz, maxz = min(zs), max(zs)

    def inset(point):
        return min(point[0] - minx, maxx - point[0], point[1] - miny, maxy - point[1])

    inner = [point for point in points if 0.4 < inset(point) < 8]
    ixs = [p[0] for p in inner]
    iys = [p[1] for p in inner]
    return {
        "outer": (minx, miny, maxx, maxy),
        "inner": (min(ixs), min(iys), max(ixs), max(iys)),
        "z": (minz, maxz),
        "floor_z": 0.0,
    }


def render_case(case: dict, path: Path):
    width, height = 1920, 980
    image, draw = make_canvas(width, height)
    ox0, oy0, ox1, oy1 = case["outer"]
    ix0, iy0, ix1, iy1 = case["inner"]
    z0, z1 = case["z"]
    outer_w = ox1 - ox0
    outer_h = oy1 - oy0
    inner_w = ix1 - ix0
    inner_h = iy1 - iy0
    wall_x = ix0 - ox0
    wall_y = iy0 - oy0
    draw_header(
        draw,
        "Case tray",
        "Open Onshape tray measured from Case Files/keeb - Part 579.step",
        width,
    )

    # Top view
    plot = (70, 170, 1180, 860)
    span_x, span_y = outer_w, outer_h
    scale = min((plot[2] - plot[0]) / (span_x * 1.08), (plot[3] - plot[1]) / (span_y * 1.18))
    used_w, used_h = span_x * scale, span_y * scale
    gx = plot[0] + ((plot[2] - plot[0]) - used_w) / 2
    gy = plot[1] + ((plot[3] - plot[1]) - used_h) / 2 + 10

    def px(x, y):
        return gx + (x - ox0) * scale, gy + (oy1 - y) * scale

    outer = [px(ox0, oy0)[0], px(ox0, oy1)[1], px(ox1, oy1)[0], px(ox1, oy0)[1]]
    outer = [min(outer[0], outer[2]), min(outer[1], outer[3]), max(outer[0], outer[2]), max(outer[1], outer[3])]
    inner = [px(ix0, iy0)[0], px(ix0, iy1)[1], px(ix1, iy1)[0], px(ix1, iy0)[1]]
    inner = [min(inner[0], inner[2]), min(inner[1], inner[3]), max(inner[0], inner[2]), max(inner[1], inner[3])]
    draw.rounded_rectangle(
        [outer[0] + 6, outer[1] + 8, outer[2] + 6, outer[3] + 8], radius=18, fill="#070809"
    )
    draw.rounded_rectangle(outer, radius=16, fill="#8b9298")
    draw.rounded_rectangle(inner, radius=10, fill="#1a1e22")
    # Floor inset so the cavity reads as a dish, not a hole through the page.
    floor_pad = 10
    draw.rounded_rectangle(
        [inner[0] + floor_pad, inner[1] + floor_pad, inner[2] - floor_pad, inner[3] - floor_pad],
        radius=8,
        fill="#2a3036",
    )
    cap = font(FONT_MEDIUM, 16)
    draw.text((outer[0], outer[1] - 28), "Top view, true scale", font=cap, fill="#c5ced6")

    dim = font(FONT_REGULAR, 15)
    label = f"{outer_w:.1f} mm"
    tw, _ = text_size(draw, label, dim)
    draw.text(((outer[0] + outer[2] - tw) / 2, outer[3] + 12), label, font=dim, fill="#d5dbe3")
    draw.text((outer[2] + 12, (outer[1] + outer[3]) / 2 - 8), f"{outer_h:.1f} mm", font=dim, fill="#d5dbe3")

    # Cross-section, vertical scale increased so the 11 mm wall is readable.
    panel = (1240, 190, 1860, 860)
    draw.rounded_rectangle(panel, radius=16, fill="#15191d", outline="#2a3138", width=1)
    section_title = font(FONT_BOLD, 20)
    body = font(FONT_REGULAR, 16)
    mono = font(FONT_MONO, 15)
    draw.text((panel[0] + 28, panel[1] + 22), "Cross-section", font=section_title, fill="#f4f7f8")
    draw.text((panel[0] + 28, panel[1] + 52), "Heights measured from the STEP vertices.", font=body, fill="#9aa6b2")

    total_h = z1 - z0
    floor_h = case["floor_z"] - z0
    wall_h = z1 - case["floor_z"]
    base_x = panel[0] + 70
    base_y = panel[1] + 620
    vscale = 28  # px per mm, labeled below
    hscale = 18
    wall_px = wall_x * hscale
    floor_px = floor_h * vscale
    wall_rise = wall_h * vscale
    cavity_px = 220
    profile = [
        (base_x, base_y),
        (base_x, base_y - floor_px - wall_rise),
        (base_x + wall_px, base_y - floor_px - wall_rise),
        (base_x + wall_px, base_y - floor_px),
        (base_x + wall_px + cavity_px, base_y - floor_px),
        (base_x + wall_px + cavity_px, base_y - floor_px - wall_rise),
        (base_x + wall_px * 2 + cavity_px, base_y - floor_px - wall_rise),
        (base_x + wall_px * 2 + cavity_px, base_y),
    ]
    draw.polygon(profile, fill="#8b9298", outline="#d7dde2")
    draw.line(
        (
            (base_x, base_y - floor_px),
            (base_x + wall_px * 2 + cavity_px, base_y - floor_px),
        ),
        fill="#2c3338",
        width=2,
    )
    note = font(FONT_REGULAR, 14)
    draw.text((base_x, base_y + 16), "Diagram, not to scale. The numbers are measured.", font=note, fill="#9aa6b2")

    right_wall = (ox1 - ix1)
    top_wall = (oy1 - iy1)
    facts = [
        f"Outer      {outer_w:.1f} × {outer_h:.1f} mm",
        f"Cavity     {inner_w:.1f} × {inner_h:.1f} mm",
        f"Walls      {min(wall_x, right_wall):.2f}–{max(wall_x, right_wall):.2f} mm (x)",
        f"           {min(wall_y, top_wall):.2f}–{max(wall_y, top_wall):.2f} mm (y)",
        f"Floor      {floor_h:.1f} mm",
        f"Wall rise  {wall_h:.1f} mm",
        f"Overall    {total_h:.1f} mm tall",
    ]
    y = panel[1] + 100
    for line in facts:
        draw.text((panel[0] + 28, y), line, font=mono, fill="#e7edf2")
        y += 28

    draw_footer(
        draw,
        "Vertex plot of the STEP solid  ·  not a render from Onshape and not a photograph",
        width,
        height,
    )
    image.save(path, "PNG", optimize=True)
    return {
        "outer_mm": (round(outer_w, 2), round(outer_h, 2), round(total_h, 2)),
        "cavity_mm": (round(inner_w, 2), round(inner_h, 2)),
        "wall_mm": (round(wall_x, 2), round(wall_y, 2)),
        "floor_mm": round(floor_h, 2),
        "rise_mm": round(wall_h, 2),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    board = load_board()
    render_layout(board, OUT_DIR / "layout.png")
    render_copper(board, OUT_DIR / "pcb-copper.png")
    case = render_case(load_case(), OUT_DIR / "case-tray.png")
    print("wrote", OUT_DIR)
    print("case", case)


if __name__ == "__main__":
    main()
