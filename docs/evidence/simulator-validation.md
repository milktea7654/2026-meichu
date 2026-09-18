# Browser simulator validation — 2026-09-19

- Python integration suite: **64 passed in 2.82s** with loopback networking enabled.
- Browser smoke test: exploration → NPC encounter → accept → inspect → return charm;
  player gains 50 XP, quest is COMPLETED in the actual SQLite table.
- Reload preserves the completed quest and player XP.
- Database and generator tabs display the actual backend snapshot.
- 390px mobile viewport has no document horizontal overflow.
- No browser JavaScript errors during the tested workflow.
- Test world uses a temporary directory; the visible simulator remains at an
  available traveler encounter, with no quest rewards already claimed.
- Screenshots: simulator-game.png, simulator-database.png,
  simulator-generator.png, simulator-mobile.png.

The simulator's GPS, camera observations and drawn map are synthetic inputs.
World, H3, event selection and SQLite are the production Python modules.
The Chinese event descriptions are templates, not an LLM generation result.

Follow-up consistency fixes:
- Core and simulator now share `World.exploration_components()`; debug scores,
  weights, thresholds and quest rewards come from actual configuration/state.
- GPS-disconnected zone selection preserves the last valid position and progress.
- A restored event's generator explanation uses the event's persisted context,
  not a newly inferred generic context. The saved observation is explicitly
  labelled as the last saved frame before creation, not necessarily the trigger frame.
- Full regression after shared-score/disconnect changes: 66 passed in 2.67s.
- Simulator-specific regression including restored generator context: 7 passed.
