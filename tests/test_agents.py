"""
Unit tests for the multi-agent LangGraph pipeline.

Test classes
------------
TestStructuringAgent   – grounding rule, no-chunk fallback, JSON parse, validation
TestCitationAgent      – claim flagging, bibliography integration, empty draft
TestFormattingAgent    – template loading, issue detection, draft assembly
TestGraphWiring        – build_graph() smoke test, retrieve_node mock
TestRunPipeline        – end-to-end run with all agents mocked

All LLM calls, ChromaDB calls, and file I/O are mocked — fully offline.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Structuring Agent tests
# ---------------------------------------------------------------------------
from app.agents.structuring import (
    THESIS_SECTIONS,
    _build_chunk_context,
    _parse_llm_json,
    _validate_structure,
    structuring_agent,
)
from app.agents.state import PipelineState


class TestStructuringAgentHelpers(unittest.TestCase):

    def test_build_chunk_context_formats_correctly(self):
        chunks = [
            {"text": "Some intro text.", "metadata": {"source_filename": "paper.pdf", "section": "Introduction"}},
            {"text": "Methods detail.",  "metadata": {"source_filename": "paper.pdf", "section": "Methods"}},
        ]
        ctx = _build_chunk_context(chunks)
        self.assertIn("[CHUNK 1]", ctx)
        self.assertIn("paper.pdf", ctx)
        self.assertIn("Some intro text.", ctx)

    def test_parse_llm_json_plain(self):
        raw = '{"outline": {"Introduction": "desc"}, "draft_sections": {"Introduction": "text"}}'
        result = _parse_llm_json(raw)
        self.assertIn("outline", result)

    def test_parse_llm_json_strips_fences(self):
        raw = "```json\n{\"outline\": {}, \"draft_sections\": {}}\n```"
        result = _parse_llm_json(raw)
        self.assertIsInstance(result, dict)

    def test_parse_llm_json_finds_embedded_json(self):
        raw = "Here is your answer:\n{\"outline\": {}, \"draft_sections\": {}}\nThat is all."
        result = _parse_llm_json(raw)
        self.assertIn("outline", result)

    def test_validate_structure_fills_missing_sections(self):
        data = {"outline": {}, "draft_sections": {}}
        outline, drafts = _validate_structure(data)
        for section in THESIS_SECTIONS:
            self.assertIn(section, outline)
            self.assertIn(section, drafts)
            self.assertEqual(drafts[section], "[NO_CONTENT]")

    def test_validate_structure_preserves_existing(self):
        data = {
            "outline":        {"Introduction": "Research question overview."},
            "draft_sections": {"Introduction": "This paper explores..."},
        }
        outline, drafts = _validate_structure(data)
        self.assertEqual(outline["Introduction"], "Research question overview.")
        self.assertEqual(drafts["Introduction"], "This paper explores...")


class TestStructuringAgentNode(unittest.TestCase):

    def _llm_response(self, outline: dict, drafts: dict):
        """Build a mock LLM that returns a valid JSON response."""
        mock_llm  = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = json.dumps({"outline": outline, "draft_sections": drafts})
        mock_llm.invoke.return_value = mock_resp
        return mock_llm

    @patch("app.agents.structuring.get_llm")
    def test_populates_outline_and_drafts(self, mock_get_llm):
        outline = {"Introduction": "Introduces the topic."}
        drafts  = {"Introduction": "This paper investigates citation systems."}
        mock_get_llm.return_value = self._llm_response(outline, drafts)

        state: PipelineState = {
            "retrieved_chunks": [
                {"text": "Citation systems are important.", "metadata": {"source_filename": "a.pdf", "section": "Introduction"}}
            ],
            "citation_style": "apa",
        }
        result = structuring_agent(state)

        self.assertEqual(result["structuring_status"], "ok")
        self.assertIn("Introduction", result["outline"])
        self.assertIn("Introduction", result["draft_sections"])
        self.assertIn("structuring", result["completed_agents"])

    @patch("app.agents.structuring.get_llm")
    def test_no_chunks_returns_empty_draft(self, mock_get_llm):
        state: PipelineState = {"retrieved_chunks": [], "citation_style": "apa"}
        result = structuring_agent(state)
        self.assertEqual(result["structuring_status"], "ok")
        for section in THESIS_SECTIONS:
            self.assertEqual(result["draft_sections"][section], "[NO_CONTENT]")
        mock_get_llm.assert_not_called()

    @patch("app.agents.structuring.get_llm")
    def test_llm_error_captured(self, mock_get_llm):
        mock_get_llm.side_effect = RuntimeError("LLM unavailable")
        state: PipelineState = {
            "retrieved_chunks": [{"text": "Some text.", "metadata": {"source_filename": "x.pdf", "section": "Introduction"}}],
        }
        result = structuring_agent(state)
        self.assertEqual(result["structuring_status"], "error")
        self.assertIn("LLM unavailable", result["structuring_error"])
        self.assertIn("structuring", result["errors"][0])

    @patch("app.agents.structuring.get_llm")
    def test_all_thesis_sections_in_output(self, mock_get_llm):
        mock_llm  = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = json.dumps({"outline": {}, "draft_sections": {}})
        mock_llm.invoke.return_value = mock_resp
        mock_get_llm.return_value = mock_llm

        state: PipelineState = {
            "retrieved_chunks": [{"text": "Content.", "metadata": {"source_filename": "f.pdf", "section": "Introduction"}}]
        }
        result = structuring_agent(state)
        for section in THESIS_SECTIONS:
            self.assertIn(section, result["draft_sections"])


# ---------------------------------------------------------------------------
# Citation Agent tests
# ---------------------------------------------------------------------------
from app.agents.citation import citation_agent, _chunk_to_citation_dict


class TestCitationAgentHelpers(unittest.TestCase):

    def test_chunk_to_citation_dict_extracts_year(self):
        chunk = {"text": "Smith J. AI systems. Nature. 2021;10:1-5.", "metadata": {}}
        result = _chunk_to_citation_dict(chunk, 0)
        self.assertIsNotNone(result)
        self.assertEqual(result["year"], 2021)

    def test_chunk_to_citation_dict_extracts_doi(self):
        chunk = {"text": "doi: 10.1038/s41586-021-03819-2 title here 2020", "metadata": {}}
        result = _chunk_to_citation_dict(chunk, 1)
        self.assertIsNotNone(result)
        self.assertIn("10.1038", result["doi"])

    def test_chunk_to_citation_dict_empty_returns_none(self):
        chunk = {"text": "", "metadata": {}}
        result = _chunk_to_citation_dict(chunk, 0)
        self.assertIsNone(result)


class TestCitationAgentNode(unittest.TestCase):

    def _make_llm_response(self, findings: list[dict]):
        mock_llm  = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = json.dumps({"findings": findings})
        mock_llm.invoke.return_value = mock_resp
        return mock_llm

    @patch("app.agents.citation.get_llm")
    def test_supported_claim_recorded(self, mock_get_llm):
        findings = [{"claim": "Accuracy was 94%.", "status": "SUPPORTED", "source": "paper.pdf:Results", "evidence": "94% accuracy"}]
        mock_get_llm.return_value = self._make_llm_response(findings)

        state: PipelineState = {
            "draft_sections":  {"Results": "Accuracy was 94% on the test set."},
            "retrieved_chunks": [{"text": "94% accuracy", "metadata": {"source_filename": "paper.pdf", "section": "Results"}}],
            "citation_style":  "apa",
        }
        result = citation_agent(state)
        self.assertEqual(result["citation_status"], "ok")
        self.assertEqual(len(result["citation_report"]), 1)
        self.assertEqual(result["citation_report"][0]["status"], "SUPPORTED")

    @patch("app.agents.citation.get_llm")
    def test_flagged_claim_recorded(self, mock_get_llm):
        findings = [{"claim": "Invented statistic.", "status": "FLAGGED", "source": None, "evidence": None}]
        mock_get_llm.return_value = self._make_llm_response(findings)

        state: PipelineState = {
            "draft_sections":  {"Methods": "We used invented statistic of 500 samples."},
            "retrieved_chunks": [],
            "citation_style":  "apa",
        }
        result = citation_agent(state)
        self.assertEqual(result["citation_report"][0]["status"], "FLAGGED")

    @patch("app.agents.citation.get_llm")
    def test_section_attached_to_finding(self, mock_get_llm):
        findings = [{"claim": "Some claim.", "status": "SUPPORTED", "source": "x.pdf:Methods", "evidence": "Some claim."}]
        mock_get_llm.return_value = self._make_llm_response(findings)

        state: PipelineState = {
            "draft_sections":  {"Methods": "Some claim."},
            "retrieved_chunks": [{"text": "Some claim.", "metadata": {"source_filename": "x.pdf", "section": "Methods"}}],
            "citation_style":  "apa",
        }
        result = citation_agent(state)
        self.assertEqual(result["citation_report"][0]["section"], "Methods")

    @patch("app.agents.citation.get_llm")
    def test_empty_draft_returns_empty_report(self, mock_get_llm):
        state: PipelineState = {"draft_sections": {}, "retrieved_chunks": [], "citation_style": "apa"}
        result = citation_agent(state)
        self.assertEqual(result["citation_report"], [])
        mock_get_llm.assert_not_called()

    @patch("app.agents.citation.get_llm")
    def test_no_content_sections_skipped(self, mock_get_llm):
        mock_get_llm.return_value = self._make_llm_response([])
        state: PipelineState = {
            "draft_sections":  {"Introduction": "[NO_CONTENT]", "Methods": "We used Python."},
            "retrieved_chunks": [{"text": "We used Python.", "metadata": {"source_filename": "p.pdf", "section": "Methods"}}],
            "citation_style":  "apa",
        }
        result = citation_agent(state)
        # LLM should only be called once (for Methods, not Introduction)
        self.assertEqual(mock_get_llm.return_value.invoke.call_count, 1)

    @patch("app.agents.citation.get_llm")
    def test_citation_agent_marks_completed(self, mock_get_llm):
        mock_get_llm.return_value = self._make_llm_response([])
        state: PipelineState = {
            "draft_sections":  {"Methods": "Text here."},
            "retrieved_chunks": [],
            "citation_style":  "apa",
            "completed_agents": ["structuring"],
        }
        result = citation_agent(state)
        self.assertIn("citation", result["completed_agents"])


# ---------------------------------------------------------------------------
# Formatting Agent tests
# ---------------------------------------------------------------------------
from app.agents.formatting import (
    formatting_agent,
    load_template,
    _word_count,
    _check_section_presence,
    _check_word_count,
    _check_flagged_claims,
    _assemble_draft,
)


class TestFormattingAgentHelpers(unittest.TestCase):

    def test_word_count_normal(self):
        self.assertEqual(_word_count("hello world foo bar"), 4)

    def test_word_count_no_content(self):
        self.assertEqual(_word_count("[NO_CONTENT]"), 0)

    def test_word_count_empty(self):
        self.assertEqual(_word_count(""), 0)

    def test_check_section_presence_flags_missing(self):
        issues: list[dict] = []
        result = _check_section_presence("Methods", "[NO_CONTENT]", issues)
        self.assertFalse(result)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "ERROR")

    def test_check_section_presence_passes_with_content(self):
        issues: list[dict] = []
        result = _check_section_presence("Methods", "Some method content here.", issues)
        self.assertTrue(result)
        self.assertEqual(len(issues), 0)

    def test_check_word_count_below_minimum(self):
        issues: list[dict] = []
        _check_word_count("Methods", "Short.", {"min_words": 300}, issues)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["rule"], "min_words")

    def test_check_word_count_above_maximum(self):
        issues: list[dict] = []
        long_text = " ".join(["word"] * 400)
        _check_word_count("Abstract", long_text, {"max_words": 300}, issues)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["rule"], "max_words")

    def test_check_flagged_claims_correct_section(self):
        issues: list[dict] = []
        report = [
            {"claim": "Invented fact.", "section": "Methods", "status": "FLAGGED"},
            {"claim": "Real fact.",     "section": "Methods", "status": "SUPPORTED"},
            {"claim": "Other.",         "section": "Results", "status": "FLAGGED"},
        ]
        flagged = _check_flagged_claims("Methods", report, issues)
        self.assertEqual(flagged, ["Invented fact."])
        self.assertEqual(len(issues), 1)

    def test_load_template_default(self):
        tmpl = load_template("default")
        self.assertIn("required_sections", tmpl)
        self.assertIn("Methods", tmpl["required_sections"])

    def test_load_template_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_template("nonexistent_template")

    def test_assemble_draft_includes_all_sections(self):
        draft = _assemble_draft(
            draft_sections={"Introduction": "Intro text.", "Methods": "[NO_CONTENT]"},
            required_sections=["Introduction", "Methods"],
            all_flagged_claims={},
            formatted_bibliography=["Smith J. 2020. Paper."],
            template={"display_name": "Test Thesis", "formatting_rules": {}},
        )
        self.assertIn("## Introduction", draft)
        self.assertIn("## Methods", draft)
        self.assertIn("_[No content available", draft)
        self.assertIn("Smith J. 2020", draft)

    def test_assemble_draft_inserts_flagged_marker(self):
        draft = _assemble_draft(
            draft_sections={"Methods": "We used 500 invented samples in our study."},
            required_sections=["Methods"],
            all_flagged_claims={"Methods": ["We used 500 invented samples"]},
            formatted_bibliography=[],
            template={"display_name": "Test", "formatting_rules": {}},
        )
        self.assertIn("[CITATION FLAGGED]", draft)


class TestFormattingAgentNode(unittest.TestCase):

    def _base_state(self, **overrides) -> PipelineState:
        state: PipelineState = {
            "draft_sections": {
                "Abstract":         "This is the abstract with sufficient word count repeated many times here.",
                "Introduction":     " ".join(["Word"] * 350),
                "Literature Review":" ".join(["Word"] * 550),
                "Methods":          " ".join(["Word"] * 320),
                "Results":          " ".join(["Word"] * 220),
                "Discussion":       " ".join(["Word"] * 310),
                "Conclusion":       " ".join(["Word"] * 160),
                "References":       "1. Smith J. 2020.",
            },
            "citation_report":        [],
            "formatted_bibliography": [],
            "citation_style":         "apa",
            "template_name":          "default",
            "completed_agents":       ["structuring", "citation"],
        }
        state.update(overrides)
        return state

    def test_ok_status_on_clean_draft(self):
        result = formatting_agent(self._base_state())
        self.assertIn(result["formatting_status"], ("ok", "warnings"))
        self.assertIsInstance(result["final_draft"], str)
        self.assertGreater(len(result["final_draft"]), 0)

    def test_missing_section_generates_error_issue(self):
        state = self._base_state()
        state["draft_sections"]["Methods"] = "[NO_CONTENT]"
        result = formatting_agent(state)
        errors = [i for i in result["formatting_report"] if i["severity"] == "ERROR"]
        self.assertTrue(any(i["section"] == "Methods" for i in errors))

    def test_flagged_claim_generates_error_issue(self):
        state = self._base_state()
        state["citation_report"] = [{
            "claim":   "We surveyed 1000 patients.",
            "section": "Methods",
            "status":  "FLAGGED",
        }]
        state["draft_sections"]["Methods"] = "We surveyed 1000 patients in our study."
        result = formatting_agent(state)
        errors = [i for i in result["formatting_report"] if i["rule"] == "unsupported_claim"]
        self.assertTrue(len(errors) > 0)

    def test_final_draft_is_markdown(self):
        result = formatting_agent(self._base_state())
        self.assertIn("##", result["final_draft"])

    def test_formatting_agent_marks_completed(self):
        result = formatting_agent(self._base_state())
        self.assertIn("formatting", result["completed_agents"])

    def test_invalid_template_sets_error_status(self):
        state = self._base_state(template_name="does_not_exist")
        result = formatting_agent(state)
        self.assertEqual(result["formatting_status"], "error")


# ---------------------------------------------------------------------------
# Graph wiring tests
# ---------------------------------------------------------------------------

class TestGraphWiring(unittest.TestCase):

    @patch("app.agents.graph.retrieve_node")
    @patch("app.agents.graph.structuring_agent")
    @patch("app.agents.graph.citation_agent")
    @patch("app.agents.graph.formatting_agent")
    def test_build_graph_compiles(self, mock_fmt, mock_cit, mock_str, mock_ret):
        """build_graph() should return a compilable graph without errors."""
        from app.agents.graph import build_graph
        graph = build_graph()
        self.assertIsNotNone(graph)

    def test_retrieve_node_handles_chroma_error(self):
        """retrieve_node should catch ChromaDB errors gracefully."""
        from app.agents.graph import retrieve_node

        with patch("app.agents.graph.EmbeddingStore") as mock_store_cls:
            mock_store_cls.side_effect = RuntimeError("ChromaDB unavailable")
            state: PipelineState = {
                "document_ids": [],
                "chroma_path":  "./nonexistent",
                "collection_name": "test",
                "n_chunks": 5,
                "errors": [],
            }
            result = retrieve_node(state)
            self.assertEqual(result["retrieved_chunks"], [])
            self.assertTrue(len(result["errors"]) > 0)


# ---------------------------------------------------------------------------
# End-to-end run_pipeline (all agents mocked, no I/O)
# ---------------------------------------------------------------------------

class TestRunPipeline(unittest.TestCase):

    @patch("app.agents.graph.EmbeddingStore")
    @patch("app.agents.structuring.get_llm")
    @patch("app.agents.citation.get_llm")
    def test_run_pipeline_returns_final_draft(
        self, mock_cit_llm, mock_str_llm, mock_store_cls
    ):
        from app.agents.graph import run_pipeline

        # Mock ChromaDB retrieval
        mock_store = MagicMock()
        mock_store.query.return_value = [
            {
                "text": "Transformer models achieve state-of-the-art results.",
                "metadata": {"source_filename": "paper.pdf", "section": "Introduction"},
                "distance": 0.1,
            }
        ]
        mock_store_cls.return_value = mock_store

        # Mock Structuring LLM
        str_resp = MagicMock()
        str_resp.content = json.dumps({
            "outline": {"Introduction": "Overview of transformer models."},
            "draft_sections": {"Introduction": "Transformer models achieve state-of-the-art results."},
        })
        mock_str_llm.return_value.invoke.return_value = str_resp

        # Mock Citation LLM
        cit_resp = MagicMock()
        cit_resp.content = json.dumps({
            "findings": [{
                "claim":    "Transformer models achieve state-of-the-art results.",
                "status":   "SUPPORTED",
                "source":   "paper.pdf:Introduction",
                "evidence": "Transformer models achieve state-of-the-art results.",
            }]
        })
        mock_cit_llm.return_value.invoke.return_value = cit_resp

        result = run_pipeline(
            document_ids=[],
            citation_style="apa",
            template_name="default",
            chroma_path="./nonexistent",
        )

        self.assertIn("final_draft", result)
        self.assertIn("formatting_report", result)
        self.assertIn("citation_report", result)
        self.assertGreater(len(result.get("completed_agents", [])), 0)

    def test_run_pipeline_with_no_chunks_still_completes(self):
        """Pipeline should complete all agents even when ChromaDB has no chunks."""
        from app.agents.graph import run_pipeline

        with patch("app.agents.graph.EmbeddingStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.query.return_value = []
            mock_store_cls.return_value = mock_store

            result = run_pipeline(
                document_ids=[],
                citation_style="apa",
                template_name="default",
                chroma_path="./nonexistent",
            )

        # Structuring agent should handle empty chunks without calling LLM
        self.assertIn("draft_sections", result)
        self.assertIn("final_draft", result)
        all_no_content = all(
            v == "[NO_CONTENT]"
            for v in result.get("draft_sections", {}).values()
        )
        self.assertTrue(all_no_content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
