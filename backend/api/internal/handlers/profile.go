package handlers

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/jackc/pgx/v5"

	"github.com/rr4323/autoapply/backend/api/internal/store"
)

type experienceEntry struct {
	ID        string   `json:"id"`
	Company   string   `json:"company"`
	Title     string   `json:"title"`
	StartDate string   `json:"start_date"`
	EndDate   *string  `json:"end_date"`
	Bullets   []string `json:"bullets"`
}

type profileResponse struct {
	ID              string            `json:"id"`
	BaseResumeDocID *string           `json:"base_resume_doc_id"`
	Skills          []string          `json:"skills"`
	Experience      []experienceEntry `json:"experience"`
}

type putProfileRequest struct {
	BaseResumeDocID *string           `json:"base_resume_doc_id"`
	Skills          []string          `json:"skills"`
	Experience      []experienceEntry `json:"experience"`
}

type putProfileResponse struct {
	ID         string `json:"id"`
	Reindexing bool   `json:"reindexing"`
}

type ProfileHandler struct {
	Queries *store.Queries
}

func NewProfileHandler(q *store.Queries) *ProfileHandler {
	return &ProfileHandler{Queries: q}
}

// Get handles GET /api/v1/profile.
func (h *ProfileHandler) Get(w http.ResponseWriter, r *http.Request) {
	userID, ok := currentUserID(w, r)
	if !ok {
		return
	}

	profile, err := h.Queries.GetProfileByUserID(r.Context(), userID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeJSONError(w, http.StatusNotFound, "not_found", "profile not found")
			return
		}
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to fetch profile")
		return
	}

	resp, err := toProfileResponse(profile)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to decode profile")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
}

// Put handles PUT /api/v1/profile — always upserts (migration 0006 makes
// profiles a singleton per user), whether or not the user has saved one
// before.
func (h *ProfileHandler) Put(w http.ResponseWriter, r *http.Request) {
	userID, ok := currentUserID(w, r)
	if !ok {
		return
	}

	var req putProfileRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json", "request body must be valid JSON")
		return
	}
	if req.Skills == nil {
		req.Skills = []string{}
	}
	if req.Experience == nil {
		req.Experience = []experienceEntry{}
	}

	experienceJSON, err := json.Marshal(req.Experience)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to encode experience")
		return
	}

	profile, err := h.Queries.UpsertProfileForUser(r.Context(), store.UpsertProfileForUserParams{
		UserID:          userID,
		BaseResumeDocID: req.BaseResumeDocID,
		Skills:          req.Skills,
		ExperienceJson:  experienceJSON,
	})
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "internal_error", "failed to save profile")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(putProfileResponse{
		ID: uuidString(profile.ID),
		// Re-chunking/re-embedding (TDD.md §6.1's RAG pipeline) doesn't
		// exist yet (Phase D) — honestly reporting false rather than
		// claiming a reindex that doesn't happen.
		Reindexing: false,
	})
}

func toProfileResponse(p store.Profile) (profileResponse, error) {
	experience := []experienceEntry{}
	if len(p.ExperienceJson) > 0 {
		if err := json.Unmarshal(p.ExperienceJson, &experience); err != nil {
			return profileResponse{}, err
		}
	}

	return profileResponse{
		ID:              uuidString(p.ID),
		BaseResumeDocID: p.BaseResumeDocID,
		Skills:          p.Skills,
		Experience:      experience,
	}, nil
}
