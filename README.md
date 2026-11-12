# ns2gen

Desktop scenario generator for the **ns2** network simulator. Draw a topology, set
link and traffic properties, get a ready-to-run TCL script. Inspired by NSG2.

Pure Python, standard library only (Tkinter for the GUI).

## Install

Needs Python 3.8+ with Tkinter:

| Distro | Command |
|---|---|
| Debian/Ubuntu | `sudo apt install python3-tk python3-venv` |
| Fedora | `sudo dnf install python3-tkinter` |
| Arch | `sudo pacman -S tk` |
| openSUSE | `sudo zypper install python3-tk` |

Then, from this folder:

```bash
./packaging/install.sh            # per-user install + app menu entry
./packaging/install.sh --uninstall
```

No install needed to just try it: `python3 -m ns2gen`.

## Use

```bash
ns2gen                              # open GUI
ns2gen examples/wired-dumbbell.json # open a scene
ns2gen scene.json --export out.tcl  # no GUI, scene -> TCL
```

1. **Add Node**: click canvas. **Add Link**: click two nodes.
2. **TCP Flow (FTP)** / **UDP Flow (CBR)**: click source, then destination.
3. Select anything to edit it in the Properties panel. TCL preview updates live.
4. **Simulation > Settings**: wired or wireless, stop time, file names, wireless options
   (routing, MAC, propagation...). Wireless nodes get X/Y and optional movements.
5. **File > Export TCL**, then `ns out.tcl`. Or **Run with ns2** if `ns` is in PATH.

Scenes are saved as `.json` (Ctrl+S). Undo/redo: Ctrl+Z / Ctrl+Y.

## What it generates

- Wired: nodes, duplex/simplex links, queue type and limit, NAM layout hints,
  TCP (Tahoe/Reno/Newreno/Vegas/Sack1) + FTP, UDP + CBR, NAM flow colors.
- Wireless: `node-config` with AODV/DSDV/DSR/TORA, 802.11 MAC, node positions,
  `setdest` movements, same TCP/UDP flows.
- Live validation: bad bandwidth/delay, duplicate links, flows with no path,
  flows ending after simulation end, nodes outside the topology, etc.

## Layout

```
ns2gen/model.py     scene dataclasses + JSON
ns2gen/tclgen.py    validation + TCL generation (pure, tested)
ns2gen/geometry.py  canvas math
ns2gen/history.py   undo/redo
ns2gen/gui.py       Tkinter app
ns2gen/cli.py       entry point
tests/              pytest
```

Run tests: `python3 -m pytest tests`

## Rust core (work in progress)

`rust/` is a dependency-free Rust port of the model, validation and TCL generator, plus a CLI.
Output is byte-identical to the Python version, checked against golden files.

```bash
python3 tests/make_golden.py          # regenerate golden files from Python
cd rust && cargo test                 # Rust must match them
cargo run --release -- ../examples/wired-dumbbell.json --export out.tcl
```

GUI is still Python/Tkinter. Next step is an egui front end on top of this core.

## Not done yet

Mobile/wireless traffic variants beyond TCP/UDP, Telnet/Exponential/Pareto apps,
LAN nodes, multicast, error models, trace analysis.

Generated scripts were run with ns2 2.35 (Ubuntu 22.04 package) for basic wired and
wireless scenes. The CI workflow runs all golden scenes through real `ns`.

## Contributing

Run `python3 tests/make_golden.py`, `python3 -m pytest tests` and
`cargo test --manifest-path rust/Cargo.toml` before opening a pull request.
Python is the reference implementation. If you change generator output, regenerate the
golden files and keep the Rust port in sync.

## License

MIT. See `LICENSE`.
