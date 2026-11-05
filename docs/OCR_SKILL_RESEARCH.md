# 한국어 채용공고 이미지 OCR 스킬 조사

## 결론

- **외부 스킬 통째 설치보다 검토한 절차만 재사용**하는 편이 안전하다. 1순위 참고 자료는 커뮤니티 `TerminalSkills/skills`의 `image-to-text`(Apache-2.0), 실행 가능한 이미지 스크립트 후보는 `davin51246/pdf-ocr`(MIT)다. 둘 다 한국어 채용공고 정확도를 입증한 자료는 확인하지 못했다.[S1][S2][S3][S4]
- **기존 Hermes `pdf` 스킬은 스캔 PDF OCR을 이미 다룬다.** Marker는 로컬 이미지도 받을 수 있으므로 “PDF만 가능”하지 않다. 다만 웹페이지의 `<img>`, 지연 로딩 이미지, 캔버스를 찾아 수집하는 기능은 별도다. 웹 텍스트 추출이 성공해도 공고 이미지의 글자까지 인식했다는 뜻은 아니다.[H1–H3][S13]
- 한국어 이미지의 반복 처리에는 **RapidOCR CPU/ONNX + 한국어 인식 모델**이 유력하다. 그러나 **프로젝트 Python 3.9에서는 Windows용 ONNX Runtime 최신 호환 wheel이 1.19.2에 묶이는 문제**가 있다. 유지보수 측면에서는 최신 Python의 별도 OCR 환경을 우선 검토하고, 3.9 고정이면 **Tesseract 5 + `kor+eng`를 먼저 시험**하는 것이 단순하다. 이는 소스·메타데이터 기반 판단이며 설치/실측 결과가 아니다.[S5–S12][P1–P3]

## 실제 GitHub 스킬 후보

| 후보 / 실제 SKILL.md | 확인한 기능·출처·라이선스 | 설치 부담·주의 / 판단 |
|---|---|---|
| [TerminalSkills `image-to-text`][S1] | 커뮤니티 작성. Tesseract TSV의 글자·좌표·신뢰도, 필요시 비전 모델과 대조, 모호한 날짜/코드 확대 검증. 저장소와 스킬 모두 Apache-2.0.[S1][S2] | Tesseract 실행 파일만으로 기본 OCR 가능; 자르기 예제는 Pillow. 한국어는 `--lang kor+eng` 및 해당 언어 데이터 필요. **절차 재사용 1순위**. Windows 예제의 `subprocess(..., text=True)`에는 UTF-8 인코딩을 명시해야 한글 디코딩 오류를 피할 수 있다. 비전 경로가 호스팅 모델이면 이미지 외부 전송 여부 확인 필요. |
| [davin51246 `pdf-ocr`][S3] | 이미지/PDF/전처리 스크립트, `--lang`, `--psm`, text/JSON/TSV. SKILL에 한국어 팩 설치가 명시됨. 저장소 MIT이며 Tesseract 공식 배포물이 아닌 개인 스킬.[S3][S4] | 안내 전체를 따르면 Tesseract + Pillow/pytesseract + OpenCV + PyMuPDF. **이미지만, 전처리 없이** 쓰는 `ocr_image.py` 기본 경로는 pytesseract/Pillow로 더 작게 구성 가능. Linux 설치 안내를 Windows에 그대로 실행 불가. `--output`에 UTF-8 미지정; 전처리 임시 PNG를 `Image.open()` 직후 삭제하므로 Windows 파일 잠금/지연 로딩 위험도 소스에서 확인. **코드 수정·검증 없이 즉시 채택은 비추천**.[S4] |
| [joneshong-skills `ocr`][S9] | 이미지 텍스트·좌표 검색, 반전/영역 분할/PSM 다중 패스. 한국어 언어 팩 언급. MIT.[S9] | Homebrew·고정 Python 경로·Claude 계열 `media`/`sandbox_execute` 가정, `--break-system-packages` 설치 안내. Hermes/Windows에 맞지 않음. 일부 검증은 “목표 글자가 더 이상 검출되지 않음”으로 일반 텍스트 추출 검증과도 맞지 않는다. **아이디어만 참고**. |
| [MihaiBalint `OCR`][S10] | 외부 `api.ocrskill.com`에 이미지 업로드 후 Markdown 반환. 기간 제한 체험키와 유료키 필요. GitHub 저장소 API에서 라이선스 식별값 없음.[S10] | 로컬 설치는 작지만 이미지 외부 전송·API 키·지속 비용 발생. 로컬 OCR 대체를 금지하는 공급자 지시도 포함. **로컬/무비밀정보 목표에 부적합**, 실행하지 않음. |

보조 후보 [TerminalSkills `pdf-ocr`][S2]: Python 3.9+, Tesseract 5, PDF용 Poppler/pdf2image 등. 스캔 PDF에는 쓸 수 있지만 기존 Hermes 기능과 겹친다. 첫 3쪽만 보고 전체 PDF의 OCR 필요 여부를 판정하는 예제는 혼합 문서의 뒤쪽 스캔을 놓칠 수 있으므로 그대로 복사하지 않는다.

## 경량 로컬 엔진 비교

### RapidOCR

- RapidAI가 PaddleOCR 모델을 ONNX 등으로 변환·배포하는 프로젝트다. Windows/CPU 오프라인 처리를 지원하며 기본값은 중국어/영어다. **기본 엔진만 생성하고 한국어가 된다고 가정하면 안 된다.**[S5]
- v3.3.0 공식 테스트는 `Rec.lang_type=LangRec.KOREAN`, `Rec.model_type=ModelType.MOBILE`, `Rec.ocr_version=OCRVersion.PPOCRV5`로 `korean.jpg`의 한국어 결과를 검증한다. 공고 전체 처리에는 검출을 켜야 하며, 릴리스의 `use_det=False` 예제는 이미 잘린 인식용 이미지에 해당한다.[S6]
- 기본 CPU 설치 안내는 `rapidocr onnxruntime`. PyTorch/GPU가 필수는 아니다. OpenCV, NumPy, Shapely 등 바이너리 의존성과 최초 모델 다운로드는 필요하다. 소스 모델 레지스트리에 한국어 PP-OCRv4/v5 URL과 SHA-256이 있다.[S5][S7]
- 크기 참고: PyPI `rapidocr==3.3.0` wheel **15,055,253 bytes**, `onnxruntime==1.19.2`의 CPython 3.9/Windows x64 wheel **11,085,591 bytes**. **압축 배포 파일만의 값이며 설치 총량/한국어 추가 모델 크기가 아니다.** 실제 디스크 사용량은 미측정.[P1][P2]
- 현행 RapidOCR 소스는 Python `>=3.8,<4`지만 런타임/하위 의존성의 별도 호환성을 보장하지 않는다. PyPI 전체 ONNX Runtime 릴리스 파일 목록에서 비철회 정식 `cp39-cp39-win_amd64` wheel의 최고 버전은 **1.19.2**로 확인했다. 3.9 환경에 무작정 최신 런타임을 지정하면 안 된다. 오래된 런타임의 보안 검토 또는 별도 최신 Python 환경이 필요하다.[S8][P3]
- 코드 Apache-2.0, 원본 가중치 저작권은 PaddleOCR/Baidu 등으로 분리된다. `MODEL_LICENSES.md`의 명시적 적용 범위는 나열된 기본 모델이며 **한국어 PP-OCRv5 모델을 그 목록에 포함된 것으로 오인하지 않는다**. 한국어 모델 배포 시 해당 PaddleOCR 원본의 조건·변환 출처도 확인해야 한다.[S7][S8]
- RapidOCR README에 공식 ClawHub 스킬 배지가 있으나 조사한 GitHub main 트리에서는 그 스킬의 `SKILL.md`를 확인하지 못했다. **배지만으로 GitHub 스킬의 코드·안전성을 검증했다고 보지 않는다.**[S5]

### Tesseract

- 엔진 및 `tessdata_fast` 언어 데이터는 Apache-2.0. PNG/JPEG/TIFF → UTF-8 텍스트/TSV/hOCR/PDF를 지원한다. 한국어는 `kor.traineddata`, 한영 혼합은 `-l kor+eng`; fast 모델에는 LSTM `--oem 1`을 사용한다.[S11][S12]
- GitHub 파일 메타데이터: fast 한국어 데이터 **1,677,415 bytes**, 영어 **4,113,088 bytes**. 엔진·DLL·선택 라이브러리는 별도이며 총 설치량은 미측정. CPU 로컬 실행이고 PyTorch/ONNX Runtime이 불필요하다.[S12]
- Windows는 공식 Tesseract 문서가 안내하는 **UB Mannheim의 제3자 빌드**를 검토할 수 있다. `pip install pytesseract`는 엔진 설치가 아니다. 직접 CLI를 호출하면 Python 바인딩도 생략 가능. **인라인 이미지 OCR에는 Poppler/Ghostscript가 불필요**하며 PDF 변환을 추가할 때만 별도 검토한다.[S11]
- 시험 명령 예시(이번 조사에서는 실행하지 않음): `tesseract posting.png stdout -l kor+eng --oem 1 --psm 3`. 단일 텍스트 블록에는 `--psm 6`, 흩어진 문구에는 `11`도 비교한다. 긴 공고·장식 글꼴·표의 읽기 순서·작은 글자에서 정확도를 보장하지 않는다. fast는 정확도/속도 절충형이다.[S1][S11][S12]

## 기존 Hermes `pdf` 스킬이면 충분한가?

| 입력 | 판정 |
|---|---|
| 텍스트 레이어 있는 PDF | 기존 PyMuPDF 경로로 충분. OCR 불필요. |
| 스캔 PDF | **절차는 이미 있음**: 소수 쪽은 렌더링+비전, 대량은 Marker. 패키지/모델이 설치됐다는 의미는 아니다.[H1] |
| 저장된 공고 PNG/JPEG | Marker의 `ImageProvider` 및 기존 `extract_marker.py` 입력으로 처리 가능한 경로가 있다. 따라서 새 스킬이 반드시 필요한 것은 아님.[H2][S13] |
| 웹페이지 안의 공고 이미지 | **기존 스킬만으로 수집 자동화까지 완결되지 않음**. DOM 텍스트 우선 → 실제 이미지 수집/영역 캡처 → 로컬 OCR → 출처와 결합하는 연결 작업이 필요. PDF 인쇄 시 축소/잘림보다 원본 이미지 확보가 우선. |

Marker 비용: 설치된 Hermes 참고 문서는 PyTorch+모델 **약 3–5GB**를 예상한다. 이는 스킬의 추정치이지 이 PC 실측이 아니다. 현행 upstream Marker는 Python **3.10+**이므로 프로젝트 3.9에 직접 설치하는 선택은 맞지 않는다. 코드 라이선스와 모델 가중치 라이선스도 다르며 상업 이용 조건을 별도 확인해야 한다.[H1][S13]

## 도입 시 통과 조건 / 미검증 사항

1. 스킬은 실행 코드뿐 아니라 **에이전트 지시문**이다. 고정 커밋으로 검토하고 설치/네트워크/외부 전송 명령은 자동 승인하지 않는다. 인용·재사용 시 MIT/Apache 고지 보존.
2. 이미지 다운로드는 허용 출처·리디렉션·크기·픽셀 수·시간 제한을 두고, 로컬/내부망 URL 접근과 파일명 기반 경로 탈출을 차단. 웹/OCR 텍스트는 명령이 아닌 불신 데이터로 취급.
3. 한국어 공고 표본으로 회사명·직무·자격요건·급여·마감일을 원본과 대조. 낮은 신뢰도뿐 아니라 **높은 신뢰도의 오인식도** 검토. 출처 URL/이미지 식별자/엔진·모델 버전 보존.
4. 이번에는 **소프트웨어/스킬 설치, OCR 실행, 모델 다운로드, 프로젝트 코드 수정 없음**. 엔진별 채용공고 정확도·속도·RAM·총 설치량·전체 의존성/보안 감사는 미검증이다.
5. `web_extract`는 현재 search-only backend 오류로 본문 추출 불가. 검색 스니펫을 근거로 채택하지 않고 `gh api`로 SKILL.md·코드·LICENSE·공식 테스트 원문을 읽었다. 일부 GitHub 검색/경로가 빈 결과 또는 404여서 저장소 트리/릴리스 태그로 재확인했다.

## 출처

- [S1] [TerminalSkills image-to-text SKILL.md (검토 커밋 고정)](https://github.com/TerminalSkills/skills/blob/0abb852010feb21984fa40f0bf52352a440ae6d4/skills/image-to-text/SKILL.md)
- [S2] [동일 저장소 pdf-ocr SKILL.md](https://github.com/TerminalSkills/skills/blob/0abb852010feb21984fa40f0bf52352a440ae6d4/skills/pdf-ocr/SKILL.md), [LICENSE](https://github.com/TerminalSkills/skills/blob/0abb852010feb21984fa40f0bf52352a440ae6d4/LICENSE)
- [S3] [davin51246/pdf-ocr SKILL.md](https://github.com/davin51246/pdf-ocr/blob/17782ff73d0787a7141385bd0f77a0e979c74a93/SKILL.md), [MIT LICENSE](https://github.com/davin51246/pdf-ocr/blob/17782ff73d0787a7141385bd0f77a0e979c74a93/LICENSE)
- [S4] [실제 ocr_image.py](https://github.com/davin51246/pdf-ocr/blob/17782ff73d0787a7141385bd0f77a0e979c74a93/scripts/ocr_image.py)
- [S5] [RapidOCR 공식 README](https://github.com/RapidAI/RapidOCR/blob/main/README.md)
- [S6] [v3.3.0 한국어 테스트](https://github.com/RapidAI/RapidOCR/blob/v3.3.0/python/tests/test_main.py#L207-L222), [릴리스](https://github.com/RapidAI/RapidOCR/releases/tag/v3.3.0)
- [S7] [공식 모델 URL/해시 레지스트리](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml)
- [S8] [RapidOCR Python/라이선스 메타데이터](https://github.com/RapidAI/RapidOCR/blob/main/python/pyproject.toml), [모델 출처·권리 범위](https://github.com/RapidAI/RapidOCR/blob/main/python/MODEL_LICENSES.md), [의존성](https://github.com/RapidAI/RapidOCR/blob/main/python/requirements.txt)
- [S9] [joneshong-skills/ocr SKILL.md](https://github.com/joneshong-skills/ocr/blob/63e53269425fad243eb4b978bcaf6b5bdcf102ba/SKILL.md), [MIT LICENSE](https://github.com/joneshong-skills/ocr/blob/63e53269425fad243eb4b978bcaf6b5bdcf102ba/LICENSE)
- [S10] [OCRskill 외부 API 스킬 원문](https://github.com/MihaiBalint/ocrskill/blob/main/skills/OCR/SKILL.md), [저장소 라이선스 메타데이터](https://api.github.com/repos/MihaiBalint/ocrskill)
- [S11] [Tesseract README](https://github.com/tesseract-ocr/tesseract/blob/main/README.md), [공식 Windows 설치 안내](https://github.com/tesseract-ocr/tessdoc/blob/main/Installation.md#windows)
- [S12] [tessdata_fast README/라이선스](https://github.com/tesseract-ocr/tessdata_fast/blob/main/README.md), [한국어 파일 메타데이터](https://api.github.com/repos/tesseract-ocr/tessdata_fast/contents/kor.traineddata), [영어 파일 메타데이터](https://api.github.com/repos/tesseract-ocr/tessdata_fast/contents/eng.traineddata)
- [S13] [Marker README: 이미지·환경·라이선스](https://github.com/datalab-to/marker/blob/main/README.md), [ImageProvider 코드](https://github.com/datalab-to/marker/blob/main/marker/providers/image.py), [Python 요구사항](https://github.com/datalab-to/marker/blob/main/pyproject.toml)
- [P1] [PyPI RapidOCR 3.3.0 배포 메타데이터](https://pypi.org/pypi/rapidocr/3.3.0/json)
- [P2] [PyPI ONNX Runtime 1.19.2 Windows/Python 3.9 wheel 메타데이터](https://pypi.org/pypi/onnxruntime/1.19.2/json)
- [P3] [PyPI ONNX Runtime 전체 릴리스 파일 목록](https://pypi.org/pypi/onnxruntime/json)
- [H1] 로컬 기존 스킬: `C:/Users/JEG/AppData/Local/hermes/skills/productivity/pdf/references/ocr-extraction.md` (`skill_view`로 확인).
- [H2] 로컬 기존 스크립트: `C:/Users/JEG/AppData/Local/hermes/skills/productivity/pdf/scripts/extract_marker.py` (`skill_view`로 확인).
- [H3] 로컬 기존 스킬: `C:/Users/JEG/AppData/Local/hermes/skills/productivity/pdf/SKILL.md` (`skill_view`로 확인).

[S1]: https://github.com/TerminalSkills/skills/blob/0abb852010feb21984fa40f0bf52352a440ae6d4/skills/image-to-text/SKILL.md
[S2]: https://github.com/TerminalSkills/skills/blob/0abb852010feb21984fa40f0bf52352a440ae6d4/skills/pdf-ocr/SKILL.md
[S3]: https://github.com/davin51246/pdf-ocr/blob/17782ff73d0787a7141385bd0f77a0e979c74a93/SKILL.md
[S4]: https://github.com/davin51246/pdf-ocr/blob/17782ff73d0787a7141385bd0f77a0e979c74a93/scripts/ocr_image.py
[S5]: https://github.com/RapidAI/RapidOCR/blob/main/README.md
[S6]: https://github.com/RapidAI/RapidOCR/blob/v3.3.0/python/tests/test_main.py#L207-L222
[S7]: https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml
[S8]: https://github.com/RapidAI/RapidOCR/blob/main/python/MODEL_LICENSES.md
[S9]: https://github.com/joneshong-skills/ocr/blob/63e53269425fad243eb4b978bcaf6b5bdcf102ba/SKILL.md
[S10]: https://github.com/MihaiBalint/ocrskill/blob/main/skills/OCR/SKILL.md
[S11]: https://github.com/tesseract-ocr/tessdoc/blob/main/Installation.md
[S12]: https://github.com/tesseract-ocr/tessdata_fast/blob/main/README.md
[S13]: https://github.com/datalab-to/marker/blob/main/README.md
[P1]: https://pypi.org/pypi/rapidocr/3.3.0/json
[P2]: https://pypi.org/pypi/onnxruntime/1.19.2/json
[P3]: https://pypi.org/pypi/onnxruntime/json
[H1]: file:///C:/Users/JEG/AppData/Local/hermes/skills/productivity/pdf/references/ocr-extraction.md
[H2]: file:///C:/Users/JEG/AppData/Local/hermes/skills/productivity/pdf/scripts/extract_marker.py
[H3]: file:///C:/Users/JEG/AppData/Local/hermes/skills/productivity/pdf/SKILL.md
