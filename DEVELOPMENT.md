# Development status

Last updated: 2026-11-12. Version 0.1.0 (pre-release).

## Components

| Part | Status | Notes |
|---|---|---|
| Scene model + JSON (Python) | Done | `ns2gen/model.py` |
| Validation + TCL generator (Python) | Done | Reference implementation |
| CLI export (`--export`) | Done | `python3 -m ns2gen scene.json --export out.tcl` |
| Tkinter GUI | Written, lightly tested | See "Known gaps" |
| Rust core (model, JSON, validation, TCL, CLI) | Done | `rust/`, matches Python byte for byte |
| Rust GUI | Not started | Plan: egui |
| Packaging (install script, .desktop, icon) | Written, untested | `packaging/` |
| CI | Written, never run | `.github/workflows/ci.yml` |

## What has been verified

- Python: 29 tests pass (generator, validation, geometry, undo, CLI).
- Rust: 10 tests pass, including 13 golden scenes and 34 number-format cases compared
  against Python output.
- Real ns2 2.35 (Ubuntu 22.04 package, run in a container) accepted and ran:
  `wired_basic`, `wired_sparse_ids`, `wireless_basic`, `wireless_all`.
- Real ns2 found one bug: simplex links were treated as two-way by the validator.
  Fixed. Directed reachability is now checked, and TCP also needs a return path for ACKs.

## What has NOT been verified

- `wired_all` after the simplex fix has not been rerun in ns2.
- The GUI has never been looked at by the author of the code. It was only exercised with a
  stubbed Tkinter. Layout, fonts, cursor handling and dialogs are unchecked on a real display.
- `packaging/install.sh` has been syntax-checked only.
- The CI workflow has never run. Its ns2 job greps output for error patterns and may
  need tuning.
- Output opened in `nam` (the visual player) has not been checked.

## Feature coverage (generated TCL)

Done:
- Wired: nodes, duplex and simplex links, queue type and limit, NAM layout hints
  (`orient`), NAM flow colours.
- Agents and applications: TCP (Tahoe, Reno, Newreno, Vegas, Sack1) with FTP; UDP with CBR.
- Wireless: `node-config` (AODV, DSDV, DSR, TORA; 802.11 or simple MAC; three propagation
  models), flat grid topography, node positions, `setdest` movements.
- Live validation with precise messages.

Not done:
- Applications: Telnet, Exponential, Pareto, CBR options such as random start, interval.
- LAN nodes, multicast, wired-cum-wireless (base stations), mixed topologies.
- Error models, link failures (`rtmodel`), custom routing protocol choice for wired
  (`rtproto`), per-link queue parameters (RED thresholds).
- Energy model, node colour/shape, trace file post-processing.
- Importing an existing `.tcl` file.

## Known gaps and risks

- Wireless scenes can produce very large trace files (a 33 s, 4-node DSDV run gave about
  480k lines). Consider a trace-detail option.
- The `propagation` and `antenna` choices are single-entry lists for some options, which
  makes those dropdowns look pointless until more values are added.
- Node ids are re-indexed from 0 in the TCL output, sorted by id. Labels appear as comments.
- GUI Settings dialog rescales node positions when topology size changes.
- Wireless mode has no link tool by design. Switching mode keeps old links in the file but
  ignores them.

## Roadmap

1. **Verify what exists**
   - Rerun `wired_all` in ns2. Run CI on GitHub and fix the ns2 job.
   - Open the GUI on a real display, fix visible bugs, add screenshots to the README.
   - Try `packaging/install.sh` on Ubuntu, Fedora and Arch.
2. **More ns2 features** (each needs a golden scene, a Rust port, and an ns2 run)
   - Telnet, Exponential, Pareto applications
   - Link failures, error models
   - RED parameters, rtproto choice
   - LAN nodes
3. **Rust GUI** (egui), reusing the Rust core. Keep the Python GUI until parity.
4. **Packaging**: PKGBUILD for Arch, `.deb`, AppImage, GitHub release binaries.
5. **Nice to have**: import `.tcl`, trace file summary (throughput, loss), NAM preview,
   example gallery, translated UI.

## Decisions

- **Python first, Rust port second.** Python is faster to change. Golden files keep the
  Rust version honest.
- **No dependencies.** Easy install on any distro, offline builds, small attack surface.
- **ns2, not ns-3.** The target audience uses ns2 coursework scripts.
- **Scene file is JSON.** Same format in Python and Rust. Unknown keys are ignored and
  missing keys use defaults, so old files keep loading.

## How to update this file

Change the date and the status table when you finish something. Move items between
"verified" and "NOT verified" only after you actually ran the check.
