# JWTs — Stateless Auth Tokens

## What it is

A JWT (JSON Web Token) is three base64url-encoded parts joined by dots: `header.payload.signature`. The header names the algorithm, the payload is a JSON claims object (who this token is for, when it expires), and the signature is an HMAC (or RSA/ECDSA) of `header.payload`, computed with a server-only secret. Anyone can *decode* the payload (it's just base64, not encryption) — the point of the signature is that nobody *without the secret* can produce a payload that verifies, so a server can trust a token's claims without a database lookup or server-side session store. That's the whole tradeoff versus session cookies: no shared session state to look up (good for horizontally-scaled stateless APIs), but also no way to revoke one token early short of shortening its expiry or checking a deny-list — there's no session row to delete.

## Verified example

```go
secret := []byte("demo-secret")

claims := jwt.RegisteredClaims{
	Subject:   "user-42",
	IssuedAt:  jwt.NewNumericDate(time.Now()),
	ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
}
token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
signed, _ := token.SignedString(secret)
fmt.Println("signed token:", signed)

parsed, err := jwt.ParseWithClaims(signed, &jwt.RegisteredClaims{}, func(t *jwt.Token) (interface{}, error) {
	return secret, nil
})
fmt.Println("parse with correct secret, valid:", parsed.Valid, "err:", err)
got := parsed.Claims.(*jwt.RegisteredClaims)
fmt.Println("subject recovered:", got.Subject)

_, err = jwt.ParseWithClaims(signed, &jwt.RegisteredClaims{}, func(t *jwt.Token) (interface{}, error) {
	return []byte("wrong-secret"), nil
})
fmt.Println("parse with wrong secret, err:", err)
```
```
signed token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTQyIiwiZXhwIjoxNzg5MjAxODg5LCJpYXQiOjE3ODkxOTgyODl9.FeOlZAzMP3SOxWtRQdIdYnOX_5zZBmq9A7RqLOTAo8M
parse with correct secret, valid: true err: <nil>
subject recovered: user-42
parse with wrong secret, err: token signature is invalid: signature is invalid
parse tampered token, err: token signature is invalid: signature is invalid
```

## Why `ParseWithClaims` takes a callback, not just the secret

`func(t *jwt.Token) (interface{}, error)` looks like overkill for one static secret, but it exists so the *token itself* (specifically its unverified header) can decide which key/algorithm to use — e.g. picking between multiple signing keys during a rotation, or (security-critically) rejecting an unexpected algorithm. `internal/auth.ParseToken` does exactly that:

```go
func(t *jwt.Token) (interface{}, error) {
	if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
		return nil, ErrInvalidToken
	}
	return secret, nil
}
```
That `SigningMethodHMAC` type-assertion blocks a real attack class ("alg confusion"): a forged token that sets its header to `"alg": "none"` or swaps in an asymmetric algorithm, hoping the verifier will use the wrong key material to check it. Always pin the expected algorithm family server-side — never trust the token's own header to tell you how to verify itself.

## Standard use case

`internal/auth/jwt.go`'s `IssueToken`/`ParseToken`, called from `AuthHandler` (issue, on signup/login) and `middleware.JWTAuth` (parse, on every authenticated request) — P1 of the SaaS-pivot plan. The subject claim carries the user id straight into the same `context.Value` slot the old stub (`middleware.UserContext`) used, so every handler downstream (`currentUserID` in `internal/handlers/applications.go`) needed zero changes.
