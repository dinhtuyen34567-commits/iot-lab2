"""Giả lập thiết bị thứ hai (esp32-sim) gửi dữ liệu có nhiễu, rơi gói, outlier, gửi trùng.

Chạy:  python simulator/fake_publisher.py --interval 1 --count 600
"""
import os
import json
import time
import math
import random
import argparse

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
PORT = int(os.getenv("MQTT_PORT", "1883"))
DEVICE_ID = "esp32-sim"
TOPIC = f"ptit/lab2/tuyen911/{DEVICE_ID}/sensors"

parser = argparse.ArgumentParser()
parser.add_argument("--interval", type=float, default=1.0, help="giay giua 2 goi")
parser.add_argument("--count", type=int, default=600, help="tong so goi")
parser.add_argument("--drop", type=float, default=0.05, help="xac suat roi goi")
parser.add_argument("--outlier", type=float, default=0.03, help="xac suat outlier")
parser.add_argument("--dup", type=float, default=0.02, help="xac suat gui trung")
args = parser.parse_args()


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tuyen911-sim-01")
client.connect(HOST, PORT)
client.loop_start()

boot_id = random.getrandbits(32)
sent = dropped = outliers = dups = 0
gap_until = -1  # một khoảng trống dài để demo xử lý giá trị thiếu
gap_start = random.randint(args.count // 3, args.count // 2)

print(f"Gui {args.count} goi vao {TOPIC} (moi {args.interval}s)")
for i in range(1, args.count + 1):
    temperature = 27 + 3 * math.sin(2 * math.pi * i / 200) + random.gauss(0, 0.3)
    humidity = 60 - 8 * math.sin(2 * math.pi * i / 200) + random.gauss(0, 1)
    light = 2000 + 1500 * math.sin(2 * math.pi * i / 300) + random.gauss(0, 50)
    distance = 100 + random.gauss(0, 2)

    # outlier (vẫn nằm trong khoảng hợp lệ của collector)
    if random.random() < args.outlier:
        kind = random.choice(["temp", "hum", "light"])
        if kind == "temp":
            temperature += random.uniform(20, 40)
        elif kind == "hum":
            humidity = clamp(humidity + random.uniform(25, 35), 0, 100)
        else:
            light = random.choice([0, 4095])
        outliers += 1

    payload = {
        "device_id": DEVICE_ID,
        "boot_id": boot_id,
        "sequence": i,
        "ts_ms": time.time_ns() // 1_000_000,
        "temperature": round(clamp(temperature, -40, 80), 2),
        "humidity": round(clamp(humidity, 0, 100), 2),
        "light": int(clamp(light, 0, 4095)),
        "distance_cm": round(clamp(distance, 2, 400), 2),
        "rssi": random.randint(-85, -60),
        "uptime_s": int(i * args.interval),
    }

    # rơi gói: sequence vẫn tăng nhưng không gửi
    if i == gap_start:
        gap_until = i + 12
    in_gap = gap_start <= i <= gap_until
    if in_gap or random.random() < args.drop:
        dropped += 1
        time.sleep(args.interval)
        continue

    msg = json.dumps(payload)
    client.publish(TOPIC, msg, qos=1)
    sent += 1
    if random.random() < args.dup:  # gửi trùng
        client.publish(TOPIC, msg, qos=1)
        dups += 1

    time.sleep(args.interval)

client.loop_stop()
client.disconnect()
print(f"Xong. da gui={sent}, roi={dropped}, outlier={outliers}, trung={dups}")
print("Doi chieu voi collector: lost ~ roi, duplicates ~ trung")