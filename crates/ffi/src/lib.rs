uniffi::setup_scaffolding!();

#[uniffi::export]
pub fn name() -> String {
    arboresce::name().to_owned()
}

#[uniffi::export]
pub fn print_name() {
    arboresce::print_name();
}
