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
    DIALEYE_PYTHON = "python2"


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
        self.previous_time = 0
        self.m3 = 0
        self.previous_value = 0
        self.already_increased = False
        self.add_url_rule("/", view_func=self.result_page)
        self.init_values()

    def get_version(self) -> str:
        return "1.0.0"

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
        litre = self.convert_dialeye_value(retval, raw)
        if retval == 0 and litre is not None:
            self.succesfull_fecth_metric.inc()
            self.handle_dialeye_value(litre)
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

    def convert_dialeye_value(self, retval: int, value: str) -> float | None:
        return round(float(value) / 10, 2) if retval == 0 else None
        
    def handle_dialeye_value(self, litre: float) -> None:
        current_value, consumption = self.check_rollover(litre)
        if consumption >= 0:
            self.handle_consumption(current_value, consumption)
        else:
            self.handle_negative_consumption(current_value, consumption)

        self.store_data(current_value)
        self.previous_value = current_value
        self.logger.debug(
            "m3=%d, litre=%.2f, already_increased=%r, previous_value=%.5f m3"
            ", current_value=%.5f m3, consumption=%.2f l",
            self.m3,
            litre,
            self.already_increased,
            self.previous_value,
            current_value,
            consumption,
        )

    def check_rollover(self, litre: float) -> tuple[float, float]:
        current_value, consumption = self.calc_values(litre)

        if litre < 100 and self.already_increased is False:
            current_value, consumption = self.inc_m3_and_calc_values(litre)
            self.already_increased = True
        elif litre >= 400 and litre < 700 and self.already_increased is True:
            self.logger.info("Cleared already_increased flag")
            self.already_increased = False
        return current_value, consumption

    def handle_consumption(self, current_value: float, consumption: float) -> None:
        consumption_l_per_min = self.calc_instant_consumtion(consumption)
        self.logger.info(
            "Current value = %.5f m3, consumption = %.2f l/min (%.2f l)",
            current_value,
            consumption_l_per_min,
            consumption,
        )
        self.publish_consumption_values(current_value, consumption_l_per_min)

    def handle_negative_consumption(
        self, current_value: float, consumption: float
    ) -> None:
        self.logger.error(
            "Consuption %.2f is less than 0, ignore update "
            "(current_value=%.5f m3, previous_value=%.5f m3)",
            consumption,
            current_value,
            self.previous_value,
        )
        self.publish_zero_consumption()

    def calc_instant_consumtion(self, consumption) -> float:
        now = time.time()
        instant_consumption_l_per_min = 0
        if consumption > 0 and self.previous_time > 0:
            instant_consumption_l_per_min = round(
                (consumption / (now - self.previous_time) * 60), 2
            )
        self.previous_time = now
        return instant_consumption_l_per_min

    def inc_m3_and_calc_values(self, litre) -> tuple[float, float]:
        self.logger.info("Increase %d m3 by one to %d", self.m3, self.m3 + 1)
        self.m3 = self.m3 + 1
        return self.calc_values(litre)

    def calc_values(self, litre) -> tuple[float, float]:
        current_value = self.m3 + round(litre / 1000, 5)
        consumption = (current_value - self.previous_value) * 1000  # litre
        return current_value, consumption

    def execute_command(self, cmd, timeout=5, cwd=None) -> tuple[int, str]:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        return (r.returncode, r.stdout)

    def init_values(self) -> None:
        if not self.read_data():
            self.m3 = int(self.config["M3_INIT_VALUE"])
            self.logger.info(f"Initialize m3 to {self.m3}")

        self.logger.info(
            "Initial values: m3=%d, already_increased=%r, previous_value=%f",
            self.m3,
            self.already_increased,
            self.previous_value,
        )

    def read_data(self) -> bool:
        filename = self.config["DATA_FILE"]
        if not os.path.isfile(filename):
            self.logger.info(f"{filename} file does not exists")
            return False
        self.logger.info(f"Initialize data from {filename} file")
        data = self.read_data_file(filename)
        if len(data) == 0:
            return False
        try:
            m3_str, already_increased_str, previous_value_str = data.strip().split(";")
            self.m3 = int(m3_str)
            self.already_increased = eval(already_increased_str)
            self.previous_value = float(previous_value_str)
        except Exception:
            self.logger.info(f"{filename} file content is invalid")
            return False
        return True

    def store_data(self, current_value: float):
        self.write_data_file(
            self.config["DATA_FILE"],
            "%d;%r;%f" % (self.m3, self.already_increased, current_value),
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
        self, current_value_m3: float, instant_consumption_l_per_min: float
    ) -> None:
        self.publish_value_to_mqtt_topic("value", current_value_m3, True)
        self.publish_value_to_mqtt_topic(
            "consumptionLitrePerMin",
            instant_consumption_l_per_min,
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
        return render_template("index.html", current_value_m3=self.previous_value)

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
