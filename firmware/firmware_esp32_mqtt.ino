#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>


const char* ssid = "TEN_WIFI_CUA_BAN";
const char* password = "MAT_KHAU_WIFI";


const char* mqtt_server = "broker.hivemq.com";
const int mqtt_port = 1883;
const char* mqtt_topic = "iot/sensor/data";


#define DHTPIN 4   
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Đang kết nối WiFi: ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi đã kết nối!");
  Serial.print("Địa chỉ IP: ");
  Serial.println(WiFi.localIP());
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Đang kết nối lại MQTT Broker...");
    String clientId = "ESP32Client-" + String(random(0, 1000));
    if (client.connect(clientId.c_str())) {
      Serial.println(" Đã kết nối MQTT!");
    } else {
      Serial.print(" Thất bại, mã lỗi: ");
      Serial.print(client.state());
      Serial.println(" Thử lại sau 5 giây...");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  
  float t = dht.readTemperature();
  float h = dht.readHumidity();

  
  if (isnan(t) || isnan(h)) {
    Serial.println("Lỗi: Không thể đọc dữ liệu từ cảm biến DHT!");
    delay(2000);
    return;
  }

  
  StaticJsonDocument<200> doc;
  doc["device_id"] = "ESP32_Zone1";
  doc["temperature"] = t;
  doc["humidity"] = h;
  doc["timestamp"] = millis(); 

  char jsonBuffer[200];
  serializeJson(doc, jsonBuffer);


  Serial.print("Đang gửi dữ liệu: ");
  Serial.println(jsonBuffer);
  client.publish(mqtt_topic, jsonBuffer);


  delay(5000);
}