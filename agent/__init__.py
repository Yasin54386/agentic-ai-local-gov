"""Agent layer over the public data repository.

A backend-agnostic agent whose tools are wired into the harvested NT/Darwin data
(the ingestion engine's catalog + downloaded records). Driven by a hosted
"AI Powered" model through agent.llm, which is the single budget-gated choke
point. This is Layer 4 (Orchestration) reasoning over Layer 3 (Data Fabric),
as described in docs/01.

The repository/tools here are dependency-free and verifiable without any model,
so the data layer can be tested on its own before the AI is attached.
"""

__version__ = "0.1.0"
