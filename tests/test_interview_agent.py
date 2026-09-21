"""
Unit tests for Guided Interview Agent (app/agents/interview.py).

Test cases:
1. test_detect_thin_sections — detects missing ([NO_CONTENT]) or thin (<150 words) sections
2. test_generate_interview_questions_dynamic — generates 3-6 dynamic questions based on domain & section
3. test_process_interview_answers_strict_grounding — converts Q&A answers into academic prose without inventing facts
4. test_sentence_source_tagging — verifies sentence tagging ("user-upload", "user-interview")
5. test_skipped_question_gap_tracking — verifies skipped questions remain flagged as open gaps without placeholder auto-fill
6. test_guided_interview_agent_node — test LangGraph node state updates and Q&A history retention
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from app.agents.interview import (
    detect_thin_sections,
    generate_interview_questions,
    guided_interview_agent,
    process_interview_answers,
)
from app.agents.state import PipelineState


class TestGuidedInterviewAgent(unittest.TestCase):

    def test_detect_thin_sections(self):
        drafts = {
            "Abstract": "Short abstract text here.", # < 150 words -> thin
            "Introduction": "[NO_CONTENT]", # missing -> thin
            "Methods": " ".join(["word"] * 200), # > 150 words -> ok
        }
        thin = detect_thin_sections(drafts, min_words=150)
        self.assertIn("Abstract", thin)
        self.assertIn("Introduction", thin)
        self.assertNotIn("Methods", thin)

    @patch("app.agents.interview.get_llm")
    def test_generate_interview_questions_dynamic(self, mock_get_llm):
        mock_resp = MagicMock()
        mock_resp.content = json.dumps([
            {"question_id": "q1", "question": "What sample size was used for your 64-qubit circuit benchmark?"},
            {"question_id": "q2", "question": "What classical optimizer was paired with QAOA?"},
            {"question_id": "q3", "question": "What error mitigation techniques were applied?"}
        ])
        mock_get_llm.return_value.invoke.return_value = mock_resp

        questions = generate_interview_questions(
            section_name="Methods",
            partial_content="We evaluated QAOA circuits.",
            domain="Quantum Computing",
            num_questions=3
        )

        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0]["question_id"], "q1")
        self.assertIn("64-qubit", questions[0]["question"])

    def test_generate_interview_questions_fallback(self):
        with patch("app.agents.interview.get_llm", side_effect=RuntimeError("Offline")):
            questions = generate_interview_questions(
                section_name="Results",
                domain="Medical Imaging",
                num_questions=4
            )
            self.assertGreaterEqual(len(questions), 3)
            self.assertLessEqual(len(questions), 6)
            self.assertTrue(any("findings" in q["question"].lower() for q in questions))

    @patch("app.agents.interview.get_llm")
    def test_process_interview_answers_strict_grounding_and_tagging(self, mock_get_llm):
        mock_resp = MagicMock()
        mock_resp.content = json.dumps({
            "sentences": [
                {"text": "Scans were tokenized using PyMuPDF.", "source": "user-upload"},
                {"text": "We evaluated 12,000 anonymized chest CT scans across 3 hospital networks.", "source": "user-interview"}
            ],
            "open_gaps": []
        })
        mock_get_llm.return_value.invoke.return_value = mock_resp

        qna_pairs = [
            {"question_id": "q1", "question": "What was your dataset size?", "answer": "12,000 chest CT scans across 3 hospital networks", "skipped": False}
        ]

        result = process_interview_answers(
            section_name="Methods",
            partial_content="Scans were tokenized using PyMuPDF.",
            qna_pairs=qna_pairs,
            domain="Medical Radiology"
        )

        self.assertEqual(result["section_name"], "Methods")
        self.assertEqual(len(result["tagged_sentences"]), 2)
        self.assertEqual(result["tagged_sentences"][0]["source"], "user-upload")
        self.assertEqual(result["tagged_sentences"][1]["source"], "user-interview")
        self.assertIn("12,000", result["prose"])

    def test_skipped_question_gap_tracking(self):
        # Deterministic fallback test when user skips a question
        qna_pairs = [
            {"question_id": "q1", "question": "What approach was used?", "answer": "Convolutional Neural Network", "skipped": False},
            {"question_id": "q2", "question": "What p-value threshold was set?", "answer": "", "skipped": True} # Skipped question
        ]

        with patch("app.agents.interview.get_llm", side_effect=RuntimeError("Offline")):
            result = process_interview_answers(
                section_name="Results",
                partial_content="Initial metrics recorded.",
                qna_pairs=qna_pairs,
                domain="Robotics"
            )

            # Check gap tracking
            gaps = result["open_gaps"]
            self.assertEqual(len(gaps), 1)
            self.assertEqual(gaps[0]["question_id"], "q2")
            # Verify no fake placeholder content was generated for skipped q2
            self.assertNotIn("p-value", result["prose"])

    def test_guided_interview_agent_node(self):
        state: PipelineState = {
            "draft_sections": {
                "Introduction": "Established introduction.",
                "Methods": "[NO_CONTENT]", # thin
            },
            "completed_agents": ["structuring"],
            "domain": "Quantum Logistics" # type: ignore[typeddict-unknown-key]
        }

        with patch("app.agents.interview.get_llm", side_effect=RuntimeError("Offline")):
            result = guided_interview_agent(state)

            self.assertEqual(result["interview_status"], "ok")
            self.assertIn("interview", result["completed_agents"])
            self.assertIn("Methods", result["interview_history"])
            self.assertIn("Methods", result["interview_gaps"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
