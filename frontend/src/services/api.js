/**
 * ResearchGPT API Service Client.
 * 
 * Interacts with the FastAPI backend endpoints:
 * - Health check
 * - Document Ingestion & Listing
 * - Multi-agent LangGraph pipeline execution
 * - Guided Interview generation & synthesis
 * - Plagiarism detection
 * - DOCX / PDF Document Assembly & Export
 */

// Use VITE_API_BASE_URL if configured (e.g. for cloud static hosting), defaulting to '/api' for local proxying
const rawBase = (import.meta.env && import.meta.env.VITE_API_BASE_URL) || '/api';
const API_BASE = rawBase.endsWith('/api') ? rawBase : `${rawBase.replace(/\/+$/, '')}/api`;

/**
 * Check backend health & status
 */
export async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`, { method: 'GET' });
    if (!res.ok) return { online: false, status: res.status };
    const data = await res.json();
    return { online: true, ...data };
  } catch (err) {
    return { online: false, error: err.message };
  }
}

/**
 * Upload a document (.pdf, .docx, .txt) for ingestion into ChromaDB
 */
export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/ingest`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ingestion failed' }));
    throw new Error(err.detail || `Upload failed with status ${res.status}`);
  }

  return await res.json();
}

/**
 * List all documents stored in ChromaDB
 */
export async function listDocuments() {
  const res = await fetch(`${API_BASE}/documents`);
  if (!res.ok) throw new Error('Failed to retrieve documents');
  return await res.json();
}

/**
 * Query semantic chunks from ChromaDB
 */
export async function queryChunks({ query = '', documentId = '', section = '', limit = 10 } = {}) {
  const params = new URLSearchParams();
  if (query) params.append('query', query);
  if (documentId) params.append('document_id', documentId);
  if (section) params.append('section', section);
  if (limit) params.append('limit', limit);

  const res = await fetch(`${API_BASE}/chunks?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to query chunks');
  return await res.json();
}

/**
 * Trigger the multi-agent pipeline (Structuring -> Citation -> Formatting)
 */
export async function runAgentPipeline({
  documentIds = [],
  citationStyle = 'apa',
  templateName = 'default',
  nChunks = 20,
  extraState = null,
} = {}) {
  const res = await fetch(`${API_BASE}/pipeline/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      document_ids: documentIds,
      citation_style: citationStyle,
      template_name: templateName,
      n_chunks: nChunks,
      extra_state: extraState,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Pipeline execution failed' }));
    throw new Error(err.detail || `Pipeline failed with status ${res.status}`);
  }

  return await res.json();
}

/**
 * Generate Guided Interview questions for a thin/missing section
 */
export async function generateInterviewQuestions({
  sectionName,
  partialContent = '',
  domain = 'General Academic',
  numQuestions = 4,
}) {
  const res = await fetch(`${API_BASE}/interview/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      section_name: sectionName,
      partial_content: partialContent,
      domain,
      num_questions: numQuestions,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Question generation failed' }));
    throw new Error(err.detail || `Interview generation failed`);
  }

  return await res.json();
}

/**
 * Synthesize answered interview Q&A pairs into publication prose
 */
export async function answerInterviewQuestions({
  sectionName,
  qnaPairs,
  partialContent = '',
}) {
  const res = await fetch(`${API_BASE}/interview/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      section_name: sectionName,
      qna_pairs: qnaPairs,
      partial_content: partialContent,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Answer synthesis failed' }));
    throw new Error(err.detail || `Interview answer synthesis failed`);
  }

  return await res.json();
}

/**
 * Check plagiarism against ChromaDB source corpus
 */
export async function checkPlagiarism({
  sections,
  threshold = 0.8,
  documentIds = [],
  runExternal = false,
}) {
  const res = await fetch(`${API_BASE}/plagiarism/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sections,
      threshold,
      document_ids: documentIds,
      run_external: runExternal,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Plagiarism check failed' }));
    throw new Error(err.detail || `Plagiarism check failed`);
  }

  return await res.json();
}

/**
 * Format bibliography using citeproc-py
 */
export async function formatCitations(citations, style = 'apa') {
  const res = await fetch(`${API_BASE}/citation/format`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ citations, style }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Citation formatting failed' }));
    throw new Error(err.detail || `Citation formatting failed`);
  }

  return await res.json();
}

/**
 * Export document as .docx file blob
 */
export async function exportDocxBlob({
  title,
  authors = ['ResearchGPT Author'],
  abstract = '',
  sections = {},
  bibliography = [],
  templateName = 'default',
}) {
  const res = await fetch(`${API_BASE}/export/docx`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title,
      authors,
      abstract,
      sections,
      bibliography,
      template_name: templateName,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Word export failed' }));
    throw new Error(err.detail || 'Failed to generate Word document');
  }

  return await res.blob();
}

/**
 * Export document as .pdf file blob
 */
export async function exportPdfBlob({
  title,
  authors = ['ResearchGPT Author'],
  abstract = '',
  sections = {},
  bibliography = [],
  templateName = 'default',
}) {
  const res = await fetch(`${API_BASE}/export/pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title,
      authors,
      abstract,
      sections,
      bibliography,
      template_name: templateName,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'PDF export failed' }));
    throw new Error(err.detail || 'Failed to generate PDF document');
  }

  return await res.blob();
}
