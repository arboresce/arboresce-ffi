fn main() {
    assert_eq!(std::env::var("CARGO_CFG_PANIC").unwrap(), "unwind");
    match std::env::var("CARGO_CFG_TARGET_OS").unwrap().as_str() {
        "macos" => {
            println!("cargo:rustc-link-arg-cdylib=-Wl,-install_name,@rpath/libarboresce_c.1.dylib");
            println!("cargo:rustc-link-arg-cdylib=-Wl,-compatibility_version,1.0");
            println!("cargo:rustc-link-arg-cdylib=-Wl,-current_version,1.0");
        }
        "linux" => println!("cargo:rustc-link-arg-cdylib=-Wl,-soname,libarboresce_c.so.1"),
        _ => {}
    }
}
