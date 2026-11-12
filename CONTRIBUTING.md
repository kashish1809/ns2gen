# Contributing to ns2gen

Thanks for helping. ns2gen draws a network topology and writes an ns2 TCL script. This
page explains how to set up, what the rules are, and how to send a change.

## Ground rules

- **Python is the reference.** Rust must produce byte-identical output.
- **No runtime dependencies.** Python uses the standard library only (Tkinter for the GUI).
  The Rust core uses `std` only. Do not add a crate or package without discussing it first.
- **Generator logic stays out of the GUI.** `model.py`, `tclgen.py`, `geometry.py` and
  `history.py` must never import Tkinter. This keeps them testable without a display.
- **Validation before generation.** Anything that makes ns2 fail should be caught by
  `validate()` with a clear message. If you find a script that breaks ns2, that is a bug.
- Be kind in issues and reviews.

## Setup

You need Python 3.8+, Tkinter, and Rust (stable) if you touch `rust/`.

| Distro | Tkinter |
|---|---|
| Debian/Ubuntu | `sudo apt install python3-tk` |
| Fedora | `sudo dnf install python3-tkinter` |
| Arch | `sudo pacman -S tk` |

```bash
git clone https://github.com/YOUR_USERNAME/ns2gen.git
cd ns2gen
pip install pytest          # tests only
python3 -m ns2gen           # run the GUI without installing
```

ns2 itself is optional but very useful for checking output. Easiest route on any distro
is a container:

```bash
python3 -m ns2gen examples/wired-dumbbell.json --export out.tcl
sed -i '/exec nam/d' out.tcl        # no display in a container
podman run --rm -v "$PWD":/w:Z -w /w docker.io/library/ubuntu:22.04 \
  bash -c "apt-get update -qq && apt-get install -y -qq ns2 >/dev/null && ns out.tcl && ls"
```

Success means no error text and `out.tr` plus `out.nam` appear.

## Before you open a pull request

Run all three, in this order:

```bash
python3 tests/make_golden.py                    # regenerate golden files from Python
python3 -m pytest tests                         # Python tests
cargo test --manifest-path rust/Cargo.toml      # Rust must match the golden files
```

CI runs the same checks, plus a job that feeds every golden scene to real ns2.

If your change alters generated TCL or error text, the golden files in `tests/golden/`
will change. Commit them in the same pull request and say why in the description.

## Changing the generator

1. Edit `ns2gen/tclgen.py` (and `ns2gen/model.py` if you add a field).
2. Add a scene to `tests/make_golden.py` that exercises the change. Valid scenes produce
   a `.tcl` golden file. Invalid scenes produce an `.err` file. Add one of each when you
   add a validation rule.
3. Add a focused test in `tests/test_tclgen.py`.
4. Port the change to `rust/src/tclgen.rs` and `rust/src/model.rs`. Error messages must
   match character for character.
5. Run the three commands above.
6. Run the new scene through real ns2 if you can, and say so in the pull request.

New model fields need a default so old `.json` scenes still load.

## Changing the GUI

- Everything lives in `ns2gen/gui.py`. Keep widgets thin and push logic into the pure modules.
- Every edit must call `self.push()` before changing the scene (undo) and `self.changed()`
  after it (redraw, preview, dirty flag).
- Test on a real display. Include a screenshot in the pull request for visible changes.
- The GUI has no automated tests with real Tkinter yet. Contributions here are welcome.

## Commit and pull request style

- Small, focused commits. Imperative subject line, under 70 characters:
  `Validate simplex links as one-way`.
- One topic per pull request.
- Describe what changed, why, and how you checked it (tests, ns2 run, screenshot).

## Reporting bugs

Open an issue with:
- your distro, Python version, ns2 version (if relevant)
- the scene `.json` (attach it) and the exported `.tcl`
- what you expected, and what happened (paste the ns2 error text if there is one)

## Good first issues

See `DEVELOPMENT.md` for the roadmap. Easy places to start: new traffic applications
(Telnet, Exponential, Pareto), more queue types, GUI polish, and more example scenes.
