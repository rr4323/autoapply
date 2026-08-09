# Packages & Imports

## What it is

Every `.go` file's first line declares which **package** it belongs to. A package is Go's unit of code organization — one directory = one package. All `.go` files in the same directory must declare the same package name, or the compiler rejects it.

## Rule 1 — `package main` is special

It's the signal "this package produces a runnable executable," and it requires exactly one `func main()` — no parameters, no return value, the actual entry point. Every other package name is a *library* package: importable, but not runnable on its own.

## Rule 2 — the import path is built from the module path

Verified example — a module `pkgdemo` with a local `stringutil` package:

```go
// stringutil/reverse.go
package stringutil

func Reverse(s string) string {
	runes := []rune(s)
	for i, j := 0, len(runes)-1; i < j; i, j = i+1, j-1 {
		runes[i], runes[j] = runes[j], runes[i]
	}
	return string(runes)
}
```

```go
// main.go
package main

import (
	"fmt"

	"pkgdemo/stringutil"
)

func main() {
	fmt.Println(stringutil.Reverse("agentos"))
}
```

```
$ go run main.go
sotnega
```

The import path `"pkgdemo/stringutil"` is literally `<module path>/<directory path>` — nothing magic, no separate package registry to configure. This is exactly why `backend/api`'s module was named `github.com/rr4323/autoapply/backend/api`: a future `internal/policy` package there will be imported as `github.com/rr4323/autoapply/backend/api/internal/policy`.

## Rule 3 — `internal/` is compiler-enforced privacy

Any package under a directory named `internal/` can only be imported by code inside the module tree *above* that `internal/` directory — the Go compiler enforces this, it's not a convention you have to remember to respect. This is why `backend/api/internal/` exists: nothing outside `backend/api` should ever import its handler/policy-engine internals directly (per `TDD.md` §1, agents only talk to the control plane over the message bus, never by importing its code).

## Rule 4 — an unused import is a compile error, not a warning

Verified:
```go
package main

import (
	"fmt"
	"os"
)

func main() {
	fmt.Println("hello")
}
```
```
$ go run unused.go
./unused.go:5:2: "os" imported and not used
```
Go refuses to even compile. This is deliberate — the language designers wanted zero dead-weight imports as a hard rule, not a linter suggestion. `goimports` (used by our `.golangci.yml` formatter, see `docs/BACKEND_BUILD_STEPS.md` Step 1) auto-adds/removes imports so you're rarely fighting this by hand.

## Standard use case

Any time you split code into a new file that needs its own conceptual boundary — a `policy` package, a `store` package, an `internal/` package nothing outside the service should touch — you're using this system. In `backend/agents` (Python), the equivalent decision was one subpackage per agent (`scraper/`, `retriever/`, ...) — same instinct, different language mechanism.
