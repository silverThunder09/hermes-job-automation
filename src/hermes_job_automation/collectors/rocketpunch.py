from .base import ManualOnlyCollector


class RocketpunchCollector(ManualOnlyCollector):
    platform = "로켓펀치"

    def __init__(self, settings):
        super().__init__(
            "공식 채용 API와 자동 접근 허용 조건을 확인하지 못했습니다. 사용자가 직접 확인한 공고만 가져옵니다."
        )
