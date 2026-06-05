"""Phase 4: People-Finder + outreach drafts (see project_goal_4.8.md).

Finds contacts at a hiring company using ONLY free public sources, via a
waterfall of isolated steps. Every heavy/optional external tool is imported
lazily so a missing dependency never breaks app startup. Results carry a
confidence score so the user contacts verified leads first.

Guardrails (enforced here):
- Public data only.
- The Outreach Agent DRAFTS messages; the user reviews and sends. No auto-blast.
"""
