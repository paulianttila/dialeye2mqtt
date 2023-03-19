from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Value:
    value: float = 0
    time: datetime = 0


@dataclass
class Meter:
    value: float
    m3: int
    m3_already_increased: bool
    instant_consumption_l_per_min: float = 0

    _current_value: Value = field(default_factory=Value)
    _previous_value: Value = field(default_factory=Value)
    _litre: float = 0
    _instant_consumption_l: float = 0

    def __post_init__(self):
        self._current_value.value = self.value

    def update_litre(self, litre: float) -> None:
        if litre < 100 and self.m3_already_increased is False:
            self.m3 = self.m3 + 1
            self._update_current_value(litre)
            self.m3_already_increased = True
        elif litre >= 400 and litre < 700 and self.m3_already_increased is True:
            self._update_current_value(litre)
            self.m3_already_increased = False
        else:
            self._update_current_value(litre)
        self._calc_instant_consumtion()
        self._round()

    def _update_current_value(self, litre):
        self._previous_value.value = self._current_value.value
        self._previous_value.time = self._current_value.time
        self._current_value.value = self.m3 + litre / 1000
        self._current_value.time = datetime.now()
        self._litre = litre
        self.value = self._current_value.value

    def _calc_instant_consumtion(self):
        if self._previous_value.time == 0:
            return

        self._instant_consumption_l = (
            self._current_value.value - self._previous_value.value
        ) * 1000
        delta_time_s = self._get_delta_between_times(
            self._current_value.time, self._previous_value.time
        )
        self.instant_consumption_l_per_min = (
            self._instant_consumption_l / delta_time_s * 60
        )

    def _get_delta_between_times(self, time1: datetime, time2: datetime) -> float:
        return (time1 - time2).total_seconds()

    def _round(self) -> None:
        self.value = round(self.value, 5)
        self.instant_consumption_l_per_min = round(
            self.instant_consumption_l_per_min, 2
        )
        self._litre = round(self._litre, 2)
        self._instant_consumption_l = round(self._instant_consumption_l, 2)
        self._instant_consumption_l += 0.0  # remove possible negative -0.00
        self._current_value.value = round(self._current_value.value, 5)
        self._previous_value.value = round(self._previous_value.value, 5)
