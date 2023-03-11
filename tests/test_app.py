from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pytest
from src.app import MyApp
from mqtt_framework.app import TriggerSource


class TestSuccesfullCase(TestCase):
    @patch.object(MyApp, "get_dialeye_value")
    @patch.object(MyApp, "write_data_file")
    @patch.object(MyApp, "read_data_file")
    @patch.object(MyApp, "publish_consumption_values")
    @patch.object(MyApp, "publish_zero_consumption")
    @patch("os.path.isfile")
    def test_app(
        self,
        mock_os_path_isfile,
        mock_publish_zero_consumption,
        mock_publish_consumption_values,
        mock_read_data_file,
        mock_write_data_file,
        mock_get_dialeye_value,
    ):
        # Mock
        mock_get_dialeye_value.return_value = (0, "5691")
        mock_read_data_file.return_value = "5;True;5.567000"
        mock_os_path_isfile.return_value = True

        m = MagicMock()
        m.get_config.return_value = {
            "DATA_FILE": "dummy_file",
            "M3_INIT_VALUE": "1234",
        }

        # Execute app
        app = MyApp()
        app.init(m)
        # emulate 30 sec update interval to get instant value update
        app.meter._current_value.time = datetime.now() - timedelta(seconds = 30)
        app.do_update(TriggerSource.INTERVAL)

        # Verify
        mock_get_dialeye_value.assert_called_once()
        mock_read_data_file.assert_called_once()
        mock_publish_zero_consumption.assert_not_called()
        mock_publish_consumption_values.assert_called_once_with(
            5.5691, pytest.approx(4.2, 0.01)
        )
        mock_write_data_file.assert_called_once_with("dummy_file", "5;False;5.569100")


class TestRollover(TestCase):
    @patch.object(MyApp, "get_dialeye_value")
    @patch.object(MyApp, "write_data_file")
    @patch.object(MyApp, "read_data_file")
    @patch.object(MyApp, "publish_consumption_values")
    @patch.object(MyApp, "publish_zero_consumption")
    @patch("os.path.isfile")
    def test_app(
        self,
        mock_os_path_isfile,
        mock_publish_zero_consumption,
        mock_publish_consumption_values,
        mock_read_data_file,
        mock_write_data_file,
        mock_get_dialeye_value,
    ):
        # Mock
        mock_get_dialeye_value.return_value = (0, "00012")
        mock_read_data_file.return_value = "5;False;5.99900"
        mock_os_path_isfile.return_value = True

        # Execute app
        app = MyApp()
        m = MagicMock()
        m.get_config.return_value = {
            "DATA_FILE": "dummy_file",
            "M3_INIT_VALUE": "1234",
        }
        app.init(m)
        # emulate 30 sec update interval to get instant value update
        app.meter._current_value.time = datetime.now() - timedelta(seconds = 30)
        app.do_update(TriggerSource.INTERVAL)

        # Verify
        mock_get_dialeye_value.assert_called_once()
        mock_read_data_file.assert_called_once()
        mock_publish_zero_consumption.assert_not_called()
        mock_publish_consumption_values.assert_called_once_with(
            6.0012, pytest.approx(4.4, 0.01)
        )
        mock_write_data_file.assert_called_once_with("dummy_file", "6;True;6.001200")


class TestFailedDialEyeExecution(TestCase):
    @patch.object(MyApp, "get_dialeye_value")
    @patch.object(MyApp, "write_data_file")
    @patch.object(MyApp, "read_data_file")
    @patch.object(MyApp, "publish_consumption_values")
    @patch.object(MyApp, "publish_zero_consumption")
    @patch("os.path.isfile")
    def test_app(
        self,
        mock_os_path_isfile,
        mock_publish_zero_consumption,
        mock_publish_consumption_values,
        mock_read_data_file,
        mock_write_data_file,
        mock_get_dialeye_value,
    ):
        # Mock
        mock_get_dialeye_value.return_value = (1, "")
        mock_read_data_file.return_value = "5;True;5.567000"
        mock_os_path_isfile.return_value = True

        # Execute app
        app = MyApp()
        m = MagicMock()
        m.get_config.return_value = {
            "DATA_FILE": "dummy_file",
            "M3_INIT_VALUE": "1234",
        }
        app.init(m)
        app.do_update(TriggerSource.INTERVAL)

        # Verify
        mock_get_dialeye_value.assert_called_once()
        mock_read_data_file.assert_called_once()
        mock_publish_zero_consumption.assert_called_once()
        mock_publish_consumption_values.assert_not_called()
        mock_write_data_file.assert_not_called()


class TestEmptyDataFile(TestCase):
    @patch.object(MyApp, "get_dialeye_value")
    @patch.object(MyApp, "write_data_file")
    @patch.object(MyApp, "read_data_file")
    @patch.object(MyApp, "publish_consumption_values")
    @patch.object(MyApp, "publish_zero_consumption")
    @patch("os.path.isfile")
    def test_app(
        self,
        mock_os_path_isfile,
        mock_publish_zero_consumption,
        mock_publish_consumption_values,
        mock_read_data_file,
        mock_write_data_file,
        mock_get_dialeye_value,
    ):
        # Mock
        mock_get_dialeye_value.return_value = (0, "5678.1")
        mock_read_data_file.return_value = "----"
        mock_os_path_isfile.return_value = False

        # Execute app
        app = MyApp()
        m = MagicMock()
        m.get_config.return_value = {
            "DATA_FILE": "dummy_file",
            "M3_INIT_VALUE": "1234",
        }
        app.init(m)
        app.do_update(TriggerSource.INTERVAL)

        # Verify
        mock_get_dialeye_value.assert_called_once()
        mock_read_data_file.assert_not_called()
        mock_publish_zero_consumption.assert_not_called()
        mock_publish_consumption_values.assert_called_once_with(1234.56781, 0)
        mock_write_data_file.assert_called_once_with(
            "dummy_file", "1234;False;1234.567810"
        )
