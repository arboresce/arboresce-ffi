#[napi_derive::napi]
pub fn name() -> String {
    arboresce::name().to_owned()
}

#[napi_derive::napi]
pub fn print_name() {
    arboresce::print_name();
}
