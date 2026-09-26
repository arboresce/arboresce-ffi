package arboresce_ffi

// #cgo darwin,arm64 LDFLAGS: ${SRCDIR}/lib/darwin_arm64/libarboresce_ffi.a -framework Security -framework CoreFoundation -liconv
// #cgo darwin,amd64 LDFLAGS: ${SRCDIR}/lib/darwin_amd64/libarboresce_ffi.a -framework Security -framework CoreFoundation -liconv
// #cgo linux,arm64 LDFLAGS: ${SRCDIR}/lib/linux_arm64/libarboresce_ffi.a -lgcc_s -ldl -lpthread -lm
// #cgo linux,amd64 LDFLAGS: ${SRCDIR}/lib/linux_amd64/libarboresce_ffi.a -lgcc_s -ldl -lpthread -lm
import "C"
