# dialeye2mqtt

Dockerized dialEye with MQTT broker interface.

Use [olammi dialEye](https://olammi.iki.fi/sw/dialEye/) to read rotary utility meter dials using image recognition.

## Environament variables

See commonn environment variables from [MQTT-Framework](https://github.com/paulianttila/MQTT-Framework).

| **Variable**       | **Default**         | **Descrition**                                                          |
|--------------------|---------------------|-------------------------------------------------------------------------|
| CFG_APP_NAME       | dialeye2mqtt        | Name of the app.                                                        |
| CFG_IMAGE_URL      |                     | Url where to fetch image of the meter.                                  |
| CFG_CONF_FILE      | /conf/dialEye.conf  | Path for dialEye.conf                                                   |
| CFG_DATA_FILE      | /data/data.txt      | Path for data file                                                      |
| CFG_TIMEOUT        | 5                   | Timeout for dialEye command.                                            |
| CFG_M3_INIT_VALUE  | 0                   | Initialization value for m3. Used when data file doesn't exists yet.    |

## Example docker-compose.yaml

```yaml
version: "3.5"

services:
  dialeye2mqtt:
    container_name: dialeye2mqtt
    image: paulianttila/dialeye2mqtt:2.0.0
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    environment:
      - CFG_LOG_LEVEL=DEBUG
      - CFG_MQTT_BROKER_URL=127.0.0.1
      - CFG_MQTT_BROKER_PORT=1883
      - CFG_IMAGE_URL=<url>
    volumes:
      - ./dialEye.conf:/conf/dialEye.conf:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/healthy"]
      interval: 60s
      timeout: 3s
      start_period: 5s
      retries: 3
 ```

 ## Configure dialEye

 See details from [dialEye howto](https://olammi.iki.fi/sw/dialEye/howto.php).

 ### Calibration image

 Image for current calibration is available via index.html page.
