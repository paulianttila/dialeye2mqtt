from mqtt_framework import Framework
from mqtt_framework import Config
from mqtt_framework.callbacks import Callbacks
from mqtt_framework.app import TriggerSource

from prometheus_client import Counter
from flask import render_template

from datetime import datetime
import time
import os
import subprocess

from meter import Meter


class MyConfig(Config):
    def __init__(self):
        super().__init__(self.APP_NAME)

    APP_NAME = "dialeye2mqtt"

    # App specific variables

    IMAGE_URL = None
    TIMEOUT = 5
    CONF_FILE = "/conf/dialEye.conf"
    DATA_FILE = "/data/data.txt"
    M3_INIT_VALUE = 0

    DIALEYE = "/opt/dialEye/dialEye.py"
    DIALEYE_PYTHON = "python3"


class MyApp:
    def init(self, callbacks: Callbacks) -> None:
        self.logger = callbacks.get_logger()
        self.config = callbacks.get_config()
        self.metrics_registry = callbacks.get_metrics_registry()
        self.add_url_rule = callbacks.add_url_rule
        self.publish_value_to_mqtt_topic = callbacks.publish_value_to_mqtt_topic
        self.subscribe_to_mqtt_topic = callbacks.subscribe_to_mqtt_topic
        self.succesfull_fecth_metric = Counter(
            "succesfull_fecth", "", registry=self.metrics_registry
        )
        self.fecth_errors_metric = Counter(
            "fecth_errors", "", registry=self.metrics_registry
        )
        self.exit = False
        self.add_url_rule("/", view_func=self.result_page)
        self.meter = self.init_meter()
        self.logger.debug(f"{self.meter}")

    def get_version(self) -> str:
        return "1.0.1"

    def stop(self) -> None:
        def wait_until(condition, interval=0.1, timeout=1, *args):
            start = time.time()
            while condition(*args) and time.time() - start < timeout:
                time.sleep(interval)

        self.logger.debug("Stopping...")
        self.exit = True
        if self.executing:
            timeout = int(self.config["TIMEOUT"]) + 1
            self.logger.debug("Wait max %d sec to dialEye execution ends...", timeout)
            wait_until(lambda: self.executing, timeout=timeout)

        self.publish_zero_consumption()
        self.logger.debug("Exit")

    def subscribe_to_mqtt_topics(self) -> None:
        pass

    def mqtt_message_received(self, topic: str, message: str) -> None:
        pass

    def do_healthy_check(self) -> bool:
        return True

    # Do work
    def do_update(self, trigger_source: TriggerSource) -> None:
        self.logger.debug(f"Update called, trigger_source={trigger_source}")
        self.executing = True
        try:
            self.update()
        finally:
            self.executing = False

    def update(self) -> None:
        retval, raw = self.get_dialeye_value()
        litre = self.convert_dialeye_value_to_litre(retval, raw)
        if retval == 0 and litre is not None:
            self.succesfull_fecth_metric.inc()
            self.handle_update(litre)
        else:
            self.logger.error(f"DialEye command execution failed: {retval} {raw}")
            self.fecth_errors_metric.inc()
            self.publish_zero_consumption()

    def get_dialeye_value(self) -> tuple[int, str | None]:
        start = time.time()
        retval, result = self.execute_command(
            [
                self.config["DIALEYE_PYTHON"],
                self.config["DIALEYE"],
                "-f",
                self.config["CONF_FILE"],
                "-s",
                "-u",
                "meter",
                self.config["IMAGE_URL"],
            ],
            timeout=self.config["TIMEOUT"],
        )
        end = time.time()
        result = result.strip()

        self.logger.debug(
            "DialEye result (retval=%d, time=%f): %s",
            retval,
            (end - start),
            result,
        )
        return retval, result

    def convert_dialeye_value_to_litre(self, retval: int, value: str) -> float | None:
        return float(value) / 10 if retval == 0 else None

    def handle_update(self, litre: float):
        self.meter.update_litre(litre)
        self.logger.debug(f"{self.meter}")
        self.logger.info(
            "Current value = %.5f m3, consumption = %.2f l/min",
            self.meter.value,
            self.meter.instant_consumption_l_per_min,
        )
        self.store_data(
            self.meter.m3,
            self.meter.m3_already_increased,
            self.meter.value,
        )
        if self.meter.instant_consumption_l_per_min >= 0:
            self.publish_consumption_values(
                self.meter.value,
                self.meter.instant_consumption_l_per_min,
            )
        else:
            self.handle_negative_consumption()

    def handle_negative_consumption(self) -> None:
        self.logger.error(
            "Consuption %.2f l/min is less than 0, ignore update",
            self.meter.instant_consumption_l_per_min,
        )
        self.publish_zero_consumption()

    def execute_command(self, cmd, timeout=5, cwd=None) -> tuple[int, str]:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        return (r.returncode, r.stdout)

    def init_meter(self) -> Meter:
        meter = self.create_meter_from_file_data()
        if meter is None:
            m3 = int(self.config["M3_INIT_VALUE"])
            self.logger.info(f"Initialize m3 to {m3}")
            meter = Meter(m3=m3, m3_already_increased=False, value=float(m3))

        self.logger.info(
            "Initial values: m3=%d, m3_already_increased=%r, value=%f",
            meter.m3,
            meter.m3_already_increased,
            meter.value,
        )
        return meter

    def create_meter_from_file_data(self) -> Meter | None:
        filename = self.config["DATA_FILE"]
        if not os.path.isfile(filename):
            self.logger.info(f"{filename} file does not exists")
            return None
        self.logger.info(f"Initialize data from {filename} file")
        data = self.read_data_file(filename)
        try:
            return self.create_meter_from_string(data)
        except Exception:
            self.logger.info(f"{filename} file content is invalid")
            return None

    def create_meter_from_string(self, data: str) -> Meter:
        m3_str, m3_already_increased_str, value_str = data.strip().split(";")
        return Meter(
            m3=int(m3_str),
            m3_already_increased=eval(m3_already_increased_str),
            value=float(value_str),
        )

    def store_data(self, m3: int, m3_already_increased: bool, current_value: float):
        self.write_data_file(
            self.config["DATA_FILE"],
            "%d;%r;%f" % (m3, m3_already_increased, current_value),
        )

    def read_data_file(self, filename: str) -> str:
        with open(filename, "r+") as file:
            data = file.read().strip()
        return data

    def write_data_file(self, filename: str, data: str) -> None:
        with open(filename, "w+") as file:
            file.seek(0)
            file.write(data)
            file.truncate()

    def publish_consumption_values(
        self, current_value: float, instant_consumption_l_per_min: float
    ) -> None:
        self.publish_value_to_mqtt_topic("value", f"{current_value:.5f}", True)
        self.publish_value_to_mqtt_topic(
            "consumptionLitrePerMin",
            f"{instant_consumption_l_per_min:.2f}",
            True,
        )
        self.publish_value_to_mqtt_topic(
            "lastUpdateTime",
            str(datetime.now().replace(microsecond=0).isoformat()),
            True,
        )

    def publish_zero_consumption(self) -> None:
        self.publish_value_to_mqtt_topic("consumptionLitrePerMin", "0.00", True)
        self.publish_value_to_mqtt_topic(
            "lastUpdateTime",
            str(datetime.now().replace(microsecond=0).isoformat()),
            True,
        )

    def result_page(self) -> str:
        self.update_image()
        return render_template("index.html", current_value_m3=self.meter.value)

    def update_image(self) -> None:
        retval, result = self.execute_command(
            [
                self.config["DIALEYE_PYTHON"],
                self.config["DIALEYE"],
                "-f",
                self.config["CONF_FILE"],
                "-r",
                "-u",
                "meter",
                self.config["IMAGE_URL"],
            ],
            timeout=self.config["TIMEOUT"],
            cwd=self.config["WEB_STATIC_DIR"],
        )
        self.logger.info("Image update result (retval=%d): %s", retval, result)


if __name__ == "__main__":
    Framework().start(MyApp(), MyConfig(), blocked=True)
