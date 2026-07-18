# auth

Identity Service: registration, login, and refresh-token rotation. Passwords
hashed with bcrypt; access tokens are short-lived HS256 JWTs; refresh tokens
are opaque UUIDs stored in Redis (`refresh:<token> -> userId`) and rotated on
every use. Postgres holds the `users` table (self-migrating on boot for local
dev — replace with a real migration tool such as `golang-migrate` for prod).

Runs on port **8081**. See `architecture/02-microservices.md` §1.1.
