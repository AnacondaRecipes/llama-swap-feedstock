#!/bin/bash
set -euxo pipefail

# Force pure-Go build (no CGO) — matches upstream release-build defaults and
# avoids a hard dep on the C toolchain at runtime.
export CGO_ENABLED=0
# Reproducible build: don't stamp per-machine VCS info into the binary.
export GOFLAGS="-buildvcs=false"

# 1. Build the embedded Svelte UI. Output lands in internal/server/ui_dist/
#    which the Go source embeds when the embed_ui build tag is set (see
#    internal/server/embed.go).
pushd ui
npm ci --no-audit --no-fund
npm run build
popd

# 2. Compile the Go binary. -ldflags "-s -w" strips symbols; the -X flags
#    stamp main.version / main.commit / main.date so `llama-swap --version`
#    matches upstream release output.
go build \
    -tags embed_ui \
    -ldflags "-s -w -X main.version=${LLAMA_SWAP_VERSION} -X main.commit=${LLAMA_SWAP_COMMIT} -X main.date=${LLAMA_SWAP_DATE}" \
    -v -o "${PREFIX}/bin/llama-swap" \
    .

# 3. Collect third-party Go module licenses into library_licenses/ so the
#    about.license_file entry ships them alongside LICENSE.md.
go-licenses save . --save_path=library_licenses

# 4. Clean up GOPATH to keep the build sandbox small.
chmod -R u+w "$(go env GOPATH)" && rm -rf "$(go env GOPATH)"
