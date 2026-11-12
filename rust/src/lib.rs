//! ns2gen core: scene model, validation and ns2 TCL generation.
//! Output is kept byte-identical to the Python reference implementation.

pub mod json;
pub mod model;
pub mod tclgen;

pub use model::Scene;
pub use tclgen::{generate, validate};
