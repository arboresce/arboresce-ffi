package arboresce

import native "arboresce.ai/internal/native"

const Name = "Arboresce"

func ProjectName() string {
	return native.Name()
}

func PrintName() {
	native.PrintName()
}
