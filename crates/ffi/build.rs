fn main() {
    if matches!(
        std::env::var("CARGO_CFG_TARGET_OS").unwrap().as_str(),
        "macos" | "ios"
    ) {
        println!("cargo:rustc-link-arg-cdylib=-Wl,-install_name,@rpath/libarboresce_ffi.dylib");
    }
}
