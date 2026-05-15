# SelfFork body daemon — cross-platform build matrix.
#
# Targets: macOS (arm64+amd64), Linux (amd64+arm64), Windows (amd64).
# Apple notarize + Azure Trusted Signing + .deb packaging are operator-driven
# (we don't bake credentials into the Makefile).

VERSION := $(shell git describe --tags --always 2>/dev/null || echo "0.0.0-dev")
LDFLAGS := -X main.Version=$(VERSION)
BIN := selffork-daemon
DIST := dist

.PHONY: all clean test \
	macos-arm64 macos-amd64 \
	linux-amd64 linux-arm64 \
	windows-amd64 \
	dmg-macos deb-ubuntu msi-windows

all: macos-arm64 macos-amd64 linux-amd64 linux-arm64 windows-amd64

clean:
	rm -rf $(DIST)

test:
	go test ./...

macos-arm64:
	@mkdir -p $(DIST)
	GOOS=darwin GOARCH=arm64 go build -ldflags "$(LDFLAGS)" -o $(DIST)/$(BIN)-darwin-arm64 ./cmd/selffork-daemon

macos-amd64:
	@mkdir -p $(DIST)
	GOOS=darwin GOARCH=amd64 go build -ldflags "$(LDFLAGS)" -o $(DIST)/$(BIN)-darwin-amd64 ./cmd/selffork-daemon

linux-amd64:
	@mkdir -p $(DIST)
	GOOS=linux GOARCH=amd64 go build -ldflags "$(LDFLAGS)" -o $(DIST)/$(BIN)-linux-amd64 ./cmd/selffork-daemon

linux-arm64:
	@mkdir -p $(DIST)
	GOOS=linux GOARCH=arm64 go build -ldflags "$(LDFLAGS)" -o $(DIST)/$(BIN)-linux-arm64 ./cmd/selffork-daemon

windows-amd64:
	@mkdir -p $(DIST)
	GOOS=windows GOARCH=amd64 go build -ldflags "$(LDFLAGS)" -o $(DIST)/$(BIN)-windows-amd64.exe ./cmd/selffork-daemon

dmg-macos:
	@command -v hdiutil >/dev/null || (echo "hdiutil missing — run on macOS" && exit 1)
	hdiutil create -volname SelfForkDaemon \
		-srcfolder $(DIST)/$(BIN)-darwin-arm64 \
		-ov -format UDZO \
		$(DIST)/SelfForkDaemon.dmg

deb-ubuntu:
	@command -v fpm >/dev/null || (echo "fpm missing — gem install fpm" && exit 1)
	fpm -s dir -t deb -n selffork-daemon -v $(VERSION) -a amd64 \
		--description "SelfFork body daemon" \
		--license Apache-2.0 \
		$(DIST)/$(BIN)-linux-amd64=/usr/local/bin/selffork-daemon

msi-windows:
	@echo "Use WiX or candle/light to package $(DIST)/$(BIN)-windows-amd64.exe."
	@echo "Azure Trusted Signing instructions: docs/operations/install-daemon-windows.md"
