"""On-Demand Q&A — 4-tier temporal lattice's conversational layer.

Users ask questions → Hedwig answers from collected signals (RAG over SQLite)
with fallback to live search (exa / r.jina.ai). Accept/reject events feed
into the Triple-Input evolution pipeline as semi-explicit feedback.

See docs/VISION_v3.md sections 6-7 for the architecture.
Phase 1 scope:
  - router.py : dispatch to RAG vs. live search vs. hybrid
  - retrieval.py : SQLite FTS over collected signals
  - feedback.py : accept/reject events → evolution_signal table

This package is a Phase 1 scaffold. Core logic lands with the /ask endpoint.
"""
