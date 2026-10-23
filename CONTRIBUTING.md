# Contributing

Thanks for helping improve Keeb Keyboard. The useful changes are design fixes, clearer docs, and firmware that matches the matrix already on the board.

## Before you open a pull request

1. Install [KiCad 10](https://www.kicad.org/) or newer. The schematic and PCB were saved with KiCad 10.0.4. KiCad 8 and 9 cannot open these files.
2. Install [marbastlib](https://github.com/ebastler/marbastlib) from the ebastler KiCad repository (`https://raw.githubusercontent.com/ebastler/ebastler-KiCad-repository/main/repository.json`). The stabilizer footprints (`PCM_marbastlib-mx:STAB_MX_*`) come from that library. Cherry MX switch footprints and the Pico footprint ship with KiCad.
3. Open `PCB FILES/keyboard.kicad_sch` and `PCB FILES/keyboard.kicad_pcb` directly. This repo has no `.kicad_pro` project file.
4. Run the design check:

```bash
python3 scripts/check_design.py
```

## If you change the board

- Keep the diode direction as it is: cathode (footprint pin 1) on the row, anode toward the switch, column on the other switch pin. Firmware authors depend on that COL2ROW wiring.
- Update `scripts/check_design.py` in the same pull request if you intentionally change a count the check locks (switch count, outline, Pico pin map, Gerber set).
- Re-export Gerbers and drills from KiCad (File → Fabrication Outputs → Gerbers, then Generate Drill Files) and replace `PCB FILES/Output.zip`. Leave macOS `__MACOSX` / `._*` files out of the zip.
- Regenerate the pictures:

```bash
pip install pillow
python3 scripts/render_previews.py
```

The pictures are plots of the file coordinates. If you change the geometry, commit the new PNGs with the board.

## What not to commit

KiCad lock files, `*-backups/`, `_autosave-*`, `.kicad_prl`, `.env`, and `__MACOSX` folders. `.gitignore` already covers these.

There is no application here and no dependency lockfile. Please don't add a package manager or a web app just to host the README.

## Reports

Use the bug and feature issue templates. Security reports go through [GitHub security advisories](https://github.com/ryaneditraj/Keeb-Keyboard/security/advisories/new), as described in [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
