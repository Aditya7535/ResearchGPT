"""
Agents package for ResearchGPT multi-agent pipeline.

Public API
----------
    from app.agents import (
        build_graph,
        run_pipeline,
        PipelineState,
        guided_interview_agent,
        generate_interview_questions,
        process_interview_answers
    )

    graph  = build_graph()
    result = run_pipeline(graph, document_ids=["..."], citation_style="apa")
"""

from app.agents.graph import build_graph, run_pipeline
from app.agents.interview import (
    guided_interview_agent,
    generate_interview_questions,
    process_interview_answers,
    detect_thin_sections
)
from app.agents.state import PipelineState

__all__ = [
    "build_graph",
    "run_pipeline",
    "PipelineState",
    "guided_interview_agent",
    "generate_interview_questions",
    "process_interview_answers",
    "detect_thin_sections",
]
