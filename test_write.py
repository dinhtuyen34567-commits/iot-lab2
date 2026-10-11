import os
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

load_dotenv()

url = os.getenv("INFLUX_URL")
token = os.getenv("INFLUX_TOKEN")
org = os.getenv("INFLUX_ORG")
bucket = os.getenv("INFLUX_BUCKET_RAW")

with InfluxDBClient(url=url, token=token, org=org) as client:
   
    write_api = client.write_api(write_options=SYNCHRONOUS)
    point = (
        Point("test")
        .tag("device_id", "esp32-01")
        .field("temperature", 25.5)
    )
    write_api.write(bucket=bucket, record=point)
    print("Write OK")

    
    query = f'''
    from(bucket: "{bucket}")
      |> range(start: -10m)
      |> filter(fn: (r) => r._measurement == "test")
    '''
    tables = client.query_api().query(query)
    for table in tables:
        for record in table.records:
            print(record.get_time(), record.get_field(), record.get_value())