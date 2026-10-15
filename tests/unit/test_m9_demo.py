"""M9 runnable demo fixture/guard tests. No Docker or network required."""
import json
from pathlib import Path
from uuid import uuid4

import fitz
import pytest
from docx import Document

from scripts.check_m9 import (
    CONTRACT_TXT, DOCX_TEXT, PDF_PAGES,
    assert_citations, fixture_files, make_docx, make_pdf, summarize_result,
    validate_demo_state,
)


def test_demo_fixtures_are_real_txt_pdf_docx():
    content = fixture_files()
    assert len(content) == 3
    txt, pdf, docx = content
    assert txt[0].endswith(".txt") and txt[1].decode() == CONTRACT_TXT
    assert pdf[0].endswith(".pdf") and pdf[1].startswith(b"%PDF-")
    with fitz.open(stream=make_pdf(), filetype="pdf") as document:
        assert len(document) == 2
        assert PDF_PAGES[1] in document[1].get_text()
    assert docx[0].endswith(".docx")
    from io import BytesIO
    paragraphs = [p.text for p in Document(BytesIO(make_docx())).paragraphs]
    assert paragraphs == list(DOCX_TEXT)
    assert b"PK" == docx[1][:2]


def source(*, sid="S1", doc_id="test-doc", page=None):
    return {
        "id": sid, "document_id": doc_id, "chunk_id": "chunk-x",
        "filename": "test.txt", "evidence": "合同违约责任", "page": page,
    }


def test_guard_accepts_real_citations():
    assert_citations({
        "answer": "违约责任见合同[S1]", "sources": [source(doc_id="abc", page=2)],
    }, "abc", required_page=2)


@pytest.mark.parametrize("answer,sources,doc,page", [
    ("没有引用", [source()], "test-doc", None),
    ("错误引用[S99]", [source()], "test-doc", None),
    ("文内引用[S1]", [], "test-doc", None),
    ("来源错位[S1]", [source(doc_id="other")], "test-doc", None),
    ("页码错误[S1]", [source(page=1)], "test-doc", 2),
    ("缺少原始块[S1]", [{"id": "S1", "document_id": "test-doc"}], "test-doc", None),
    ("重复编号[S1]", [source(), source()], "test-doc", None),
])
def test_guard_rejects_unattributed_or_out_of_scope_answer(answer, sources, doc, page):
    with pytest.raises(AssertionError):
        assert_citations({"answer": answer, "sources": sources}, doc, required_page=page)


def test_demo_state_version_and_uuid_scope():
    state = {
        "schema_version": 1, "documents": {
            "txt": str(uuid4()), "pdf": str(uuid4()), "docx": str(uuid4()),
        },
        "user_id": str(uuid4()), "case_results": [],
    }
    validate_demo_state(state)
    with pytest.raises(AssertionError):
        validate_demo_state({**state, "schema_version": 999})


def test_demo_report_has_no_original_query_or_evidence():
    reply = {
        "status": "answered",
        "tools_called": ["mcp_find_clause"], "mcp_tools_called": ["find_clause"],
        "sources": [source()],
        "answer": "合同的违约责任包含个人敏感内容[S1]",
        "query": "私人内容",
        "trace_id": str(uuid4()),
    }
    report = summarize_result("clause", reply)
    output = json.dumps(report, ensure_ascii=False)
    assert report["source_count"] == 1
    assert "私人内容" not in output
    assert "敏感内容" not in output


def test_one_build_and_no_download_in_acceptance_scripts():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY scripts/check_m9.py ./scripts/check_m9.py" in dockerfile
    for bat in ("check_m9.bat", "check_m9_live.bat", "run_eval.bat"):
        body = (root / "scripts" / bat).read_text(encoding="utf-8").lower()
        assert "up -d --build" not in body
        assert "down -v" not in body
    assert "docker compose exec -t api python scripts/check_m9.py base" not in (
        root / "scripts" / "check_m9.bat"
    ).read_text()
