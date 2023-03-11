from datetime import datetime, timedelta
import pytest

from meter import Meter

def test_normal_flow():
    meter = Meter(m3=1234, m3_already_increased=False, value=1234.123)
    
    meter.update_litre(200.0)
    assert meter.m3 == 1234
    assert meter.m3_already_increased is False
    assert meter.value == 1234.200
    assert meter.instant_consumption_l_per_min == 0

    # emulate 30 sec update interval to get instant value update
    meter._current_value.time = datetime.now() - timedelta(seconds = 30)

    meter.update_litre(201.0)
    assert meter.m3 == 1234
    assert meter.m3_already_increased is False
    assert meter.value == 1234.201
    assert meter.instant_consumption_l_per_min == pytest.approx(2.0)

    # emulate 60 sec update interval to get instant value update
    meter._current_value.time = datetime.now() - timedelta(seconds = 60)

    meter.update_litre(423.1)
    assert meter.m3 == 1234
    assert meter.m3_already_increased is False
    assert meter.value == 1234.4231
    assert meter.instant_consumption_l_per_min == pytest.approx(221.1, 0.01)

    # emulate 60 sec update interval to get instant value update
    meter._current_value.time = datetime.now() - timedelta(seconds = 60)

    meter.update_litre(714.1)
    assert meter.m3 == 1234
    assert meter.m3_already_increased is False
    assert meter.value == 1234.7141
    assert meter.instant_consumption_l_per_min == pytest.approx(291.0, 0.01)

    # emulate 60 sec update interval to get instant value update
    meter._current_value.time = datetime.now() - timedelta(seconds = 60)

    meter.update_litre(020.5)
    assert meter.m3 == 1235
    assert meter.m3_already_increased is True
    assert meter.value == 1235.0205
    assert meter.instant_consumption_l_per_min == pytest.approx(306.4, 0.01)

    # emulate 60 sec update interval to get instant value update
    meter._current_value.time = datetime.now() - timedelta(seconds = 60)

    meter.update_litre(423.5)
    assert meter.m3 == 1235
    assert meter.m3_already_increased is False
    assert meter.value == 1235.4235
    assert meter.instant_consumption_l_per_min == pytest.approx(403.0, 0.01)

def test_back_flow():
    meter = Meter(m3=1234, m3_already_increased=False, value=1234.123)

    meter.update_litre(121.4)
    assert meter.m3 == 1234
    assert meter.m3_already_increased is False
    assert meter.value == 1234.1214
    assert meter.instant_consumption_l_per_min == 0

    # emulate 60 sec update interval to get instant value update
    meter._current_value.time = datetime.now() - timedelta(seconds = 60)

    meter.update_litre(123.1)
    assert meter.m3 == 1234
    assert meter.m3_already_increased is False
    assert meter.value == 1234.1231
    assert meter.instant_consumption_l_per_min == pytest.approx(1.7, 0.01)
