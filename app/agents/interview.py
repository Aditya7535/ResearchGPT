"""
Guided Interview Agent — ResearchGPT multi-agent pipeline.

Responsibility
--------------
Activates when the Structuring Agent (or user) flags a thesis section as
thin, incomplete, or missing ([NO_CONTENT]).

Requirements & Features
-----------------------
1. Generates 3–6 short, specific follow-up questions dynamically based on:
   - Section type (e.g. Methods, Results, Discussion, Introduction)
   - Partial content already extracted from uploads
   - Paper's topic / domain (detected or provided)
2. Captures plain text responses per question (or handles skipped questions).
3. Converts answered Q&A pairs + upload content into properly formatted academic
   prose using ONLY the user's own answers and uploaded content — NO invented
   facts, numbers, or claims beyond what the user stated.
4. Tags every sentence in the output section with its source:
   - "user-upload"    : derived from uploaded document chunks
   - "user-interview" : derived from user's interview answers
5. If a question is skipped or empty, leaves it flagged as an open gap in that section;
   does NOT auto-fill placeholder text.
6. Stores complete Q&A history so the user can revisit and edit answers later.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.agents.llm import get_llm, make_human_message, make_system_message
from app.agents.state import PipelineState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default fallback questions per section if LLM is offline/mocked
# ---------------------------------------------------------------------------
STANDARD_QUESTION_TEMPLATES: dict[str, list[str]] = {
    "Methods": [
        "What specific method, framework, or approach did you use?",
        "What was your sample size, dataset, or computational scale?",
        "What software, instruments, or tools were utilized for data collection?",
        "What validation protocols or baseline comparisons were established?"
    ],
    "Results": [
        "What were your key quantitative or qualitative findings?",
        "Did you find statistical significance? What were the exact values or metrics?",
        "What unexpected outcomes or trends were observed in the data?",
        "How do the results compare across different experimental conditions?"
    ],
    "Discussion": [
        "How do your findings compare to existing literature or cited papers?",
        "What are the main limitations or potential sources of error in your study?",
        "What are the theoretical or practical implications of your results?",
        "What future research directions do your findings suggest?"
    ],
    "Introduction": [
        "What is the primary research question or core hypothesis of your study?",
        "What real-world problem or gap in knowledge does this research address?",
        "What is the practical or academic motivation behind this work?"
    ],
    "Literature Review": [
        "What key theoretical frameworks form the foundation of your study?",
        "What major landmark papers or studies directly influence your work?",
        "What specific gaps in existing literature does your research aim to fill?"
    ],
    "Conclusion": [
        "What is the single most important takeaway from your research?",
        "How do your contributions advance the current state of the field?"
    ]
}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
_QUESTION_GEN_SYSTEM_PROMPT = """You are an academic research interviewer for ResearchGPT.

Task:
Generate 3 to 6 short, highly specific follow-up questions for a thesis section that has thin or missing content.

Rules:
1. Tailor questions dynamically to the specified paper domain/topic and section type.
2. Ask about standard academic details missing from the section (e.g. sample size, methods used, key values, comparison to literature, study limitations).
3. Keep questions clear, direct, and concise (1 sentence each).
4. Respond ONLY with a valid JSON array of objects, where each object has:
   "question_id": "q1", "q2", etc.
   "question": "question text"

Do NOT include markdown formatting or extra text outside the JSON array."""

_PROSE_SYNTHESIS_SYSTEM_PROMPT = """You are an academic prose editor for ResearchGPT.

CRITICAL RULES — STRICT GROUNDING:
1. Convert the user's interview Q&A answers and existing partial upload text into formal, publication-ready academic prose for the section.
2. Use ONLY facts, numbers, methods, and claims provided in the user's answers or upload content.
3. ABSOLUTELY NO INVENTED FACTS, NUMBERS, CITATIONS, OR CLAIMS beyond what the user stated.
4. If a question was skipped or unanswered, do NOT make up an answer or insert generic placeholders.
5. Format the output as a JSON object with two keys:
   "sentences": list of objects, each containing:
       "text": string (a single complete sentence)
       "source": string ("user-upload" if from upload content, or "user-interview" if from Q&A answer)
   "open_gaps": list of objects for skipped/unanswered items:
       "question_id": string
       "question": string

Respond ONLY with the JSON object."""

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _clean_json_output(raw: str) -> str:
    """Strip markdown fences and trim whitespace from LLM output."""
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    return raw


def split_into_sentences(text: str) -> list[str]:
    """Split text into individual sentences using standard sentence boundaries."""
    if not text or text == "[NO_CONTENT]":
        return []
    # Split on sentence-ending punctuation followed by space or newline
    raw_sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in raw_sentences if s.strip()]

# ---------------------------------------------------------------------------
# Core Guided Interview Logic
# ---------------------------------------------------------------------------

def detect_thin_sections(draft_sections: dict[str, str], min_words: int = 150) -> list[str]:
    """
    Identify sections flagged as missing ([NO_CONTENT]) or thin (< min_words).
    """
    thin_sections: list[str] = []
    for section_name, content in draft_sections.items():
        if not content or content == "[NO_CONTENT]":
            thin_sections.append(section_name)
        else:
            word_count = len(content.split())
            if word_count < min_words:
                thin_sections.append(section_name)
    return thin_sections


def generate_interview_questions(
    section_name: str,
    partial_content: str = "",
    domain: str = "General Academic",
    num_questions: int = 4
) -> list[dict[str, str]]:
    """
    Generate 3-6 short, specific follow-up questions dynamically tailored to
    the paper's topic/domain and section type.
    """
    prompt = f"""Section Type: {section_name}
Paper Topic / Domain: {domain}
Existing Content Snippet: "{partial_content[:300] if partial_content else '[NO_CONTENT]'}"

Generate {num_questions} specific follow-up questions to complete the {section_name} section."""

    try:
        llm = get_llm(temperature=0.2)
        messages = [
            make_system_message(_QUESTION_GEN_SYSTEM_PROMPT),
            make_human_message(prompt)
        ]
        response = llm.invoke(messages)
        raw_text = response.content if hasattr(response, "content") else str(response)
        cleaned = _clean_json_output(raw_text)

        parsed = json.loads(cleaned)
        if isinstance(parsed, list) and len(parsed) > 0:
            questions = []
            for idx, q_item in enumerate(parsed, 1):
                q_text = q_item.get("question") if isinstance(q_item, dict) else str(q_item)
                questions.append({
                    "question_id": f"q{idx}",
                    "question": q_text,
                    "section": section_name
                })
            return questions[:6]
    except Exception as exc:
        logger.warning("LLM question generation failed, using domain-tailored templates: %s", exc)

    # Fallback generator if LLM is unavailable
    default_qs = STANDARD_QUESTION_TEMPLATES.get(
        section_name,
        [
            f"What specific details should be included in your {section_name}?",
            f"What key data or supporting evidence is relevant to {section_name}?"
        ]
    )
    
    formatted_questions = []
    for idx, q_text in enumerate(default_qs[:num_questions], 1):
        # Tailor fallback questions with domain context
        domain_tailored = f"{q_text[:-1]} for your study on {domain}?" if not q_text.lower().endswith("?") else q_text
        formatted_questions.append({
            "question_id": f"q{idx}",
            "question": domain_tailored,
            "section": section_name
        })
    return formatted_questions


def process_interview_answers(
    section_name: str,
    partial_content: str,
    qna_pairs: list[dict[str, Any]],
    domain: str = "General Academic"
) -> dict[str, Any]:
    """
    Convert user answers + partial content into tagged academic prose.

    - Uses ONLY user answers and uploaded partial content.
    - Tags sentences with source: "user-upload" or "user-interview".
    - Flags skipped questions as open_gaps without auto-filling placeholders.
    """
    answered_items: list[dict] = []
    skipped_items: list[dict] = []

    for qna in qna_pairs:
        q_id = qna.get("question_id", "q")
        q_text = qna.get("question", "")
        answer = (qna.get("answer") or "").strip()
        is_skipped = qna.get("skipped", False) or not answer

        if is_skipped:
            skipped_items.append({"question_id": q_id, "question": q_text})
        else:
            answered_items.append({
                "question_id": q_id,
                "question": q_text,
                "answer": answer
            })

    # Prepare LLM input
    qna_input_text = "\n".join(
        f"Q ({item['question_id']}): {item['question']}\nA: {item['answer']}"
        for item in answered_items
    )

    user_prompt = f"""Section Name: {section_name}
Domain: {domain}
Existing Upload Content: "{partial_content if partial_content and partial_content != '[NO_CONTENT]' else 'None'}"

User Q&A Answers:
{qna_input_text if qna_input_text else 'No user answers provided.'}

Unanswered / Skipped Questions:
{json.dumps(skipped_items, indent=2)}

Generate the formatted academic prose and return the sentence-level JSON object."""

    try:
        llm = get_llm(temperature=0.1)
        messages = [
            make_system_message(_PROSE_SYNTHESIS_SYSTEM_PROMPT),
            make_human_message(user_prompt)
        ]
        response = llm.invoke(messages)
        raw_text = response.content if hasattr(response, "content") else str(response)
        cleaned = _clean_json_output(raw_text)

        parsed = json.loads(cleaned)
        tagged_sentences = parsed.get("sentences", [])
        open_gaps = parsed.get("open_gaps", skipped_items)

        # Assemble full section text
        full_text = " ".join(s["text"] for s in tagged_sentences) if tagged_sentences else ""

        return {
            "section_name": section_name,
            "prose": full_text,
            "tagged_sentences": tagged_sentences,
            "open_gaps": open_gaps,
            "qna_history": qna_pairs
        }

    except Exception as exc:
        logger.warning("LLM prose synthesis error, building deterministic tagged sentences: %s", exc)

    # Fallback deterministic sentence assembly without LLM
    tagged_sentences: list[dict[str, str]] = []
    
    # 1. Existing upload sentences
    if partial_content and partial_content != "[NO_CONTENT]":
        for s in split_into_sentences(partial_content):
            tagged_sentences.append({"text": s, "source": "user-upload"})

    # 2. User interview answer sentences
    for item in answered_items:
        ans_text = item["answer"]
        # Convert Q&A answer into structured prose sentence
        s_text = ans_text if ans_text.endswith(".") else f"{ans_text}."
        for sentence in split_into_sentences(s_text):
            tagged_sentences.append({"text": sentence, "source": "user-interview"})

    full_text = " ".join(s["text"] for s in tagged_sentences)

    return {
        "section_name": section_name,
        "prose": full_text if full_text else "[NO_CONTENT]",
        "tagged_sentences": tagged_sentences,
        "open_gaps": skipped_items,
        "qna_history": qna_pairs
    }

# ---------------------------------------------------------------------------
# Guided Interview Agent Node for LangGraph
# ---------------------------------------------------------------------------

def guided_interview_agent(state: PipelineState) -> PipelineState:
    """
    LangGraph Node — Guided Interview Agent.

    Reads:  state["draft_sections"], state.get("interview_answers"), state.get("domain")
    Writes: state["interview_history"], state["interview_gaps"], state["tagged_sections"],
            state["draft_sections"], state["interview_status"]
    """
    logger.info("▶  Guided Interview Agent — start")

    draft_sections: dict[str, str] = state.get("draft_sections", {})
    pending_answers: dict[str, list[dict]] = state.get("pending_interview_answers", {}) # type: ignore[typeddict-unknown-key]
    domain: str = state.get("domain", "General Academic") # type: ignore[typeddict-unknown-key]

    interview_history: dict[str, list[dict]] = dict(state.get("interview_history", {}))
    interview_gaps: dict[str, list[dict]] = dict(state.get("interview_gaps", {}))
    tagged_sections: dict[str, list[dict]] = dict(state.get("tagged_sections", {}))
    updated_drafts: dict[str, str] = dict(draft_sections)

    thin_sections = detect_thin_sections(draft_sections)

    try:
        # If user submitted pending interview answers for thin sections, process them
        for sec in thin_sections:
            partial = draft_sections.get(sec, "")
            
            # Retrieve or generate Q&A pairs
            qna_list = pending_answers.get(sec)
            if not qna_list:
                # Generate initial interview questions if none exist
                qs = generate_interview_questions(sec, partial, domain=domain)
                interview_history[sec] = [{**q, "answer": "", "skipped": True} for q in qs]
                interview_gaps[sec] = [{"question_id": q["question_id"], "question": q["question"]} for q in qs]
            else:
                # Process submitted user answers
                result = process_interview_answers(sec, partial, qna_list, domain=domain)
                interview_history[sec] = result["qna_history"]
                interview_gaps[sec] = result["open_gaps"]
                tagged_sections[sec] = result["tagged_sentences"]
                if result["prose"]:
                    updated_drafts[sec] = result["prose"]

        logger.info(
            "Guided Interview Agent: evaluated %d thin sections. History updated for %s.",
            len(thin_sections),
            list(interview_history.keys())
        )

        return {
            **state,
            "draft_sections": updated_drafts,
            "interview_history": interview_history,
            "interview_gaps": interview_gaps,
            "tagged_sections": tagged_sections,
            "interview_status": "ok",
            "completed_agents": state.get("completed_agents", []) + ["interview"]
        }

    except Exception as exc:
        logger.error("Guided Interview Agent error: %s", exc, exc_info=True)
        return {
            **state,
            "interview_status": "error",
            "interview_error": str(exc),
            "errors": state.get("errors", []) + [f"interview: {exc}"]
        }
