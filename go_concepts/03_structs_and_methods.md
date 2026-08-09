# Structs & Methods

## What it is

A **struct** is a typed bundle of fields — Go's way of grouping related data (no classes, no inheritance). A **method** is a function with a *receiver* — `func (d Dog) Speak() string` — attaching it to a specific type, so values of that type can call it with `.` syntax.

## Verified example

```go
type Dog struct {
	Name string
}

func (d Dog) Speak() string {
	return d.Name + " says Woof"
}
```

```
rex := Dog{Name: "Rex"}
fmt.Println(rex.Speak()) // "Rex says Woof"
```

`(d Dog)` is the receiver. Read it as "this function is attached to the `Dog` type, and inside the function body, `d` refers to the specific `Dog` value it was called on" — equivalent in spirit to `self`/`this` in other languages, just declared explicitly rather than implicit.

## Value receivers vs. pointer receivers (the thing to know exists)

`func (d Dog) Speak() string` takes `d` **by value** — the method gets a copy, can't mutate the original. `func (d *Dog) Rename(n string) { d.Name = n }` takes `d` **by pointer** — the method can mutate the actual struct the caller has. Rule of thumb you'll see constantly in this codebase: if a method needs to modify the struct, or the struct is large enough that copying it is wasteful, use a pointer receiver (`*Dog`). Read-only methods on small structs are fine as value receivers. You'll see this concretely once handlers hold a `*Server` (pointer — one shared instance, config/DB pool inside it) rather than `Server`.

## Standard use case

Every non-trivial value in the Go control plane is a struct: `Config` (env-loaded settings), `Decision` (Policy Engine's `{action, reasons}` output, `TDD.md` §7.2), `Application` (mirrors the `applications` table, §8). Methods attached to these — `(c Config) DatabaseURL() string`, `(d Decision) IsTerminal() bool` — are how behavior stays close to the data it operates on, without a class hierarchy.
