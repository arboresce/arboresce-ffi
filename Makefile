.DEFAULT_GOAL := help
.PHONY: package-c package-cpp test-c-package test-cpp-package package-python package-swift test-swift-consumer build-kotlin-all
package-c package-cpp test-c-package test-cpp-package package-python package-swift test-swift-consumer build-kotlin-all:
	@bash scripts/make.sh $@
.PHONY: check-rust
check-rust:
	@bash scripts/make.sh check-rust
.PHONY: help doctor setup setup-apple setup-android setup-linux generate generate-python generate-kotlin generate-swift generate-go build build-rust build-python build-typescript build-node build-wasm build-kotlin build-swift build-swift-apple build-go build-android build-linux check check-generated format test test-python test-node test-wasm test-kotlin test-go test-swift test-linux verify

help:
	@bash scripts/make.sh help

doctor:
	@bash scripts/make.sh doctor

setup:
	@bash scripts/make.sh setup

setup-apple:
	@bash scripts/make.sh setup-apple

setup-android:
	@bash scripts/make.sh setup-android

setup-linux:
	@bash scripts/make.sh setup-linux

generate:
	@bash scripts/make.sh generate

generate-python:
	@bash scripts/make.sh generate-python

generate-kotlin:
	@bash scripts/make.sh generate-kotlin

generate-swift:
	@bash scripts/make.sh generate-swift

generate-go:
	@bash scripts/make.sh generate-go

build:
	@bash scripts/make.sh build

build-rust:
	@bash scripts/make.sh build-rust

build-python:
	@bash scripts/make.sh build-python

build-typescript:
	@bash scripts/make.sh build-typescript

build-node:
	@bash scripts/make.sh build-node

build-wasm:
	@bash scripts/make.sh build-wasm

build-kotlin:
	@bash scripts/make.sh build-kotlin

build-swift:
	@bash scripts/make.sh build-swift

.PHONY: check-swift-local
check-swift-local:
	@bash scripts/make.sh check-swift-local

build-swift-apple:
	@bash scripts/make.sh build-swift-apple

build-go:
	@bash scripts/make.sh build-go

build-android:
	@bash scripts/make.sh build-android

build-linux:
	@bash scripts/make.sh build-linux

check:
	@bash scripts/make.sh check

check-generated:
	@bash scripts/make.sh check-generated

format:
	@bash scripts/make.sh format

test:
	@bash scripts/make.sh test

test-python:
	@bash scripts/make.sh test-python

test-node:
	@bash scripts/make.sh test-node

test-wasm:
	@bash scripts/make.sh test-wasm

test-kotlin:
	@bash scripts/make.sh test-kotlin

test-go:
	@bash scripts/make.sh test-go

test-swift:
	@bash scripts/make.sh test-swift

test-linux:
	@bash scripts/make.sh test-linux

verify:
	@bash scripts/make.sh verify

.PHONY: setup-go
setup-go:
	@bash scripts/make.sh setup-go

.PHONY: doctor-go
doctor-go:
	@bash scripts/make.sh doctor-go

.PHONY: check-go-generator
check-go-generator:
	@bash scripts/make.sh check-go-generator

.PHONY: build-go-all
build-go-all:
	@bash scripts/make.sh build-go-all

.PHONY: build-node-all build-android-aar
build-node-all:
	@bash scripts/make.sh build-node-all
build-android-aar:
	@bash scripts/make.sh build-android-aar

.PHONY: setup-rust
setup-rust:
	@bash scripts/make.sh setup-rust

.PHONY: setup-python
setup-python:
	@bash scripts/make.sh setup-python

.PHONY: setup-typescript
setup-typescript:
	@bash scripts/make.sh setup-typescript

.PHONY: setup-kotlin
setup-kotlin:
	@bash scripts/make.sh setup-kotlin

.PHONY: setup-swift
setup-swift:
	@bash scripts/make.sh setup-swift

.PHONY: doctor-rust
doctor-rust:
	@bash scripts/make.sh doctor-rust

.PHONY: doctor-python
doctor-python:
	@bash scripts/make.sh doctor-python

.PHONY: doctor-typescript
doctor-typescript:
	@bash scripts/make.sh doctor-typescript

.PHONY: doctor-kotlin
doctor-kotlin:
	@bash scripts/make.sh doctor-kotlin

.PHONY: doctor-swift
doctor-swift:
	@bash scripts/make.sh doctor-swift

.PHONY: test-rust
test-rust:
	@bash scripts/make.sh test-rust

.PHONY: setup-browser
setup-browser:
	@bash scripts/make.sh setup-browser

.PHONY: test-browser
test-browser:
	@bash scripts/make.sh test-browser

.PHONY: test-ios
test-ios:
	@bash scripts/make.sh test-ios

.PHONY: test-android
test-android:
	@bash scripts/make.sh test-android

.PHONY: test-swift-platforms
test-swift-platforms:
	@bash scripts/make.sh test-swift-platforms

.PHONY: test-go-platforms
test-go-platforms:
	@bash scripts/make.sh test-go-platforms

.PHONY: setup-checks setup-c setup-cpp doctor-c doctor-cpp generate-c check-generated-c build-c build-cpp install-c test-c test-c-static test-c-shared test-c-abi test-c-consumer test-cpp test-cpp-consumer test-cpp-no-exceptions package-typescript package-typescript-all package-go package-kotlin package-kotlin-all package-android test-typescript-consumer test-browser-consumer test-go-consumer test-kotlin-consumer test-python-types stage-swift-dev check-support update-support check-python format-python check-typescript format-typescript check-go format-go check-kotlin format-kotlin check-swift format-swift check-c format-c check-cpp format-cpp
setup-checks setup-c setup-cpp doctor-c doctor-cpp generate-c check-generated-c build-c build-cpp install-c test-c test-c-static test-c-shared test-c-abi test-c-consumer test-cpp test-cpp-consumer test-cpp-no-exceptions package-typescript package-typescript-all package-go package-kotlin package-kotlin-all package-android test-typescript-consumer test-browser-consumer test-go-consumer test-kotlin-consumer test-python-types stage-swift-dev check-support update-support check-python format-python check-typescript format-typescript check-go format-go check-kotlin format-kotlin check-swift format-swift check-c format-c check-cpp format-cpp:
	@bash scripts/make.sh $@

.PHONY: test-tooling
test-tooling:
	@bash scripts/make.sh test-tooling

.PHONY: test-packaged-go test-packaged-swift test-packaged-ios test-packaged-android test-packaged-c test-packaged-cpp
test-packaged-go test-packaged-swift test-packaged-ios test-packaged-android test-packaged-c test-packaged-cpp:
	@bash scripts/make.sh $@
