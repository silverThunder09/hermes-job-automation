"""Validate PR metadata offline. Never executes or echoes untrusted PR text."""
import argparse
import json
import re
from pathlib import Path
from typing import List

TITLE = re.compile(r"(feat|fix|docs|refactor|test|ci|chore|perf|build|style|revert)(?:\([a-z][a-z0-9_-]*\))?!?: \S[^\r\n]*")
REQUIRED = ("연결 이슈", "변경 내용", "검증", "ADR", "외부 변경·롤백")
ISSUE = re.compile(r"(?:Closes|Fixes|Refs) #[1-9][0-9]*")
ADR_PATH = re.compile(r"docs/adr/[0-9]{4}-[a-z0-9-]+\.md")


def validate_pr(title: str, body: str, root: Path) -> List[str]:
    errors = []
    title = title if isinstance(title, str) else ""
    body = body if isinstance(body, str) else ""
    match = TITLE.fullmatch(title)
    if not match or len(title) > 100:
        errors.append("제목: 100자 이하 Conventional Commits 형식을 사용하세요.")
    # Template guidance and commented answers are not evidence.
    body = re.sub(r"<!--.*?(?:-->|$)", "", body, flags=re.S)
    sections = {}
    current = None
    fence = None
    for line in body.splitlines():
        stripped = line.lstrip()
        marker = stripped[:3]
        if marker in {"```", "~~~"}:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
        if fence is None and line.startswith("## "):
            current = line[3:].strip()
            if current in sections:
                errors.append("필수 항목 제목을 중복 작성하지 마세요.")
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    values = {name: "\n".join(sections.get(name, [])).strip() for name in REQUIRED}
    for name, value in values.items():
        if not value:
            errors.append("{}: 구체적인 내용을 작성하세요.".format(name))
    issue_lines = values["연결 이슈"].splitlines()
    has_issue = any(ISSUE.fullmatch(line.strip()) for line in issue_lines)
    bootstrap = values["연결 이슈"] == "N/A: bootstrap" and match and match.group(1) in {"docs", "ci"}
    if not has_issue and not bootstrap:
        errors.append("연결 이슈: Closes/Fixes/Refs #양의정수 형식이 필요합니다. 초기 docs/ci만 N/A: bootstrap 예외입니다.")
    adr = values["ADR"]
    if adr.startswith("N/A: ") and len(adr[5:].strip()) >= 10:
        pass
    else:
        candidates = ADR_PATH.findall(adr)
        valid = False
        for name in candidates:
            candidate = (root / name).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                continue
            if candidate.is_file():
                valid = True
        if not valid or "../" in adr or "..\\" in adr:
            errors.append("ADR: 존재하는 docs/adr/NNNN-name.md 또는 N/A: 뒤에 10자 이상의 불필요 사유를 작성하세요.")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1], type=Path)
    args = parser.parse_args(argv)
    try:
        if args.event.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("oversized metadata")
        event = json.loads(args.event.read_text(encoding="utf-8"))
        pr = event["pull_request"]
        errors = validate_pr(pr.get("title"), pr.get("body"), args.root)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print("PR 이벤트를 읽을 수 없습니다. 입력 원문은 출력하지 않습니다.")
        return 1
    if errors:
        for error in errors:
            print("FAIL: " + error)
        return 1
    print("PASS: PR 메타데이터 형식 검사 통과. 이슈 실재 여부·ADR 타당성·검증 결과는 리뷰에서 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
