use std::ffi::c_char;
use std::panic::{UnwindSafe, catch_unwind};
use std::ptr;

pub type ArboresceStatus = u32;

pub const ARBORESCE_ABI_VERSION: u32 = 0x0001_0000;
pub const ARBORESCE_OK: ArboresceStatus = 0;
pub const ARBORESCE_INVALID_ARGUMENT: ArboresceStatus = 1;
pub const ARBORESCE_PANIC: ArboresceStatus = 2;

#[repr(C)]
pub struct ArboresceStringView {
    pub data: *const c_char,
    pub len: usize,
}

fn boundary(operation: impl FnOnce() + UnwindSafe) -> ArboresceStatus {
    match catch_unwind(operation) {
        Ok(()) => ARBORESCE_OK,
        Err(_) => ARBORESCE_PANIC,
    }
}

unsafe fn name_with(
    out_name: *mut ArboresceStringView,
    operation: impl FnOnce() -> &'static str + UnwindSafe,
) -> ArboresceStatus {
    if out_name.is_null() {
        return ARBORESCE_INVALID_ARGUMENT;
    }
    unsafe {
        out_name.write(ArboresceStringView {
            data: ptr::null(),
            len: 0,
        });
    }
    boundary(|| {
        let name = operation();
        unsafe {
            out_name.write(ArboresceStringView {
                data: name.as_ptr().cast(),
                len: name.len(),
            });
        }
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn arboresce_v1_abi_version() -> u32 {
    ARBORESCE_ABI_VERSION
}

#[allow(
    clippy::missing_safety_doc,
    reason = "The pointer safety contract is maintained in DEVELOPERS.md"
)]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn arboresce_v1_name(out_name: *mut ArboresceStringView) -> ArboresceStatus {
    unsafe { name_with(out_name, arboresce::name) }
}

#[unsafe(no_mangle)]
pub extern "C" fn arboresce_v1_print_name() -> ArboresceStatus {
    boundary(arboresce::print_name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn panic_resets_output() {
        let mut output = ArboresceStringView {
            data: c"stale".as_ptr(),
            len: 5,
        };
        assert_eq!(
            unsafe { name_with(&mut output, || panic!("test panic")) },
            ARBORESCE_PANIC
        );
        assert!(output.data.is_null());
        assert_eq!(output.len, 0);
        assert_eq!(boundary(|| panic!("print panic")), ARBORESCE_PANIC);
    }

    #[test]
    fn null_never_runs_operation() {
        assert_eq!(
            unsafe { name_with(ptr::null_mut(), || panic!("must not run")) },
            ARBORESCE_INVALID_ARGUMENT
        );
    }

    #[test]
    fn panic_payload_drop_aborts_at_foreign_boundary() {
        struct PanickingDrop;
        impl Drop for PanickingDrop {
            fn drop(&mut self) {
                panic!("payload destructor");
            }
        }
        extern "C" fn aborting_boundary() {
            boundary(|| std::panic::panic_any(PanickingDrop));
        }
        if std::env::var_os("ARBORESCE_TEST_ABORT_CHILD").is_some() {
            aborting_boundary();
            unreachable!();
        }
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "tests::panic_payload_drop_aborts_at_foreign_boundary",
            ])
            .env("ARBORESCE_TEST_ABORT_CHILD", "1")
            .output()
            .unwrap();
        assert!(!output.status.success());
        assert!(String::from_utf8_lossy(&output.stderr).contains("cannot unwind"));
    }
}
