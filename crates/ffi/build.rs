fn main() {
    if matches!(
        std::env::var("CARGO_CFG_TARGET_OS").unwrap().as_str(),
        "macos" | "ios"
    ) {
        println!("cargo:rustc-link-arg-cdylib=-Wl,-install_name,@rpath/libarboresce_ffi.dylib");
    }
    if std::env::var("CARGO_CFG_TARGET_OS").unwrap() == "linux"
        && std::env::var("PROFILE").unwrap() == "release"
    {
        let root = std::env::var("CARGO_MANIFEST_DIR").unwrap();
        println!("cargo:rerun-if-changed=linux.ld");
        println!("cargo:rustc-link-arg-cdylib=-Wl,-T,{root}/linux.ld");
    }
}
