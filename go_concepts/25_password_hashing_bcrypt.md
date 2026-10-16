# Password Hashing with bcrypt

## What it is

You never store a plaintext password, and you never store a plain hash either (`sha256(password)` is crackable at billions of guesses/second on commodity hardware — no per-password cost). `bcrypt` is a hashing algorithm designed to be *slow* and to bake a random per-call **salt** into its own output, so two hashes of the same password never match each other, and brute-forcing many accounts at once buys an attacker nothing (each hash costs the same work regardless of how many you have).

## Verified example

```go
hash1, _ := bcrypt.GenerateFromPassword([]byte("hunter2"), bcrypt.DefaultCost)
hash2, _ := bcrypt.GenerateFromPassword([]byte("hunter2"), bcrypt.DefaultCost)
fmt.Println(string(hash1))
fmt.Println(string(hash2))
fmt.Println("hashes equal?", string(hash1) == string(hash2))

err := bcrypt.CompareHashAndPassword(hash1, []byte("hunter2"))
fmt.Println("correct password check error:", err)

err = bcrypt.CompareHashAndPassword(hash1, []byte("wrong-password"))
fmt.Println("wrong password check error:", err)
```
```
$2a$10$YAFlGsW2.nqpyqotw5ps9uO.CG6NgiCtoHupgPDEHEAgu95GW9BQ.
$2a$10$xDo5nxarkCTZV1DzYRo4bepmuU4hegpJ3KgPUQnnJXdCXza6l0vNO
hashes equal? false
correct password check error: <nil>
wrong password check error: crypto/bcrypt: hashedPassword is not the hash of the given password
```

## Reading the hash string itself

`$2a$10$YAFlGsW2.nqpyqotw5ps9uO.CG6NgiCtoHupgPDEHEAgu95GW9BQ.` isn't opaque noise — it's `$<algorithm version>$<cost>$<22-char salt><31-char hash>`. The **cost** (`10` here, `bcrypt.DefaultCost`) is a power-of-two work factor: each +1 roughly doubles the time to compute one hash. That's the whole security model in one field — hashing is deliberately expensive so guessing is expensive, and the cost travels with the hash itself, so you can raise it in future signups without breaking verification of old ones (`CompareHashAndPassword` reads the cost back out of the stored hash, it isn't a separate config value you have to keep in sync).

`CompareHashAndPassword` — never `==` on two hashes, and never re-hash the input and compare strings — is the only correct way to check a password, precisely because of the random salt: hashing the same password twice, on purpose, never produces the same output.

## Standard use case

`internal/auth/password.go`'s `HashPassword`/`CheckPassword` — called from `AuthHandler.Signup` (hash, store in `users.password_hash`) and `AuthHandler.Login` (compare against the stored hash). This is P1 of the SaaS-pivot plan replacing the Phase 1 stub user (`middleware.DefaultStubUserID`) with real accounts.
