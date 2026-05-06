package main

import (
	"fmt"
	"os"
	"strings"
)

const lazyCatOIDCSource = `package handler

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
	"unicode"

	"github.com/jackc/pgx/v5/pgtype"
	"github.com/multica-ai/multica/server/internal/auth"
	"github.com/multica-ai/multica/server/internal/logger"
	db "github.com/multica-ai/multica/server/pkg/db/generated"
)

type lazyCatOIDCTokenResponse struct {
	AccessToken string ` + "`json:\"access_token\"`" + `
	IDToken     string ` + "`json:\"id_token\"`" + `
	TokenType   string ` + "`json:\"token_type\"`" + `
}

type lazyCatOIDCUserInfo struct {
	Sub               string   ` + "`json:\"sub\"`" + `
	Email             string   ` + "`json:\"email\"`" + `
	Name              string   ` + "`json:\"name\"`" + `
	PreferredUsername string   ` + "`json:\"preferred_username\"`" + `
	Picture           string   ` + "`json:\"picture\"`" + `
	Groups            []string ` + "`json:\"groups\"`" + `
}

func firstLazyCatEnv(names ...string) string {
	for _, name := range names {
		if value := strings.TrimSpace(os.Getenv(name)); value != "" {
			return value
		}
	}
	return ""
}

func firstLazyCatString(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func lazyCatOIDCConfigured() bool {
	return firstLazyCatEnv("OIDC_CLIENT_ID", "LAZYCAT_AUTH_OIDC_CLIENT_ID") != "" &&
		firstLazyCatEnv("OIDC_CLIENT_SECRET", "LAZYCAT_AUTH_OIDC_CLIENT_SECRET") != "" &&
		firstLazyCatEnv("OIDC_AUTH_URI", "LAZYCAT_AUTH_OIDC_AUTH_URI") != "" &&
		firstLazyCatEnv("OIDC_TOKEN_URI", "LAZYCAT_AUTH_OIDC_TOKEN_URI") != "" &&
		firstLazyCatEnv("OIDC_USERINFO_URI", "LAZYCAT_AUTH_OIDC_USERINFO_URI") != ""
}

func lazyCatOIDCRedirectURI(r *http.Request) string {
	if configured := firstLazyCatEnv("OIDC_REDIRECT_URI", "GOOGLE_REDIRECT_URI"); configured != "" {
		return configured
	}
	proto := strings.TrimSpace(r.Header.Get("X-Forwarded-Proto"))
	if proto == "" {
		proto = "https"
	}
	host := strings.TrimSpace(r.Host)
	if host == "" {
		host = strings.TrimSpace(r.Header.Get("Host"))
	}
	return proto + "://" + host + "/auth/callback"
}

func normalizeLazyCatEmail(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	if value == "" {
		return ""
	}
	if strings.Contains(value, "@") {
		return value
	}
	var b strings.Builder
	for _, r := range value {
		switch {
		case unicode.IsLetter(r) || unicode.IsDigit(r):
			b.WriteRune(unicode.ToLower(r))
		case r == '.' || r == '_' || r == '-':
			b.WriteRune(r)
		default:
			b.WriteByte('-')
		}
	}
	local := strings.Trim(b.String(), ".-_")
	if local == "" {
		return ""
	}
	return local + "@lazycat.local"
}

func (h *Handler) LazyCatOIDCStart(w http.ResponseWriter, r *http.Request) {
	if !lazyCatOIDCConfigured() {
		writeError(w, http.StatusServiceUnavailable, "LazyCat OIDC is not configured")
		return
	}

	authURI := firstLazyCatEnv("OIDC_AUTH_URI", "LAZYCAT_AUTH_OIDC_AUTH_URI")
	params := url.Values{
		"client_id":     {firstLazyCatEnv("OIDC_CLIENT_ID", "LAZYCAT_AUTH_OIDC_CLIENT_ID")},
		"redirect_uri":  {lazyCatOIDCRedirectURI(r)},
		"response_type": {"code"},
		"scope":         {"openid email profile"},
	}
	if state := strings.TrimSpace(r.URL.Query().Get("state")); state != "" {
		params.Set("state", state)
	}

	separator := "?"
	if strings.Contains(authURI, "?") {
		separator = "&"
	}
	http.Redirect(w, r, authURI+separator+params.Encode(), http.StatusFound)
}

func (h *Handler) LazyCatOIDCLogin(w http.ResponseWriter, r *http.Request, req GoogleLoginRequest) {
	clientID := firstLazyCatEnv("OIDC_CLIENT_ID", "LAZYCAT_AUTH_OIDC_CLIENT_ID")
	clientSecret := firstLazyCatEnv("OIDC_CLIENT_SECRET", "LAZYCAT_AUTH_OIDC_CLIENT_SECRET")
	tokenURI := firstLazyCatEnv("OIDC_TOKEN_URI", "LAZYCAT_AUTH_OIDC_TOKEN_URI")
	userInfoURI := firstLazyCatEnv("OIDC_USERINFO_URI", "LAZYCAT_AUTH_OIDC_USERINFO_URI")
	if clientID == "" || clientSecret == "" || tokenURI == "" || userInfoURI == "" {
		writeError(w, http.StatusServiceUnavailable, "LazyCat OIDC is not configured")
		return
	}

	redirectURI := req.RedirectURI
	if redirectURI == "" {
		redirectURI = lazyCatOIDCRedirectURI(r)
	}

	tokenResp, err := http.PostForm(tokenURI, url.Values{
		"code":          {req.Code},
		"client_id":     {clientID},
		"client_secret": {clientSecret},
		"redirect_uri":  {redirectURI},
		"grant_type":    {"authorization_code"},
	})
	if err != nil {
		slog.Error("lazycat oidc token exchange failed", "error", err)
		writeError(w, http.StatusBadGateway, "failed to exchange code with LazyCat OIDC")
		return
	}
	defer tokenResp.Body.Close()

	tokenBody, err := io.ReadAll(tokenResp.Body)
	if err != nil {
		writeError(w, http.StatusBadGateway, "failed to read LazyCat OIDC token response")
		return
	}
	if tokenResp.StatusCode != http.StatusOK {
		slog.Error("lazycat oidc token exchange returned error", "status", tokenResp.StatusCode, "body", string(tokenBody))
		writeError(w, http.StatusBadRequest, "failed to exchange code with LazyCat OIDC")
		return
	}

	var oidcToken lazyCatOIDCTokenResponse
	if err := json.Unmarshal(tokenBody, &oidcToken); err != nil {
		writeError(w, http.StatusBadGateway, "failed to parse LazyCat OIDC token response")
		return
	}
	if oidcToken.AccessToken == "" {
		writeError(w, http.StatusBadGateway, "LazyCat OIDC token response has no access token")
		return
	}

	userInfoReq, err := http.NewRequestWithContext(r.Context(), http.MethodGet, userInfoURI, nil)
	if err != nil {
		slog.Error("failed to create LazyCat OIDC userinfo request", "error", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}
	userInfoReq.Header.Set("Authorization", "Bearer "+oidcToken.AccessToken)

	userInfoResp, err := http.DefaultClient.Do(userInfoReq)
	if err != nil {
		slog.Error("lazycat oidc userinfo fetch failed", "error", err)
		writeError(w, http.StatusBadGateway, "failed to fetch LazyCat user info")
		return
	}
	defer userInfoResp.Body.Close()
	if userInfoResp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(userInfoResp.Body)
		slog.Error("lazycat oidc userinfo returned error", "status", userInfoResp.StatusCode, "body", string(body))
		writeError(w, http.StatusBadGateway, "failed to fetch LazyCat user info")
		return
	}

	var oidcUser lazyCatOIDCUserInfo
	if err := json.NewDecoder(userInfoResp.Body).Decode(&oidcUser); err != nil {
		writeError(w, http.StatusBadGateway, "failed to parse LazyCat user info")
		return
	}

	email := normalizeLazyCatEmail(firstLazyCatString(oidcUser.Email, oidcUser.PreferredUsername, oidcUser.Sub))
	if email == "" {
		writeError(w, http.StatusBadRequest, "LazyCat account has no usable identity")
		return
	}
	displayName := firstLazyCatString(oidcUser.Name, oidcUser.PreferredUsername, oidcUser.Email, oidcUser.Sub)

	user, err := h.findOrCreateUser(r.Context(), email)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to create user")
		return
	}

	needsUpdate := false
	newName := user.Name
	newAvatar := user.AvatarUrl
	if displayName != "" && user.Name == strings.Split(email, "@")[0] {
		newName = displayName
		needsUpdate = true
	}
	if oidcUser.Picture != "" && !user.AvatarUrl.Valid {
		newAvatar = pgtype.Text{String: oidcUser.Picture, Valid: true}
		needsUpdate = true
	}
	if needsUpdate {
		updated, err := h.Queries.UpdateUser(r.Context(), db.UpdateUserParams{
			ID:        user.ID,
			Name:      newName,
			AvatarUrl: newAvatar,
		})
		if err == nil {
			user = updated
		}
	}

	tokenString, err := h.issueJWT(user)
	if err != nil {
		slog.Warn("lazycat oidc login failed", append(logger.RequestAttrs(r), "error", err, "email", email)...)
		writeError(w, http.StatusInternalServerError, "failed to generate token")
		return
	}

	if err := auth.SetAuthCookies(w, tokenString); err != nil {
		slog.Warn("failed to set auth cookies", "error", err)
	}
	if h.CFSigner != nil {
		for _, cookie := range h.CFSigner.SignedCookies(time.Now().Add(72 * time.Hour)) {
			http.SetCookie(w, cookie)
		}
	}

	slog.Info("user logged in via lazycat oidc", append(logger.RequestAttrs(r), "user_id", uuidToString(user.ID), "email", user.Email)...)
	writeJSON(w, http.StatusOK, LoginResponse{
		Token: tokenString,
		User:  userToResponse(user),
	})
}
`

func main() {
	path := "server/cmd/server/router.go"
	source, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}

	before := `	r.Get("/ws", func(w http.ResponseWriter, r *http.Request) {
		realtime.HandleWebSocket(hub, mc, pr, slugResolver, w, r)
	})`

	after := `	r.Get("/ws", func(w http.ResponseWriter, r *http.Request) {
		realtime.HandleWebSocket(hub, mc, pr, slugResolver, w, r)
	})
	r.Get("/ws/", func(w http.ResponseWriter, r *http.Request) {
		realtime.HandleWebSocket(hub, mc, pr, slugResolver, w, r)
	})`

	text := string(source)
	if !strings.Contains(text, before) {
		panic("expected WebSocket route block not found")
	}
	if err := os.WriteFile(path, []byte(strings.Replace(text, before, after, 1)), 0o644); err != nil {
		panic(err)
	}
	fmt.Println("Patched backend WebSocket route to also accept /ws/")

	oidcRouteBefore := `	// Auth (public)
	r.Post("/auth/send-code", h.SendCode)`
	oidcRouteAfter := `	// Auth (public)
	r.Get("/auth/oidc/start", h.LazyCatOIDCStart)
	r.Post("/auth/send-code", h.SendCode)`

	source, err = os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	text = string(source)
	if !strings.Contains(text, oidcRouteBefore) {
		panic("expected auth route block not found")
	}
	if err := os.WriteFile(path, []byte(strings.Replace(text, oidcRouteBefore, oidcRouteAfter, 1)), 0o644); err != nil {
		panic(err)
	}
	fmt.Println("Patched backend auth routes to expose LazyCat OIDC start endpoint")

	authPath := "server/internal/handler/auth.go"
	source, err = os.ReadFile(authPath)
	if err != nil {
		panic(err)
	}
	authBefore := `	if req.Code == "" {
		writeError(w, http.StatusBadRequest, "code is required")
		return
	}

	clientID := os.Getenv("GOOGLE_CLIENT_ID")`
	authAfter := `	if req.Code == "" {
		writeError(w, http.StatusBadRequest, "code is required")
		return
	}

	if lazyCatOIDCConfigured() {
		h.LazyCatOIDCLogin(w, r, req)
		return
	}

	clientID := os.Getenv("GOOGLE_CLIENT_ID")`
	text = string(source)
	if !strings.Contains(text, authBefore) {
		panic("expected GoogleLogin code validation block not found")
	}
	if err := os.WriteFile(authPath, []byte(strings.Replace(text, authBefore, authAfter, 1)), 0o644); err != nil {
		panic(err)
	}
	if err := os.WriteFile("server/internal/handler/lazycat_oidc.go", []byte(lazyCatOIDCSource), 0o644); err != nil {
		panic(err)
	}
	fmt.Println("Patched backend Google login to exchange LazyCat OIDC codes")
}
