"""Phase 3: per-job ATS resume tailoring (see project_goal_4.8.md).

Generates an ATS-friendly resume tailored to a specific pool job for a logged-in
user. Uses the async AI client when available, and falls back to a deterministic
template when no AI key is configured, so the feature works with zero keys.
"""
