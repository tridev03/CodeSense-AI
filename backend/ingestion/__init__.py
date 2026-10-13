"""
backend.ingestion — Repository Ingestion Pipeline

Implemented in Phase 2:
- Repository cloning (GitHub + local)
- File discovery and filtering
- Tree-sitter based code parsing (Python, JS, TS)
- Code-aware semantic chunking
- Documentation & configuration chunking
- Metadata extraction
- Ingestion pipeline orchestration
"""
from backend.ingestion.models import (  # noqa: F401
    CodeChunk,
    CodeSymbol,
    ContentType,
    DiscoveredFile,
    GitCommitInfo,
    ParsedFile,
    SymbolType,
)
