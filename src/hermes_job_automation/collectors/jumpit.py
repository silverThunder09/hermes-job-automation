from .base import ManualOnlyCollector


class JumpitCollector(ManualOnlyCollector):
    platform = "점핏"

    def __init__(self, settings):
        super().__init__(
            "공식 API 사용 승인이 확인되지 않았습니다. 공고 상세의 접수 상태를 직접 확인한 뒤 가져옵니다."
        )
