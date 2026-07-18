package handlers

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"golang.org/x/crypto/bcrypt"

	"github.com/openhealthagents/ai-rxos/services/auth/internal/config"
	"github.com/openhealthagents/ai-rxos/services/auth/internal/store"
)

type AuthHandler struct {
	DB    *store.Postgres
	Redis *redis.Client
	Cfg   config.Config
}

type registerRequest struct {
	Email          string `json:"email"`
	Password       string `json:"password"`
	DisplayName    string `json:"displayName"`
	OrganizationID string `json:"organizationId"`
}

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type tokenResponse struct {
	AccessToken  string `json:"accessToken"`
	RefreshToken string `json:"refreshToken"`
	ExpiresIn    int    `json:"expiresIn"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]string{"code": code, "message": message})
}

func (h *AuthHandler) Register(w http.ResponseWriter, r *http.Request) {
	var req registerRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}
	if req.Email == "" || len(req.Password) < 8 {
		writeErr(w, http.StatusBadRequest, "invalid_input", "email required, password must be >= 8 chars")
		return
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "hash_failed", "could not hash password")
		return
	}

	orgID, err := uuid.Parse(req.OrganizationID)
	if err != nil {
		orgID = uuid.New()
	}

	user := store.User{
		ID:             uuid.New(),
		Email:          req.Email,
		PasswordHash:   string(hash),
		DisplayName:    req.DisplayName,
		OrganizationID: orgID,
		Roles:          []string{"member"},
	}

	if err := h.DB.CreateUser(r.Context(), user); err != nil {
		if err == store.ErrDuplicate {
			writeErr(w, http.StatusConflict, "email_taken", "an account with this email already exists")
			return
		}
		writeErr(w, http.StatusInternalServerError, "create_failed", err.Error())
		return
	}

	h.issueTokens(w, r.Context(), user)
}

func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	var req loginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}

	user, err := h.DB.GetUserByEmail(r.Context(), req.Email)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "invalid_credentials", "email or password is incorrect")
		return
	}
	if bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)) != nil {
		writeErr(w, http.StatusUnauthorized, "invalid_credentials", "email or password is incorrect")
		return
	}

	h.issueTokens(w, r.Context(), user)
}

func (h *AuthHandler) Refresh(w http.ResponseWriter, r *http.Request) {
	var body struct {
		RefreshToken string `json:"refreshToken"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid_body", err.Error())
		return
	}

	userID, err := h.Redis.Get(r.Context(), "refresh:"+body.RefreshToken).Result()
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "invalid_refresh_token", "refresh token is invalid or expired")
		return
	}

	uid, err := uuid.Parse(userID)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "invalid_refresh_token", "malformed subject")
		return
	}

	// Rotate: invalidate the used refresh token before issuing a new pair.
	h.Redis.Del(r.Context(), "refresh:"+body.RefreshToken)
	h.issueTokens(w, r.Context(), store.User{ID: uid})
}

func (h *AuthHandler) issueTokens(w http.ResponseWriter, ctx context.Context, user store.User) {
	now := time.Now()
	claims := jwt.MapClaims{
		"sub": user.ID.String(),
		"iat": now.Unix(),
		"exp": now.Add(h.Cfg.AccessTokenTTL).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	accessToken, err := token.SignedString([]byte(h.Cfg.JWTSecret))
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "token_sign_failed", err.Error())
		return
	}

	refreshToken := uuid.NewString()
	if err := h.Redis.Set(ctx, "refresh:"+refreshToken, user.ID.String(), h.Cfg.RefreshTokenTTL).Err(); err != nil {
		writeErr(w, http.StatusInternalServerError, "refresh_store_failed", err.Error())
		return
	}

	writeJSON(w, http.StatusOK, tokenResponse{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		ExpiresIn:    int(h.Cfg.AccessTokenTTL.Seconds()),
	})
}
