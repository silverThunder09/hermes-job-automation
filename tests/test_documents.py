from hermes_job_automation.documents import create_application_documents


def test_application_documents_include_docx_and_korean_pdf(posting, tmp_path):
    files = create_application_documents(
        tmp_path,
        posting(),
        "Java와 Spring 경험",
        "프로젝트에서 결함을 수정했습니다.",
    )

    assert len(files) == 4
    assert [path.suffix for path in files] == [".docx", ".pdf", ".docx", ".pdf"]
    assert all(path.is_file() for path in files)
    assert all(path.read_bytes().startswith(b"%PDF-") for path in files if path.suffix == ".pdf")