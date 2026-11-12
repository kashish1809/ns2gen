//! Compares the Rust port against files produced by the Python reference
//! (python3 tests/make_golden.py).

use std::fs;
use std::path::PathBuf;

use ns2gen::tclgen::g;
use ns2gen::{generate, validate, Scene};

fn golden_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../tests/golden")
}

#[test]
fn scenes_match_python() {
    let mut names: Vec<String> = fs::read_dir(golden_dir())
        .expect("run python3 tests/make_golden.py first")
        .filter_map(|e| e.ok())
        .filter_map(|e| e.file_name().into_string().ok())
        .filter_map(|n| n.strip_suffix(".json").map(String::from))
        .collect();
    names.sort();
    assert!(names.len() >= 10, "expected golden scenes, found {}", names.len());

    for name in &names {
        let dir = golden_dir();
        let scene = Scene::load(dir.join(format!("{name}.json")).to_str().unwrap())
            .unwrap_or_else(|e| panic!("{name}: cannot load: {e}"));
        let tcl_path = dir.join(format!("{name}.tcl"));
        let err_path = dir.join(format!("{name}.err"));
        if tcl_path.exists() {
            let want = fs::read_to_string(&tcl_path).unwrap();
            let got = generate(&scene).unwrap_or_else(|e| panic!("{name}: unexpected errors:\n{e}"));
            assert_eq!(got, want, "TCL differs for {name}");
        } else {
            let want = fs::read_to_string(&err_path).unwrap();
            let got = validate(&scene).join("\n") + "\n";
            assert_eq!(got, want, "errors differ for {name}");
            assert!(generate(&scene).is_err(), "{name}: generate should fail");
        }
    }
}

#[test]
fn number_format_matches_python() {
    let text = fs::read_to_string(golden_dir().join("g_cases.txt")).unwrap();
    let mut n = 0;
    for line in text.lines() {
        let (v, want) = line.split_once('\t').unwrap();
        let v: f64 = v.parse().unwrap();
        assert_eq!(g(v), want, "g({v})");
        n += 1;
    }
    assert!(n > 20);
}

#[test]
fn json_roundtrip_keeps_output() {
    for name in ["wired_all", "wireless_all", "wired_sparse_ids"] {
        let p = golden_dir().join(format!("{name}.json"));
        let sc = Scene::load(p.to_str().unwrap()).unwrap();
        let back = Scene::from_json_str(&sc.to_json_string()).unwrap();
        assert_eq!(sc, back, "{name}");
        assert_eq!(generate(&sc), generate(&back));
    }
}

#[test]
fn remove_node_cascades() {
    let p = golden_dir().join("wired_basic.json");
    let mut sc = Scene::load(p.to_str().unwrap()).unwrap();
    sc.remove_node(2);
    assert!(sc.links.iter().all(|l| l.a != 2 && l.b != 2));
    assert!(sc.flows.is_empty());
    assert_eq!(sc.next_node_id(), 2);
}

#[test]
fn bad_json_reports_error() {
    assert!(Scene::from_json_str("[]").is_err());
    assert!(Scene::from_json_str(r#"{"nodes": [{"x": 1}]}"#).is_err());
    assert!(Scene::from_json_str(r#"{"nodes": [{"id": 1.5}]}"#).is_err());
    assert!(Scene::from_json_str(r#"{"flows": "no"}"#).is_err());
    assert!(Scene::from_json_str("{").is_err());
}
