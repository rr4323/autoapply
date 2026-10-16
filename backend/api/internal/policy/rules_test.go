package policy

import (
	"path/filepath"
	"testing"
)

func TestLoadRules_ParsesTheRealConfigFile(t *testing.T) {
	// Loads the actual deployed config (../../config/policy_rules.yaml),
	// not a separate testdata copy — one file, so it can't drift out of
	// sync with what production actually reads.
	path, err := filepath.Abs("../../config/policy_rules.yaml")
	if err != nil {
		t.Fatalf("failed to resolve config path: %v", err)
	}

	rules, err := LoadRules(path)
	if err != nil {
		t.Fatalf("LoadRules failed: %v", err)
	}

	if rules.Version != "policy-rules-v1" {
		t.Errorf("Version = %v, want policy-rules-v1", rules.Version)
	}
	if rules.MinGenerateScore != 60 {
		t.Errorf("MinGenerateScore = %v, want 60", rules.MinGenerateScore)
	}
	if rules.MinAutosubmitScore != 80 {
		t.Errorf("MinAutosubmitScore = %v, want 80", rules.MinAutosubmitScore)
	}
	if !rules.RequireReviewIfBotCheck {
		t.Errorf("RequireReviewIfBotCheck = false, want true")
	}
	if rules.VelocityCapPerDay != 15 {
		t.Errorf("VelocityCapPerDay = %v, want 15", rules.VelocityCapPerDay)
	}
	wantAllowlist := []string{"greenhouse", "lever"}
	if len(rules.PlatformAllowlist) != len(wantAllowlist) {
		t.Fatalf("PlatformAllowlist = %v, want %v", rules.PlatformAllowlist, wantAllowlist)
	}
	for i, p := range wantAllowlist {
		if rules.PlatformAllowlist[i] != p {
			t.Errorf("PlatformAllowlist[%d] = %v, want %v", i, rules.PlatformAllowlist[i], p)
		}
	}
	if rules.MaxDailyGenerateSpendUSD != nil {
		t.Errorf("MaxDailyGenerateSpendUSD = %v, want nil (unset until §7.5 sets it)", *rules.MaxDailyGenerateSpendUSD)
	}
}

func TestLoadRules_MissingFileReturnsError(t *testing.T) {
	_, err := LoadRules("/nonexistent/policy_rules.yaml")
	if err == nil {
		t.Fatal("expected an error for a missing rules file, got nil")
	}
}
