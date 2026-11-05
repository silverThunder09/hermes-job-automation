from .base import ManualOnlyCollector


class JobKoreaCollector(ManualOnlyCollector):
    platform = "잡코리아"

    def __init__(self, settings):
        super().__init__(
            "개인용 수집 DB에 대한 공식 API 허용을 확인하지 못해 자동 수집은 중지했습니다. "
            "공고는 브라우저에서 직접 확인하고 사용자가 승인한 내보내기 파일만 가져옵니다."
        )
