# CLAUDE.md

Guidance for AI coding assistants working in this repository.

## What this project is

ns2gen: a desktop tool that draws a network topology and generates an ns2 (network
simulator 2) TCL script. Inspired by NSG2. Python reference implementation with a Tkinter
GUI, plus a dependency-free Rust port of the core in `rust/`.

Read `DEVELOPMENT.md` for current status and `CONTRIBUTING.md` for the workflow.

## Layout

```
ns2gen/model.py      scene dataclasses + JSON load/save
ns2gen/tclgen.py     validate() and generate(): pure functions, the heart of the project
ns2gen/geometry.py   canvas math (no GUI imports)
ns2gen/history.py    undo/redo over JSON snapshots
ns2gen/gui.py        Tkinter app (only file that imports tkinter)
ns2gen/cli.py        entry point; --export runs without a display
tests/               pytest; make_golden.py writes tests/golden/*
rust/src/            json.rs, model.rs, tclgen.rs, main.rs (std only)
rust/tests/golden.rs compares Rust against the Python golden files
packaging/           install.sh, .desktop, icon
examples/            sample scene files
```

## Commands

```bash
python3 -m ns2gen                         # GUI
python3 -m ns2gen scene.json --export out.tcl
python3 tests/make_golden.py              # regenerate golden files (run before Rust tests)
python3 -m pytest -q tests
cargo test --manifest-path rust/Cargo.toml
```

Always run all three test commands after changing generator code.

## Rules

1. **Python is the reference.** Change Python first, regenerate golden files, then port to
   Rust until `cargo test` passes. Output and error text must match byte for byte.
2. **No new dependencies**, Python or Rust, without asking.
3. **Keep `model.py`, `tclgen.py`, `geometry.py`, `history.py` free of Tkinter imports.**
4. **Every validation rule gets a test and a golden `.err` case.** Error strings are part
   of the contract between Python and Rust. Do not reword them casually.
5. **New model fields need defaults** so old scene files still load. Update both
   `Scene.from_dict` (Python) and `Scene::from_json` / `to_json` (Rust).
6. **Python integer-versus-float output** goes through `g()` (`f"{v:g}"` semantics). The
   Rust `g()` mirrors it. Do not format numbers any other way in generated TCL.
7. **GUI edits:** call `self.push()` before mutating the scene and `self.changed()` after.
8. Do not claim something works in ns2 unless it was actually run. Say what was and was
   not verified.

## Environment notes

- The sandbox used to build this may lack Tkinter. GUI logic was exercised with a stubbed
  `tkinter` module. A real display is needed to judge layout.
- ns2 is not installed by default. Use a container (Ubuntu 22.04 `apt install ns2`) to run
  generated scripts. Remove the `exec nam` line when there is no display.
- Keep Rust building offline (`cargo test --offline`). Do not add crates.

## Style

- Python: type hints, small functions, no print debugging in library modules.
- Rust: `cargo fmt` style, no `unsafe`, no `unwrap` on user input paths.
- Error messages are short sentences that tell the user what to fix.
- Keep files focused. If `gui.py` grows past a comfortable size, split dialogs out.

## Known ns2 gotchas

- Simplex links carry traffic one way only. TCP needs a path back for ACKs. The validator
  models this as a directed graph.
- Output files named in the scene must use only letters, digits, `. _ - /`. Subfolders
  must exist before ns2 runs.
- `exec nam ...` in `finish` fails on a machine with no display.
- Wireless traces get large quickly.
