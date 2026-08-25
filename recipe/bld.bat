@echo off
setlocal EnableDelayedExpansion

REM Force pure-Go build (no CGO) — matches upstream release defaults.
set CGO_ENABLED=0
REM Reproducible build: don't stamp per-machine VCS info.
set GOFLAGS=-buildvcs=false

REM 1. Build the embedded Svelte UI (Vite output -> internal/server/ui_dist/,
REM    embedded into the Go binary via the embed_ui build tag).
pushd ui
call npm ci --no-audit --no-fund
if errorlevel 1 exit 1
call npm run build
if errorlevel 1 exit 1
popd

REM 2. Compile the Go binary; ldflags stamp version + commit surfaced by
REM    `llama-swap --version`. main.date is intentionally NOT stamped — we
REM    aren't upstream's release build (Stan Seibert review, PKG-17553).
go build ^
    -tags embed_ui ^
    -ldflags "-s -w -X main.version=%LLAMA_SWAP_VERSION% -X main.commit=%LLAMA_SWAP_COMMIT%" ^
    -v -o "%PREFIX%\Library\bin\llama-swap.exe" ^
    .
if errorlevel 1 exit 1

REM 3. Collect third-party Go module licenses for about.license_file.
go-licenses save . --save_path=library_licenses
if errorlevel 1 exit 1
