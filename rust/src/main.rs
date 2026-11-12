use std::process::ExitCode;

use ns2gen::{generate, Scene};

const USAGE: &str = "\
ns2gen-rs - ns2 scenario generator (core, no GUI yet)

usage:
  ns2gen-rs SCENE.json --export OUT.tcl   convert a scene to a TCL script
  ns2gen-rs SCENE.json --check            validate only, print problems
  ns2gen-rs --version
";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|a| a == "--version") {
        println!("ns2gen-rs {}", env!("CARGO_PKG_VERSION"));
        return ExitCode::SUCCESS;
    }
    if args.is_empty() || args.iter().any(|a| a == "-h" || a == "--help") {
        print!("{USAGE}");
        return ExitCode::SUCCESS;
    }

    let mut file: Option<&str> = None;
    let mut export: Option<&str> = None;
    let mut check = false;
    let mut it = args.iter();
    while let Some(a) = it.next() {
        match a.as_str() {
            "--export" => match it.next() {
                Some(p) => export = Some(p),
                None => {
                    eprintln!("ns2gen-rs: --export needs an output path");
                    return ExitCode::from(2);
                }
            },
            "--check" => check = true,
            s if s.starts_with("--") => {
                eprintln!("ns2gen-rs: unknown option {s}");
                return ExitCode::from(2);
            }
            s => file = Some(s),
        }
    }
    let Some(file) = file else {
        eprintln!("ns2gen-rs: need a scene file\n\n{USAGE}");
        return ExitCode::from(2);
    };

    let scene = match Scene::load(file) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("ns2gen-rs: {e}");
            return ExitCode::FAILURE;
        }
    };

    if check {
        let errs = ns2gen::validate(&scene);
        if errs.is_empty() {
            println!("ok");
            return ExitCode::SUCCESS;
        }
        for e in &errs {
            println!("{e}");
        }
        return ExitCode::FAILURE;
    }

    let Some(out) = export else {
        eprintln!("ns2gen-rs: nothing to do (use --export OUT.tcl or --check)");
        return ExitCode::from(2);
    };
    match generate(&scene) {
        Ok(tcl) => match std::fs::write(out, tcl) {
            Ok(()) => {
                println!("wrote {out}");
                ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("ns2gen-rs: {out}: {e}");
                ExitCode::FAILURE
            }
        },
        Err(e) => {
            eprintln!("ns2gen-rs: {e}");
            ExitCode::FAILURE
        }
    }
}
