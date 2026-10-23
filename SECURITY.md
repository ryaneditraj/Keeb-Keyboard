# Security

Keeb Keyboard is an open hardware design: a KiCad schematic, a PCB, Gerber manufacturing files, and a STEP case. There is no firmware, web app, or server in this repository.

## Reporting a vulnerability

Please use [GitHub private vulnerability reporting](https://github.com/ryaneditraj/Keeb-Keyboard/security/advisories/new) for anything sensitive (a leaked credential, a malicious file, or an instruction that could hurt someone building the board).

Use a public issue for ordinary design questions, footprint problems, and documentation fixes.

## What was reviewed

The full git history (two commits) and the working tree were scanned for AWS access keys, GitHub tokens, Slack tokens, OpenAI-style keys, private keys, and assignment-style secrets. **Nothing was found. There is no credential to rotate.**

Also reviewed:

| Area | Result |
| --- | --- |
| Hardcoded secrets | None in the schematic, PCB, Gerbers, STEP file, or history. The STEP author and organization fields are empty. No email addresses. |
| Application dependencies | None. There is no package manifest, so there is no dependency advisory to bump. |
| Injection, XSS, unsafe web config | No application, template, or web server. |
| `.env` | Nothing reads environment variables. `.env.example` documents that, and `.gitignore` keeps a real `.env` out of git. |
| Gerber zip | The zip previously included macOS `__MACOSX` AppleDouble sidecars (163 bytes each). They only held a `com.apple.provenance` attribute, not a username or credential. Those entries were removed. The Gerber and drill bytes were left unchanged. |
| Fabrication metadata | Gerbers record a KiCad 10.0.4 export time of 2026-06-23 with timezone offset `+05:30`, plus a project id of `keyboard`. That is normal fab metadata, not a secret. Re-export if you would rather not publish the timestamp. |
| Public manufacturing files | Anyone can order this PCB from the Gerbers. That is intentional for an open hardware repo. |

## Design notes that are not code vulnerabilities

These are left as-is so the published Gerbers stay identical to the board file. Read them before you pay for a board:

* Traces are 0.2 mm. The two vias are a 0.3 mm drill in a 0.6 mm pad. Confirm those minimums with your fabricator.
* The board outline is a 328.5 × 100.5 mm rectangle with almost no margin past the outer keycaps, and there are no mounting holes. The case is meant to be glued, with PE foam in the bottom.
* GND is tied between the Pico's ground pins on the module footprint. There is no ground pour on the board.
* Paste Gerbers are essentially empty because the parts are through-hole.

`scripts/check_design.py` fails the build if a credential-shaped string shows up in the text files, or if the macOS junk returns to the Gerber zip.
