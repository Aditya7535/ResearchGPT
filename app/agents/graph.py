"""
LangGraph StateGraph — ResearchGPT multi-agent pipeline.

Graph topology
--------------

    ┌─────────────┐
    │  retrieve   │  ← entry node: fetches chunks from ChromaDB
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │ structuring │  ← Agent 1: proposes thesis outline + draft sections
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  citation   │  ← Agent 2: fact-checks claims, formats bibliography
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │ formatting  │  ← Agent 3: template validation + final draft assembly
    └──────┬──────┘
           │
         END

Each node is a pure function (state_in → state_out).
Errors in any node are captured in state["errors"] and do NOT abort
subsequent nodes — the pipeline always runs to completion.

Public API
----------
    graph  = build_graph()
    result = run_pipeline(
        graph,
        document_ids=["uuid-1"],
        citation_style="apa",
        template_name="default",
        chroma_path="./chroma_data",
        n_chunks=20,
    )
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.citation import citation_agent
from app.agents.formatting import formatting_agent
from app.agents.interview import guided_interview_agent
from app.agents.state import PipelineState
from app.agents.structuring import structuring_agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retrieve node — pulls chunks from ChromaDB before agents run
# ---------------------------------------------------------------------------

def retrieve_node(state: PipelineState) -> PipelineState:
    """
    Entry node: fetch relevant chunks from ChromaDB.

    Uses ``document_ids`` from the state to filter results; if empty,
    retrieves from all documents (broad query across sections).
    """
    from app.services.ingestion.embedder import EmbeddingStore, DEFAULT_CHROMA_PATH, DEFAULT_COLLECTION

    chroma_path     = state.get("chroma_path",     DEFAULT_CHROMA_PATH)   # type: ignore[misc]
    collection_name = state.get("collection_name", DEFAULT_COLLECTION)     # type: ignore[misc]
    document_ids    = state.get("document_ids",    [])
    n_chunks        = state.get("n_chunks",        20)                     # type: ignore[misc]

    logger.info("▶  Retrieve Node — document_ids=%s, n_chunks=%d", document_ids, n_chunks)

    try:
        store = EmbeddingStore(
            persist_path=chroma_path,
            collection_name=collection_name,
        )

        all_chunks: list[dict] = []

        sections_to_query = [
            "Introduction", "Literature Review", "Methods",
            "Results", "Discussion", "Conclusion", "References",
        ]

        for section in sections_to_query:
            where: dict | None = {"section": section}
            if document_ids:
                if len(document_ids) == 1:
                    where = {"$and": [
                        {"section": section},
                        {"document_id": document_ids[0]},
                    ]}
                else:
                    where = {"$and": [
                        {"section": section},
                        {"document_id": {"$in": document_ids}},
                    ]}

            chunks = store.query(
                query_text=section,
                n_results=max(1, n_chunks // len(sections_to_query)),
                where=where,
            )
            all_chunks.extend(chunks)

        logger.info("Retrieve Node: fetched %d chunks total.", len(all_chunks))
        return {**state, "retrieved_chunks": all_chunks}

    except Exception as exc:
        logger.error("Retrieve Node error: %s", exc, exc_info=True)
        return {
            **state,
            "retrieved_chunks": [],
            "errors": state.get("errors", []) + [f"retrieve: {exc}"],
        }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    """
    Compile and return the LangGraph StateGraph.

    Returns
    -------
    CompiledGraph
        Call ``.invoke(initial_state)`` to run the pipeline.
    """
    graph = StateGraph(PipelineState)

    # Register nodes
    graph.add_node("retrieve",    retrieve_node)
    graph.add_node("structuring", structuring_agent)
    graph.add_node("interview",   guided_interview_agent)
    graph.add_node("citation",    citation_agent)
    graph.add_node("formatting",  formatting_agent)

    # Linear edges
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve",    "structuring")
    graph.add_edge("structuring", "interview")
    graph.add_edge("interview",   "citation")
    graph.add_edge("citation",    "formatting")
    graph.add_edge("formatting",  END)

    return graph.compile()


# ---------------------------------------------------------------------------
# High-level runner
# ---------------------------------------------------------------------------

def run_pipeline(
    graph: Any | None = None,
    *,
    document_ids:    list[str] | None = None,
    citation_style:  str = "apa",
    template_name:   str = "default",
    chroma_path:     str = "./chroma_data",
    collection_name: str = "researchgpt_documents",
    n_chunks:        int = 20,
    extra_state:     dict | None = None,
) -> PipelineState:
    """
    Run the full multi-agent pipeline end-to-end.

    Parameters
    ----------
    graph:
        Pre-compiled LangGraph (build_graph()). Built automatically if None.
    document_ids:
        List of ChromaDB document_id values to restrict retrieval to.
        Pass an empty list to retrieve across all ingested documents.
    citation_style:
        ``"apa"`` or ``"vancouver"``.
    template_name:
        Corresponds to a JSON file in ``app/agents/templates/``.
    chroma_path:
        Filesystem path of the ChromaDB persistent store.
    collection_name:
        ChromaDB collection name.
    n_chunks:
        Total number of chunks to retrieve (spread across sections).
    extra_state:
        Any additional keys to seed into the initial state.

    Returns
    -------
    PipelineState
        The final state dict after all three agents have run.
    """
    if graph is None:
        graph = build_graph()

    initial: PipelineState = {
        "document_ids":    document_ids or [],
        "citation_style":  citation_style,
        "template_name":   template_name,
        "chroma_path":     chroma_path,        # type: ignore[typeddict-unknown-key]
        "collection_name": collection_name,    # type: ignore[typeddict-unknown-key]
        "n_chunks":        n_chunks,           # type: ignore[typeddict-unknown-key]
        "retrieved_chunks": [],
        "errors":          [],
        "completed_agents": [],
        **(extra_state or {}),
    }

    logger.info(
        "Running ResearchGPT pipeline — style=%s, template=%s, docs=%s",
        citation_style, template_name, document_ids,
    )
    result: PipelineState = graph.invoke(initial)

    logger.info(
        "Pipeline complete — agents: %s, errors: %d",
        result.get("completed_agents", []),
        len(result.get("errors", [])),
    )
    return result
