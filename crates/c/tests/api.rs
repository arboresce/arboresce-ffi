use arboresce_c::*;
use std::mem::{align_of, offset_of, size_of};

#[test]
fn identity_and_layout() {
    assert_eq!(arboresce_v1_abi_version(), 65536);
    assert_eq!(
        (ARBORESCE_OK, ARBORESCE_INVALID_ARGUMENT, ARBORESCE_PANIC),
        (0, 1, 2)
    );
    assert_eq!(size_of::<ArboresceStatus>(), 4);
    assert_eq!(size_of::<ArboresceStringView>(), 2 * size_of::<usize>());
    assert_eq!(align_of::<ArboresceStringView>(), align_of::<usize>());
    assert_eq!(offset_of!(ArboresceStringView, data), 0);
    assert_eq!(offset_of!(ArboresceStringView, len), size_of::<usize>());
}

#[test]
fn repeated_and_concurrent() {
    std::thread::scope(|scope| {
        for _ in 0..8 {
            scope.spawn(|| {
                let mut previous: *const std::ffi::c_char = std::ptr::null();
                for _ in 0..1000 {
                    let mut view = ArboresceStringView {
                        data: std::ptr::null(),
                        len: 0,
                    };
                    assert_eq!(unsafe { arboresce_v1_name(&mut view) }, ARBORESCE_OK);
                    let bytes =
                        unsafe { std::slice::from_raw_parts(view.data.cast::<u8>(), view.len) };
                    assert_eq!(bytes, b"Arboresce");
                    if !previous.is_null() {
                        assert_eq!(previous, view.data);
                    }
                    previous = view.data;
                }
            });
        }
    });
}

#[test]
fn null_is_invalid() {
    assert_eq!(
        unsafe { arboresce_v1_name(std::ptr::null_mut()) },
        ARBORESCE_INVALID_ARGUMENT
    );
}
