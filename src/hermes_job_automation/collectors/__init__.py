from .groupby import GroupByCollector
from .jikhaeng import JikhaengCollector
from .jobkorea import JobKoreaCollector
from .jumpit import JumpitCollector
from .rocketpunch import RocketpunchCollector
from .saramin import SaraminCollector
from .wanted import WantedCollector


def all_collectors(settings):
    return [
        SaraminCollector(settings),
        JobKoreaCollector(settings),
        WantedCollector(settings),
        JumpitCollector(settings),
        JikhaengCollector(settings),
        RocketpunchCollector(settings),
        GroupByCollector(settings),
    ]


__all__ = ["all_collectors"]
