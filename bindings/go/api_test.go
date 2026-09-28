package arboresce_test

import (
	"os/exec"
	"sync"
	"testing"

	"github.com/arboresce/arboresce-ffi/bindings/go"
)

func TestIdentity(t *testing.T) {
	const identity = arboresce.Name
	if identity != "Arboresce" || arboresce.ProjectName() != "Arboresce" {
		t.Fatal("public identity differs")
	}
}

func TestRepeatedCalls(t *testing.T) {
	for range 1000 {
		if got := arboresce.ProjectName(); got != "Arboresce" {
			t.Fatalf("ProjectName() = %q", got)
		}
	}
}

func TestConcurrentCalls(t *testing.T) {
	var group sync.WaitGroup
	for range 8 {
		group.Go(func() {
			for range 128 {
				if got := arboresce.ProjectName(); got != "Arboresce" {
					t.Errorf("ProjectName() = %q", got)
				}
			}
		})
	}
	group.Wait()
}

func TestPrintName(t *testing.T) {
	output, err := exec.Command("go", "run", "./testdata/print-name").Output()
	if err != nil {
		t.Fatal(err)
	}
	if string(output) != "Arboresce\n" {
		t.Fatalf("PrintName output = %q", output)
	}
}
