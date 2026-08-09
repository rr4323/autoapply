# Go Modules & `go.mod`

## What it is

A **module** is Go's unit of dependency management — one `go.mod` file at the root of a directory tree declares that everything below it is one versioned, buildable unit. Before modules (pre-2019, Go < 1.11), all Go code had to live inside a single global `GOPATH` directory — modules removed that restriction; a Go project can now live anywhere on disk.

## The file itself

`backend/api/go.mod`, as of Step 1:
```go
module github.com/rr4323/autoapply/backend/api

go 1.23.2
```

- **`module <path>`** — the module's identity. Every import inside this module is written relative to this path. It doesn't have to be a real reachable URL for local development, but it should match where the code actually lives if anyone ever runs `go get` on it from outside — which is why this was set to match the repo's actual GitHub remote (`github.com/rr4323/autoapply`), not left as a placeholder.
- **`go 1.23.2`** — the minimum Go version this module requires. The compiler will refuse to build with an older toolchain.

Once you `go get` an external dependency, two more things appear:
- A **`require` block** in `go.mod`, listing the dependency and its version.
- A **`go.sum` file** — cryptographic checksums of every dependency (direct and transitive), so builds are reproducible and tampering is detectable. Think of it as Go's equivalent of `package-lock.json` (npm) or `uv.lock` (Python/uv).

## Standard use case

```bash
# once, at the start of a new Go project:
go mod init github.com/you/your-repo/path/to/module

# whenever you need an external library:
go get github.com/go-chi/chi/v5

# to clean up go.mod/go.sum after adding/removing imports by hand:
go mod tidy
```

`go mod tidy` is worth running periodically — it adds anything you're importing but haven't `go get`'d yet, and removes entries nothing imports anymore.
