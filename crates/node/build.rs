fn main() {
    napi_build::setup();
    if std::env::var("CARGO_CFG_TARGET_OS").unwrap() == "macos" {
        println!("cargo:rustc-link-arg-cdylib=-Wl,-install_name,@rpath/libarboresce_node.dylib");
    }
}
