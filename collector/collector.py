
import os
import json
import time
import logging

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collector")

REQUIRED = {
    "device_id": str, "boot_id": int, "sequence": int, "ts_ms": int,
    "temperature": float, "humidity": float, "light": int,
    "distance_cm": float, "rssi": int, "uptime_s": int,
}

RANGES = {
    "temperature": (-40, 80), "humidity": (0, 100),
    "light": (0, 4095), "distance_cm": (2, 400),
}

stats = {"received": 0, "valid": 0, "invalid": 0, "written": 0,
         "write_errors": 0, "lost": 0, "duplicates": 0}
last_seq = {} 

HOST = os.getenv("MQTT_HOST")
PORT = int(os.getenv("MQTT_PORT"))
TOPIC = os.getenv("MQTT_TOPIC")
BUCKET_RAW = os.getenv("INFLUX_BUCKET_RAW")

influx = InfluxDBClient(url=os.getenv("INFLUX_URL"), token=os.getenv("INFLUX_TOKEN"),
                        org=os.getenv("INFLUX_ORG"))
write_api = influx.write_api(write_options=SYNCHRONOUS)


def validate(data):
    """Trả về None nếu hợp lệ, hoặc chuỗi lý do nếu lỗi."""
    for name, typ in REQUIRED.items():
        if name not in data:
            return f"thieu field {name}"
        v = data[name]
        if isinstance(v, bool):
            return f"sai kieu {name}"
        ok = isinstance(v, (int, float)) if typ is float else isinstance(v, typ)
        if not ok:
            return f"sai kieu {name}"
    for name, (lo, hi) in RANGES.items():
        if not lo <= data[name] <= hi:
            return f"{name} ngoai khoang: {data[name]}"
    return None


def on_connect(client, userdata, flags, reason_code, properties):
    log.info("Da ket noi, ma: %s", reason_code)
    client.subscribe(TOPIC, qos=1)


def on_message(client, userdata, msg):
    recv_ms = time.time_ns() // 1_000_000
    stats["received"] += 1

    try:
        data = json.loads(msg.payload.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        stats["invalid"] += 1
        log.warning("JSON hong: %r", msg.payload[:80])
        return

    reason = validate(data) if isinstance(data, dict) else "khong phai object"
    if reason:
        stats["invalid"] += 1
        log.warning("Bo qua goi: %s", reason)
        return
    stats["valid"] += 1

    dev, boot, seq = data["device_id"], data["boot_id"], data["sequence"]
    prev = last_seq.get(dev)
    if prev is not None:
        prev_boot, prev_seq = prev
        if boot != prev_boot:
            log.info("Thiet bi %s reboot (boot_id moi)", dev)
        elif seq > prev_seq + 1:
            n = seq - prev_seq - 1
            stats["lost"] += n
            log.warning("Mat %d goi (seq %d -> %d)", n, prev_seq, seq)
        elif seq <= prev_seq:
            stats["duplicates"] += 1
            log.warning("Goi trung/tre: seq=%d (da co %d)", seq, prev_seq)
    last_seq[dev] = (boot, seq)

    try:
        point = (
            Point("sensor_raw")
            .tag("device_id", dev)
            .field("temperature", float(data["temperature"]))
            .field("humidity", float(data["humidity"]))
            .field("distance_cm", float(data["distance_cm"]))
            .field("light", int(data["light"]))
            .field("rssi", int(data["rssi"]))
            .field("sequence", int(seq))
            .field("boot_id", int(boot))
            .field("uptime_s", int(data["uptime_s"]))
            .time(data["ts_ms"], WritePrecision.MS)
        )
        write_api.write(bucket=BUCKET_RAW, record=point)
        stats["written"] += 1
    except Exception as e:
        stats["write_errors"] += 1
        log.error("Loi ghi DB: %s", e)
        return

    done_ms = time.time_ns() // 1_000_000
    mqtt_ms = recv_ms - data["ts_ms"]
    db_ms = done_ms - recv_ms
    e2e_ms = done_ms - data["ts_ms"]
    try:
        lat = (
            Point("latency").tag("device_id", dev)
            .field("mqtt_ms", int(mqtt_ms)).field("db_ms", int(db_ms))
            .field("e2e_ms", int(e2e_ms)).time(data["ts_ms"], WritePrecision.MS)
        )
        write_api.write(bucket=BUCKET_RAW, record=lat)
    except Exception as e:
        log.error("Loi ghi latency: %s", e)

    log.info("OK %s seq=%s temp=%.1f | mqtt=%dms db=%dms e2e=%dms | %s",
             dev, seq, data["temperature"], mqtt_ms, db_ms, e2e_ms, stats)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tuyen911-collector-01")
client.on_connect = on_connect
client.on_message = on_message
client.connect(HOST, PORT)
client.loop_forever()