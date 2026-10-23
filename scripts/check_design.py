#!/usr/bin/env python3
"""Sanity-check the keyboard design files.

Stdlib only. Confirms the KiCad board still parses as the reviewed
64-key design, the fabrication zip has the expected Gerbers and no
macOS junk, and text files do not contain credential-shaped strings.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PCB_PATH = ROOT / "PCB FILES" / "keyboard.kicad_pcb"
SCH_PATH = ROOT / "PCB FILES" / "keyboard.kicad_sch"
ZIP_PATH = ROOT / "PCB FILES" / "Output.zip"
STEP_PATH = ROOT / "Case Files" / "keeb - Part 579.step"

GERBERS = {
    "Output/keyboard-F_Cu.gbr",
    "Output/keyboard-B_Cu.gbr",
    "Output/keyboard-F_Mask.gbr",
    "Output/keyboard-B_Mask.gbr",
    "Output/keyboard-F_Silkscreen.gbr",
    "Output/keyboard-B_Silkscreen.gbr",
    "Output/keyboard-F_Paste.gbr",
    "Output/keyboard-B_Paste.gbr",
    "Output/keyboard-Edge_Cuts.gbr",
    "Output/keyboard-PTH.drl",
    "Output/keyboard-NPTH.drl",
}

SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password|token)\b\s*[:=]\s*['\"][^'\"]+['\"]"),
)

TEXT_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".txt", ".kicad_pcb", ".kicad_sch", ".example", ".gitignore"}


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


def prop(node: list, key: str):
    for item in node:
        if isinstance(item, list) and len(item) > 2 and item[0] == "property" and item[1] == key:
            return item[2]
    return None


def child(node: list, name: str):
    for item in node:
        if isinstance(item, list) and item and item[0] == name:
            return item
    return None


class Report:
    def __init__(self):
        self.errors: list[str] = []

    def check(self, condition: bool, message: str):
        if not condition:
            self.errors.append(message)

    def fail(self, message: str):
        self.errors.append(message)


def pad_nets(footprint: list) -> dict[str, str]:
    nets: dict[str, str] = {}
    for pad in footprint:
        if not isinstance(pad, list) or not pad or pad[0] != "pad":
            continue
        net = child(pad, "net")
        if net and len(net) > 1:
            nets.setdefault(str(pad[1]), net[1])
    return nets


def check_board(report: Report):
    report.check(PCB_PATH.is_file(), f"missing {PCB_PATH.name}")
    report.check(SCH_PATH.is_file(), f"missing {SCH_PATH.name}")
    if not PCB_PATH.is_file() or not SCH_PATH.is_file():
        return
    pcb = parse_sexpr(PCB_PATH.read_text(encoding="utf-8"))
    sch = parse_sexpr(SCH_PATH.read_text(encoding="utf-8"))
    report.check(pcb and pcb[0] == "kicad_pcb", "PCB root is not kicad_pcb")
    report.check(sch and sch[0] == "kicad_sch", "schematic root is not kicad_sch")

    footprints = [node for node in pcb if isinstance(node, list) and node and node[0] == "footprint"]
    counts = {"SW": 0, "D": 0, "ST": 0, "A": 0}
    pico_nets: dict[str, str] = {}
    diode_rows = 0
    switch_cols = 0
    for footprint in footprints:
        ref = prop(footprint, "Reference") or ""
        prefix = re.match(r"[A-Z]+", ref)
        if prefix:
            counts[prefix.group(0)] = counts.get(prefix.group(0), 0) + 1
        nets = pad_nets(footprint)
        if ref == "A1":
            pico_nets = nets
        if ref.startswith("D") and nets.get("1", "").startswith("ROW") and nets.get("2", "").startswith("Net-(D"):
            diode_rows += 1
        if ref.startswith("SW") and any(net.startswith("COL") for net in nets.values()):
            switch_cols += 1

    report.check(counts.get("SW") == 64, f"expected 64 switches, found {counts.get('SW')}")
    report.check(counts.get("D") == 64, f"expected 64 diodes, found {counts.get('D')}")
    report.check(counts.get("ST") == 5, f"expected 5 stabilizers, found {counts.get('ST')}")
    report.check(counts.get("A") == 1, f"expected 1 Pico, found {counts.get('A')}")
    report.check(diode_rows == 64, f"expected 64 diodes with cathode on a ROW, found {diode_rows}")
    report.check(switch_cols == 64, f"expected 64 switches on a COL net, found {switch_cols}")

    row_pins = {1: "ROW0", 2: "ROW1", 4: "ROW2", 5: "ROW3", 6: "ROW4"}
    for pin, net in row_pins.items():
        report.check(pico_nets.get(str(pin)) == net, f"Pico pin {pin} should be {net}")
    # Pico pins 7, 9-12, 14-17, 19-22, 24-27 are COL0-COL16 in order, skipping GND pins.
    column_pins = [7, 9, 10, 11, 12, 14, 15, 16, 17, 19, 20, 21, 22, 24, 25, 26, 27]
    for index, pin in enumerate(column_pins):
        report.check(pico_nets.get(str(pin)) == f"COL{index}", f"Pico pin {pin} should be COL{index}")

    outline = None
    for node in pcb:
        if isinstance(node, list) and node and node[0] == "gr_rect":
            layer = child(node, "layer")
            if layer and layer[1] == "Edge.Cuts":
                start = child(node, "start")
                end = child(node, "end")
                outline = tuple(float(value) for value in (start[1], start[2], end[1], end[2]))
    report.check(outline == (-9.5, -10.0, 319.0, 90.5), f"unexpected board outline {outline}")

    segments = [node for node in pcb if isinstance(node, list) and node and node[0] == "segment"]
    report.check(len(segments) == 575, f"expected 575 copper segments, found {len(segments)}")
    placed = [
        node
        for node in sch
        if isinstance(node, list) and node and node[0] == "symbol" and child(node, "lib_id")
    ]
    report.check(len(placed) == 134, f"expected 134 placed schematic symbols, found {len(placed)}")


def check_fabrication(report: Report):
    report.check(ZIP_PATH.is_file(), "missing Gerber zip")
    report.check(STEP_PATH.is_file(), "missing case STEP")
    if STEP_PATH.is_file():
        head = STEP_PATH.read_text(encoding="utf-8", errors="replace")[:20]
        report.check(head.startswith("ISO-10303-21"), "case file is not a STEP file")
    if not ZIP_PATH.is_file():
        return
    with zipfile.ZipFile(ZIP_PATH) as archive:
        names = set(archive.namelist())
        report.check("__MACOSX/" not in "".join(names), "Gerber zip still contains __MACOSX resource forks")
        for name in names:
            if name.endswith("/"):
                continue
            report.check(name in GERBERS, f"unexpected fabrication file {name}")
            info = archive.getinfo(name)
            report.check(info.file_size > 0, f"empty fabrication file {name}")
        report.check(GERBERS <= names, f"Gerber zip is missing {sorted(GERBERS - names)}")


def check_secrets(report: Report):
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts or "docs/images" in str(path):
            continue
        if path.name == ".env":
            report.fail(f"secret file present: {path.relative_to(ROOT)}")
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {".gitignore", ".env.example"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                report.fail(f"credential-shaped string in {path.relative_to(ROOT)}")
                break


def main():
    report = Report()
    check_board(report)
    check_fabrication(report)
    check_secrets(report)
    if report.errors:
        for error in report.errors:
            print(f"FAIL {error}")
        return 1
    print("design check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
