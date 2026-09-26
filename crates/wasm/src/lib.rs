use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub fn name() -> String {
    arboresce::name().to_owned()
}
