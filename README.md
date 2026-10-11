# IoT Lab 2: Thu thập, lưu trữ và tiền xử lý dữ liệu IoT

Học phần IoT và Ứng dụng (INT14149). Pipeline: **ESP32 (Wokwi) → MQTT broker → collector (Python) → InfluxDB Cloud → tiền xử lý → dashboard Streamlit**.

## Kiến trúc

```
ESP32 / Wokwi (esp32-01) ──┐
                           ├─> broker.hivemq.com ─> collector.py ─> InfluxDB Cloud
fake_publisher.py ─────────┘     (MQTT, QoS1)        validate        bucket raw
 (esp32-sim, có nhiễu)                                đo độ trễ        │
                                                                       ▼
                                  app/app.py (Streamlit) <── preprocess.py ──> bucket clean
```

## Cấu trúc thư mục

| Đường dẫn | Nội dung |
|---|---|
| `firmware/` | `main.ino`, `diagram.json`, `libraries.txt` (dán vào dự án Wokwi) |
| `collector/collector.py` | Subscribe MQTT, kiểm tra dữ liệu, ghi InfluxDB, đo độ trễ, phát hiện mất/trùng gói |
| `simulator/fake_publisher.py` | Thiết bị giả `esp32-sim`: nhiễu, rơi gói, outlier, gửi trùng |
| `preprocess/preprocess.py` | Tiền xử lý và ghi bucket `clean` |
| `app/app.py` | Dashboard và ứng dụng giám sát (Streamlit) |
| `.env.example` | Mẫu cấu hình |

## Cài đặt

1. Tạo tài khoản InfluxDB Cloud (gói Free), tạo 2 bucket: `raw` (retention 7 ngày) và `clean` (30 ngày). Tạo API token có quyền Read/Write cho cả hai.
2. `cp .env.example .env` rồi điền `INFLUX_URL`, `INFLUX_ORG`, `INFLUX_TOKEN`.
3. `pip install -r requirements.txt`
4. Dự án Wokwi: dán `firmware/main.ino`, `diagram.json`, `libraries.txt`. Link dự án: **(điền link Wokwi Bài 2)**.

## Chạy

Mở 3 terminal:

```bash
python collector/collector.py                                   # 1. luôn chạy
python simulator/fake_publisher.py --interval 1 --count 600     # 2. dữ liệu giả ~10 phút
python preprocess/preprocess.py --device esp32-sim --minutes 30 --freq 10s   # 3. tiền xử lý
streamlit run app/app.py                                        # 4. dashboard
```

Bật Wokwi (Start Simulation) để có thêm dữ liệu thật từ `esp32-01`.

## Định dạng dữ liệu

Topic: `ptit/lab2/tuyen911/<device_id>/sensors`. Payload JSON:

```json
{"device_id":"esp32-01","boot_id":123,"sequence":7,"ts_ms":1791691427485,
 "temperature":25.0,"humidity":50.0,"light":1001,"distance_cm":100.9,"rssi":-70,"uptime_s":35}
```

## Schema InfluxDB

| Bucket | Measurement | Tag | Field |
|---|---|---|---|
| raw | `sensor_raw` | `device_id` | temperature, humidity, distance_cm, light, rssi, sequence, boot_id, uptime_s |
| raw | `latency` | `device_id` | mqtt_ms, db_ms, e2e_ms |
| clean | `sensor_clean` | `device_id` | 4 cảm biến đã làm sạch, `*_roll`, `*_delta`, `*_norm`, `imputed` |

- Thời gian ghi là `ts_ms` của thiết bị, nên gói gửi trùng (cùng tag và timestamp) tự ghi đè.
- Chỉ `device_id` làm tag để tránh phình cardinality.
- Retention: raw 7 ngày (nhiều, nhiễu), clean 30 ngày (ít, có giá trị).

## Xử lý lỗi và độ tin cậy

- Collector bỏ qua JSON hỏng, thiếu field, sai kiểu, ngoài khoảng vật lý; lỗi ghi DB chỉ log, không dừng chương trình.
- Mất gói: so `sequence` liên tiếp trong cùng `boot_id`. Thiết bị reboot đổi `boot_id` nên không bị tính nhầm là mất gói.
- ESP32 tự kết nối lại WiFi và MQTT.

## Tiền xử lý

1. Loại trùng timestamp.
2. Phát hiện outlier IQR (hệ số 1.5) và Z-score (ngưỡng 3), thay bằng NaN; có thể chọn phương pháp bằng `--method`.
3. Resample theo cửa sổ (mặc định 10s, lấy trung bình).
4. Giá trị thiếu: nội suy theo thời gian (tối đa 3 bin), phần còn lại điền ngắn, bin không cứu được thì bỏ; cột `imputed` đánh dấu bin được điền.
5. Đặc trưng: rolling mean (cửa sổ 5), delta.
6. Chuẩn hóa min-max.
7. Ghi vào `sensor_clean`; tóm tắt lưu ở `results/preprocess_summary.json`.

## Kết quả thực nghiệm

(Điền sau khi chạy: ảnh dashboard, bảng độ trễ mean/p95/max, số gói gửi/rơi/outlier/trùng so với `lost`/`duplicates` của collector, số outlier IQR so với Z-score.)

## Hạn chế và hướng cải tiến

- `PubSubClient` chỉ hỗ trợ QoS 0 khi publish; có thể dùng thư viện hỗ trợ QoS 1 hoặc buffer cục bộ trên thiết bị.
- Broker công cộng, không mã hóa; nên dùng HiveMQ Cloud với TLS (cổng 8883) và xác thực.
- Độ trễ đo bằng hai đồng hồ khác nhau (đồng bộ NTP), sai số vài chục ms.
- Collector ghi từng điểm đồng bộ; có thể gom batch để giảm độ trễ ghi DB.

## Khó khăn và cách giải quyết

(Ví dụ: Wokwi không kết nối được localhost nên dùng broker công cộng; ThingsBoard ở Bài 1 không cho subscribe tự do nên đổi sang HiveMQ; dữ liệu Wokwi hằng số nên viết thêm bộ giả lập.)