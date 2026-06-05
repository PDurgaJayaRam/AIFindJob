"""Per-user matching layer (Phase 2 of project_goal_4.8.md).

Matches the shared `jobs` pool against a single user's resume + target role.
This layer is pure data/AI-free on the hot path: fast, ban-free, and runs on
demand when a user logs in. It never triggers scraping.
"""
