# Hệ thống Thu thập, Lưu trữ và Tiền xử lý Dữ liệu IoT

## 1. Giới thiệu
Dự án thực hiện việc thu thập dữ liệu nhiệt độ, độ ẩm từ thiết bị nhúng (ESP32), publish qua MQTT, sau đó lưu trữ vào database, tiền xử lý và hiển thị giám sát trên Dashboard.

## 2. Cấu trúc mã nguồn
- `/firmware`: Mã nguồn C++ cho ESP32 đọc cảm biến DHT22 và publish JSON.
- `/collector`: Script Python subscribe MQTT và ghi vào database.
- `/preprocess`: Script xử lý giá trị thiếu, outlier và chuẩn hóa dữ liệu.
- `/dashboard`: Mã nguồn giao diện giám sát (Streamlit).
- `/app`: Ứng dụng quản lý đi kèm.

## 3. Hướng dẫn cài đặt và chạy hệ thống

### Bước 1: Nạp firmware cho phần cứng
1. Mở file `firmware_esp32_mqtt.ino` bằng Arduino IDE.
2. Cài đặt các thư viện: `PubSubClient`, `DHT sensor library`, `ArduinoJson`.
3. Sửa thông tin WiFi (`ssid`, `password`) và thông tin MQTT Broker.
4. Cắm cáp ESP32 và ấn Upload.

### Bước 2: Chạy MQTT Broker & Database
Đảm bảo MQTT Broker (Mosquitto/HiveMQ) và Database (InfluxDB/MongoDB) đang hoạt động. Nếu dùng Docker:
`docker-compose up -d` (nếu có file docker-compose.yml)

### Bước 3: Chạy Pipeline dữ liệu
1. Cài đặt thư viện Python:
   `pip install paho-mqtt pandas numpy scikit-learn pymongo influxdb-client streamlit`
2. Chạy file thu thập dữ liệu:
   `python collector/main.py`
3. Chạy file tiền xử lý dữ liệu (có thể chạy theo lịch cronjob):
   `python preprocess/process.py`

### Bước 4: Chạy Dashboard
Mở terminal mới và khởi chạy giao diện:
`streamlit run dashboard/app.py`
Truy cập `http://localhost:8501` trên trình duyệt để xem kết quả real-time.