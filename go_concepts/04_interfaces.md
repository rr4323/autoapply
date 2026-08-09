# Interfaces

## What it is

An interface is a set of method signatures — nothing else, no fields, no implementation. Go uses **structural typing**: a type satisfies an interface automatically just by having the right methods, with **no `implements` keyword anywhere**. This is a real difference from Java/C#, where a class has to explicitly declare which interfaces it implements.

## Verified example

```go
type Animal interface {
	Speak() string
}

type Dog struct{ Name string }

func (d Dog) Speak() string { return d.Name + " says Woof" }

type Cat struct{}

func (c Cat) Speak() string { return "Meow" }

func announce(a Animal) {
	fmt.Println(a.Speak())
}

func main() {
	announce(Dog{Name: "Rex"})
	announce(Cat{})
}
```
```
$ go run interfaces.go
Rex says Woof
Meow
```

`announce` never mentions `Dog` or `Cat` — it only knows about `Animal`. Neither `Dog` nor `Cat` declares "I am an `Animal`" anywhere; they satisfy it just by having a `Speak() string` method.

## The standard-library example that matters most here: `http.Handler`

```go
type Handler interface {
	ServeHTTP(w http.ResponseWriter, r *http.Request)
}
```
Any type — including your own structs — that has a `ServeHTTP(w, r)` method can be handed to a router as a handler. `chi` (our router, see `docs/BACKEND_BUILD_STEPS.md` Step 0) doesn't replace this interface, it builds routing/middleware on top of it.

## The idiom: keep interfaces small

Go's convention (Rob Pike: *"the bigger the interface, the weaker the abstraction"*) is to define the smallest interface that fits the immediate need, often right where it's used — not one big shared interface declared up front. See [08_testable_interfaces.md](08_testable_interfaces.md) for the concrete payoff: a one-method interface makes something trivially fakeable in a unit test.

## Standard use case

The Policy Engine (`TDD.md` §7) is the highest-stakes example in this codebase: its `Evaluate(context) -> Decision` signature should be defined against small interfaces for anything it reads (spend totals, velocity counts), so it can be unit-tested against every rule branch (below threshold, bot-check, velocity cap, spend cap, clean pass — Step 31 of the build plan) without touching a real database.
