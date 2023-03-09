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
        self.init_values(self.config["DATA_FILE"])
        self.add_url_rule("/", view_func=self.result_page)

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
        self.logger.debug("update called, trigger_source=%s", trigger_source)

        self.executing = True
        try:
            self.update()
        finally:
            self.executing = False

    def update(self):
        retval, litre = self.get_dialeye_value()

        if retval == 0:
            self.succesfull_fecth_metric.inc()
            current_value, consumption = self.calc_values(litre)

            if litre < 100 and self.already_increased == False:
                current_value, consumption = self.inc_m3_and_calc_values(litre)
                self.already_increased = True
            elif litre >= 400 and litre < 700 and self.already_increased == True:
                self.logger.info("Cleared already_increased flag")
                self.already_increased = False

            self.logger.debug(
                "m3=%d, litre=%.2f, already_increased=%r, previous_value=%.5f m3, current_value=%.5f m3, consumption=%.2f l",
                self.m3,
                litre,
                self.already_increased,
                self.previous_value,
                current_value,
                consumption,
            )

            if consumption >= 0:
                instant_consumption_l_per_min = self.calc_instant_consumtion(
                    consumption
                )
                self.logger.info(
                    "Current value = %.5f m3, consumption = %.2f l/min (%.2f l)",
                    current_value,
                    instant_consumption_l_per_min,
                    consumption,
                )
                self.publish_values(current_value, instant_consumption_l_per_min)
            else:
                self.logger.error(
                    "Consuption %.2f is less than 0, ignore update (current_value=%.5f m3, previous_value=%.5f m3)",
                    consumption,
                    current_value,
                    self.previous_value,
                )
                self.publish_zero_consumption()

            self.write_data_file(
                self.config["DATA_FILE"],
                "%d;%r;%f" % (self.m3, self.already_increased, current_value),
            )
            self.previous_value = current_value
        else:
            self.fecth_errors_metric.inc()
            self.logger.error("DialEye command execution failed: %d", retval)
            self.publish_zero_consumption()

    def get_dialeye_value(self):
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
        self.logger.debug(
            "DialEye result (retval=%d, time=%f): %s", retval, (end - start), result
        )
        litre = None
        if retval == 0:
            litre = round(float(result) / 10, 2)
        return retval, litre

    def calc_instant_consumtion(self, consumption):
        now = time.time()
        instant_consumption_l_per_min = 0
        if consumption > 0 and self.previous_time > 0:
            instant_consumption_l_per_min = (
                consumption / (now - self.previous_time) * 60
            )
        self.previous_time = now
        return instant_consumption_l_per_min

    def inc_m3_and_calc_values(self, litre):
        self.logger.info("Increase %d m3 by one to %d", self.m3, self.m3 + 1)
        self.m3 = self.m3 + 1
        return self.calc_values(litre)

    def calc_values(self, litre):
        current_value = self.m3 + litre / 1000
        consumption = (current_value - self.previous_value) * 1000  # litre
        return current_value, consumption

    def result_page(self):
        self.update_image()
        return render_template("index.html", current_value_m3=self.previous_value)

    def update_image(self):
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

    def execute_command(self, cmd, timeout=5, cwd=None):
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        return (r.returncode, r.stdout)

    def read_data_file(self, filename):
        file = open(filename, "r+")
        data = file.read().strip()
        file.close()
        return data

    def write_data_file(self, filename, data):
        file = open(filename, "w+")
        file.seek(0)
        file.write(data)
        file.truncate()
        file.close()

    def init_values(self, filename):
        if os.path.isfile(filename):
            self.logger.info("Initialize data from %s file", filename)
            data = self.read_data_file(filename)
            m3_str, already_increased_str, previous_value_str = data.strip().split(";")
            self.m3 = int(m3_str)
            self.already_increased = eval(already_increased_str)
            self.previous_value = float(previous_value_str)
        else:
            self.logger.info("%s file does not exists, initialize variables", filename)
            self.m3 = int(self.config["M3_INIT_VALUE"])

        self.logger.info(
            "Initial values: m3=%d, already_increased=%r, previous_value=%f",
            self.m3,
            self.already_increased,
            self.previous_value,
        )

    def publish_values(self, current_value_m3, instant_consumption_l_per_min):
        self.publish_value_to_mqtt_topic("value", current_value_m3, True)
        self.publish_value_to_mqtt_topic(
            "consumptionLitrePerMin",
            float("{0:.2f}".format(instant_consumption_l_per_min)),
            True,
        )
        self.publish_value_to_mqtt_topic(
            "lastUpdateTime",
            str(datetime.now().replace(microsecond=0).isoformat()),
            True,
        )

    def publish_zero_consumption(self):
        self.publish_value_to_mqtt_topic(
            "consumptionLitrePerMin", float("{0:.2f}".format(0)), True
        )
        self.publish_value_to_mqtt_topic(
            "lastUpdateTime",
            str(datetime.now().replace(microsecond=0).isoformat()),
            True,
        )


if __name__ == "__main__":
    Framework().start(MyApp(), MyConfig(), blocked=True)
