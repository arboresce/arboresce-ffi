# Arboresce Go SDK

Go SDK for Arboresce.

The module path is `arboresce.ai`. HTTPS module discovery must map it to
`bindings/go` in [arboresce/arboresce-ffi](https://github.com/arboresce/arboresce-ffi).
Version tags use `bindings/go/v<version>`; distribution snapshots include the
native libraries required by cgo. The `master` branch contains source only.
See the repository's release notes for available versions.

```bash
go get arboresce.ai@v0.0.0
```

```go
package main

import "arboresce.ai"

func main() {
    arboresce.PrintName()
}
```
