"""Index legal PDF/text files into the shared legal knowledge base."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.engines.rag_drafter import build_knowledge_base


def read_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--doc-type", default="circular")
    args = parser.parse_args()
    docs = [(args.doc_type, read_document(path)) for path in args.directory.iterdir()
            if path.suffix.lower() in {".pdf", ".txt"}]
    db = SessionLocal()
    try:
        print(f"Indexed {build_knowledge_base(docs, db)} chunks")
    finally:
        db.close()
