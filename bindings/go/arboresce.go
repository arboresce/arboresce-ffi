package arboresce

import native "github.com/arboresce/arboresce-ffi/bindings/go/internal/native"

const Name = "Arboresce"

func ProjectName() string {
	return native.Name()
}

func PrintName() {
	native.PrintName()
}
