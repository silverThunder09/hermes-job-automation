from .base import ManualOnlyCollector


class WantedCollector(ManualOnlyCollector):
    platform = "원티드"

    def __init__(self, settings):
        super().__init__(
            "공식 개인용 채용 API 또는 자동 접근 허용 근거가 설정되지 않았습니다. "
            "현재는 사용자가 승인한 공고 내보내기만 가져옵니다."
        )
