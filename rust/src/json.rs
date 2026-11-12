//! Minimal JSON parser and writer (std only).

#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Num(f64),
    Str(String),
    Arr(Vec<Value>),
    Obj(Vec<(String, Value)>),
}

impl Value {
    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Obj(items) => items.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }
}

const MAX_DEPTH: usize = 128;

pub fn parse(text: &str) -> Result<Value, String> {
    let mut p = Parser { s: text.as_bytes(), i: 0 };
    p.ws();
    let v = p.value(0)?;
    p.ws();
    if p.i != p.s.len() {
        return Err(p.err("trailing characters"));
    }
    Ok(v)
}

struct Parser<'a> {
    s: &'a [u8],
    i: usize,
}

impl<'a> Parser<'a> {
    fn err(&self, msg: &str) -> String {
        format!("JSON error at byte {}: {}", self.i, msg)
    }

    fn ws(&mut self) {
        while self.i < self.s.len() && matches!(self.s[self.i], b' ' | b'\t' | b'\n' | b'\r') {
            self.i += 1;
        }
    }

    fn peek(&self) -> Option<u8> {
        self.s.get(self.i).copied()
    }

    fn lit(&mut self, word: &str, v: Value) -> Result<Value, String> {
        if self.s[self.i..].starts_with(word.as_bytes()) {
            self.i += word.len();
            Ok(v)
        } else {
            Err(self.err("invalid literal"))
        }
    }

    fn value(&mut self, depth: usize) -> Result<Value, String> {
        if depth > MAX_DEPTH {
            return Err(self.err("nesting too deep"));
        }
        match self.peek() {
            None => Err(self.err("unexpected end")),
            Some(b'n') => self.lit("null", Value::Null),
            Some(b't') => self.lit("true", Value::Bool(true)),
            Some(b'f') => self.lit("false", Value::Bool(false)),
            Some(b'"') => Ok(Value::Str(self.string()?)),
            Some(b'[') => {
                self.i += 1;
                let mut items = Vec::new();
                self.ws();
                if self.peek() == Some(b']') {
                    self.i += 1;
                    return Ok(Value::Arr(items));
                }
                loop {
                    self.ws();
                    items.push(self.value(depth + 1)?);
                    self.ws();
                    match self.peek() {
                        Some(b',') => self.i += 1,
                        Some(b']') => {
                            self.i += 1;
                            return Ok(Value::Arr(items));
                        }
                        _ => return Err(self.err("expected , or ]")),
                    }
                }
            }
            Some(b'{') => {
                self.i += 1;
                let mut items = Vec::new();
                self.ws();
                if self.peek() == Some(b'}') {
                    self.i += 1;
                    return Ok(Value::Obj(items));
                }
                loop {
                    self.ws();
                    if self.peek() != Some(b'"') {
                        return Err(self.err("expected string key"));
                    }
                    let k = self.string()?;
                    self.ws();
                    if self.peek() != Some(b':') {
                        return Err(self.err("expected :"));
                    }
                    self.i += 1;
                    self.ws();
                    let v = self.value(depth + 1)?;
                    items.push((k, v));
                    self.ws();
                    match self.peek() {
                        Some(b',') => self.i += 1,
                        Some(b'}') => {
                            self.i += 1;
                            return Ok(Value::Obj(items));
                        }
                        _ => return Err(self.err("expected , or }")),
                    }
                }
            }
            Some(b'-') | Some(b'0'..=b'9') => self.number(),
            Some(_) => Err(self.err("unexpected character")),
        }
    }

    fn number(&mut self) -> Result<Value, String> {
        let start = self.i;
        while self.i < self.s.len()
            && matches!(self.s[self.i], b'-' | b'+' | b'.' | b'e' | b'E' | b'0'..=b'9')
        {
            self.i += 1;
        }
        let txt = std::str::from_utf8(&self.s[start..self.i]).map_err(|_| self.err("bad number"))?;
        txt.parse::<f64>().map(Value::Num).map_err(|_| self.err("bad number"))
    }

    fn hex4(&mut self) -> Result<u32, String> {
        if self.i + 4 > self.s.len() {
            return Err(self.err("short \\u escape"));
        }
        let h = std::str::from_utf8(&self.s[self.i..self.i + 4]).map_err(|_| self.err("bad \\u escape"))?;
        let n = u32::from_str_radix(h, 16).map_err(|_| self.err("bad \\u escape"))?;
        self.i += 4;
        Ok(n)
    }

    fn string(&mut self) -> Result<String, String> {
        self.i += 1; // opening quote
        let mut out: Vec<u8> = Vec::new();
        loop {
            let b = match self.peek() {
                None => return Err(self.err("unterminated string")),
                Some(b) => b,
            };
            self.i += 1;
            match b {
                b'"' => break,
                b'\\' => {
                    let e = self.peek().ok_or_else(|| self.err("bad escape"))?;
                    self.i += 1;
                    let ch = match e {
                        b'"' => '"',
                        b'\\' => '\\',
                        b'/' => '/',
                        b'b' => '\u{8}',
                        b'f' => '\u{c}',
                        b'n' => '\n',
                        b'r' => '\r',
                        b't' => '\t',
                        b'u' => {
                            let mut cp = self.hex4()?;
                            if (0xD800..0xDC00).contains(&cp) {
                                if self.s[self.i..].starts_with(b"\\u") {
                                    self.i += 2;
                                    let lo = self.hex4()?;
                                    if !(0xDC00..0xE000).contains(&lo) {
                                        return Err(self.err("bad surrogate pair"));
                                    }
                                    cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                                } else {
                                    return Err(self.err("lone surrogate"));
                                }
                            }
                            char::from_u32(cp).ok_or_else(|| self.err("bad code point"))?
                        }
                        _ => return Err(self.err("bad escape")),
                    };
                    let mut buf = [0u8; 4];
                    out.extend_from_slice(ch.encode_utf8(&mut buf).as_bytes());
                }
                0..=0x1f => return Err(self.err("control character in string")),
                _ => out.push(b),
            }
        }
        String::from_utf8(out).map_err(|_| self.err("invalid UTF-8"))
    }
}

// ---------------------------------------------------------------- writer
pub fn to_string_pretty(v: &Value) -> String {
    let mut out = String::new();
    write_value(v, 0, &mut out);
    out.push('\n');
    out
}

fn write_value(v: &Value, indent: usize, out: &mut String) {
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Num(n) => out.push_str(&num_text(*n)),
        Value::Str(s) => write_str(s, out),
        Value::Arr(items) => {
            if items.is_empty() {
                out.push_str("[]");
                return;
            }
            out.push_str("[\n");
            for (i, it) in items.iter().enumerate() {
                pad(indent + 2, out);
                write_value(it, indent + 2, out);
                out.push_str(if i + 1 < items.len() { ",\n" } else { "\n" });
            }
            pad(indent, out);
            out.push(']');
        }
        Value::Obj(items) => {
            if items.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push_str("{\n");
            for (i, (k, it)) in items.iter().enumerate() {
                pad(indent + 2, out);
                write_str(k, out);
                out.push_str(": ");
                write_value(it, indent + 2, out);
                out.push_str(if i + 1 < items.len() { ",\n" } else { "\n" });
            }
            pad(indent, out);
            out.push('}');
        }
    }
}

fn pad(n: usize, out: &mut String) {
    for _ in 0..n {
        out.push(' ');
    }
}

fn num_text(n: f64) -> String {
    if n.is_finite() && n.fract() == 0.0 && n.abs() < 1e15 {
        format!("{}", n as i64)
    } else if n.is_finite() {
        format!("{}", n)
    } else {
        "null".to_string()
    }
}

fn write_str(s: &str, out: &mut String) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_basics() {
        let v = parse(r#" {"a": [1, 2.5, -3e2, true, null], "s": "x\"\u00e9\n"} "#).unwrap();
        assert_eq!(
            v.get("a"),
            Some(&Value::Arr(vec![
                Value::Num(1.0), Value::Num(2.5), Value::Num(-300.0), Value::Bool(true), Value::Null
            ]))
        );
        assert_eq!(v.get("s"), Some(&Value::Str("x\"é\n".into())));
    }

    #[test]
    fn surrogate_pair() {
        assert_eq!(parse(r#""\ud83d\ude00""#).unwrap(), Value::Str("😀".into()));
    }

    #[test]
    fn rejects_bad_input() {
        for bad in ["", "{", "[1,]", "{\"a\" 1}", "tru", "\"abc", "1 2", "\"\\x\"", "[1 2]"] {
            assert!(parse(bad).is_err(), "should reject {bad:?}");
        }
    }

    #[test]
    fn roundtrip() {
        let src = r#"{"a":[1,2.5,"t\n"],"b":{"c":null,"d":false},"e":[]}"#;
        let v = parse(src).unwrap();
        assert_eq!(parse(&to_string_pretty(&v)).unwrap(), v);
    }

    #[test]
    fn deep_nesting_rejected() {
        let s = "[".repeat(500) + &"]".repeat(500);
        assert!(parse(&s).is_err());
    }
}
