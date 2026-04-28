"""Chat layer — single ChatGPT-style entry point that routes through tools.

Implements the user's emphasised pillars:
  1. 정보 홍수에서 핵심만 (한 화면 entry)
  2. 자가진화 + 자연어 주도권 (NL editor calls via tools)
  3. SNS 통합 플랫폼 + 인지 부하 0 (one chat box → all features)

The router exposes Hedwig's read/write API as OpenAI tool definitions
so the LLM can decide which tool to call when the user asks for a
briefing, a search, an algorithm tweak, or a URL summary.
"""
