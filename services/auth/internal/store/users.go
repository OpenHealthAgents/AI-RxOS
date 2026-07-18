package store

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

var ErrNotFound = errors.New("user not found")
var ErrDuplicate = errors.New("email already registered")

type User struct {
	ID             uuid.UUID
	Email          string
	PasswordHash   string
	DisplayName    string
	OrganizationID uuid.UUID
	Roles          []string
}

func (p *Postgres) CreateUser(ctx context.Context, u User) error {
	_, err := p.Pool.Exec(ctx,
		`INSERT INTO users (id, email, password_hash, display_name, organization_id, roles)
		 VALUES ($1, $2, $3, $4, $5, $6)`,
		u.ID, u.Email, u.PasswordHash, u.DisplayName, u.OrganizationID, u.Roles,
	)
	if err != nil {
		if pgErrIsUniqueViolation(err) {
			return ErrDuplicate
		}
		return err
	}
	return nil
}

func (p *Postgres) GetUserByEmail(ctx context.Context, email string) (User, error) {
	var u User
	err := p.Pool.QueryRow(ctx,
		`SELECT id, email, password_hash, display_name, organization_id, roles
		 FROM users WHERE email = $1`, email,
	).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.DisplayName, &u.OrganizationID, &u.Roles)
	if errors.Is(err, pgx.ErrNoRows) {
		return User{}, ErrNotFound
	}
	return u, err
}

func pgErrIsUniqueViolation(err error) bool {
	var pgErr interface{ SQLState() string }
	if errors.As(err, &pgErr) {
		return pgErr.SQLState() == "23505"
	}
	return false
}
