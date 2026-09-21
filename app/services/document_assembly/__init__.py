"""
Document Assembly Service for ResearchGPT.

Public API
----------
    from app.services.document_assembly import DocumentAssembler, ThesisContent

    content  = ThesisContent.from_dict(json_data)
    result   = DocumentAssembler().assemble(content, output_dir="./output")
    print(result.word_path)   # Path to .docx
    print(result.pdf_path)    # Path to .pdf
"""

from app.services.document_assembly.assembler import DocumentAssembler, AssemblyResult
from app.services.document_assembly.models import (
    ThesisContent, Section, DataTable, ChartConfig,
)

__all__ = [
    "DocumentAssembler", "AssemblyResult",
    "ThesisContent", "Section", "DataTable", "ChartConfig",
]
