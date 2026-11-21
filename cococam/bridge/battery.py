"""Cache read-only CloudEdge telemetry and optionally publish it through MQTT."""

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone

from .cloud import cloud_client, select_camera

LOGGER = logging.getLogger(__name__)
INTERVAL = 30 * 60


def parse_battery(values):
    if not isinstance(values, dict):
        return None
    def field(code):
        value = values.get(code, values.get(int(code)))
        if isinstance(value, dict):
            value = value.get("value")
        if type(value) is int or isinstance(value, str) and value.isdecimal():
            return int(value)
        return None

    percent, charging = field("154"), field("156")
    if percent is None or not 0 <= percent <= 100:
        return None
    return {
        "percent": percent,
        "charging": charging == 1 if charging in (0, 1) else None,
    }


class Battery:
    def __init__(self, config, path):
        self.config = config
        self.path = path
        self.account = hashlib.sha256(json.dumps(
            [config.get(key) for key in ("email", "country", "phone_code", "camera_name")],
        ).encode()).hexdigest()
        self.sample = None
        try:
            data = json.loads(path.read_text()) if path else {}
            if data.get("account") == self.account:
                sample = data["sample"]
                if (type(sample["percent"]) is int and 0 <= sample["percent"] <= 100
                        and sample["charging"] in (True, False, None)
                        and isinstance(sample["observed_at"], str)):
                    self.sample = sample
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            pass

    def read(self):
        api, _ = cloud_client(self.config)
        api.login()
        device = select_camera(api, self.config)
        serial = device.get("snNum") if device else None
        if not serial:
            return None
        values = api.get_battery_info(serial)
        if not values and api.openapi_server:
            values = api.get_device_iot_config(serial)
        data = parse_battery(values)
        if data is None:
            return None
        return data | {
            "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "device_id": hashlib.sha256(serial.encode()).hexdigest()[:16],
        }

    def snapshot(self):
        if self.sample is None:
            return None
        return {key: self.sample[key] for key in ("percent", "charging", "observed_at")}

    def save(self, sample):
        self.sample = sample
        if self.path:
            try:
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(json.dumps({"account": self.account, "sample": sample}))
                temporary.replace(self.path)
            except OSError:
                LOGGER.warning("Impossible d’enregistrer la mesure de batterie COCOCAM")

    async def poll(self, http, session):
        while True:
            if not session.task:
                try:
                    sample = await asyncio.to_thread(self.read)
                except PermissionError:
                    LOGGER.warning("Connexion CloudEdge refusée pour la batterie COCOCAM")
                    return
                except Exception as error:
                    LOGGER.warning("Lecture de la batterie COCOCAM indisponible (%s)", type(error).__name__)
                else:
                    if sample is not None:
                        self.save(sample)
                        LOGGER.info("Batterie COCOCAM lue auprès de CloudEdge : %s %%", sample["percent"])
                        if self.config.get("battery_mqtt"):
                            await publish_mqtt(http, sample)
                    else:
                        LOGGER.warning("CloudEdge n’a pas fourni de niveau de batterie COCOCAM")
            await asyncio.sleep(INTERVAL)


async def publish_mqtt(http, sample):
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        return
    try:
        async with http.get("http://supervisor/services/mqtt",
                            headers={"Authorization": f"Bearer {token}"}) as response:
            response.raise_for_status()
            service = (await response.json())["data"]
        await asyncio.to_thread(send_mqtt, service, sample)
    except Exception as error:
        LOGGER.warning("Publication MQTT de la batterie indisponible (%s)", type(error).__name__)


def send_mqtt(service, sample):
    from paho.mqtt import client as mqtt

    identity = f"cococam_{sample['device_id']}"
    state_topic = f"cococam/{identity}/battery"
    discovery = {
        "name": "Batterie",
        "unique_id": f"{identity}_battery",
        "state_topic": state_topic,
        "value_template": "{{ value_json.percent }}",
        "json_attributes_topic": state_topic,
        "json_attributes_template": "{{ {'observed_at': value_json.observed_at, 'charging': value_json.charging} | tojson }}",
        "device_class": "battery",
        "state_class": "measurement",
        "unit_of_measurement": "%",
        "device": {"identifiers": [identity], "name": "COCOCAM", "manufacturer": "COCOCAM"},
    }
    protocol = mqtt.MQTTv31 if service.get("protocol") == "3.1" else mqtt.MQTTv311
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=protocol)
    if service.get("username"):
        client.username_pw_set(service["username"], service.get("password"))
    if service.get("ssl"):
        client.tls_set()
    client.connect(service["host"], int(service["port"]))
    client.loop_start()
    try:
        state = {key: sample[key] for key in ("percent", "charging", "observed_at")}
        for topic, value in (
            (f"homeassistant/sensor/{identity}/battery/config", discovery),
            (state_topic, state),
        ):
            message = client.publish(topic, json.dumps(value), qos=1, retain=True)
            message.wait_for_publish(timeout=5)
            if not message.is_published():
                raise TimeoutError("MQTT publication timed out")
    finally:
        client.disconnect()
        client.loop_stop()
