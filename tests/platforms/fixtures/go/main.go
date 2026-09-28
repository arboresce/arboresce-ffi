package main

import (
	"sync"

	"github.com/arboresce/arboresce-ffi/bindings/go"
)

func main() {
	if arboresce.Name != "Arboresce" {
		panic("name")
	}
	var group sync.WaitGroup
	for range 16 {
		group.Go(func() {
			for range 1000 {
				if arboresce.ProjectName() != "Arboresce" {
					panic("name")
				}
			}
		})
	}
	group.Wait()
	arboresce.PrintName()
}
