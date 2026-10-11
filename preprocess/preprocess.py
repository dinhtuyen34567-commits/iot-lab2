
import os
import json
import argparse

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.preprocessing import MinMaxScaler

load_dotenv()

SENSORS = ["temperature", "humidity", "light", "distance_cm"]


def query_df(sql, bucket):
    """Đọc dữ liệu bằng SQL (InfluxDB Cloud Serverless) -> DataFrame."""
    from influxdb_client_3 import InfluxDBClient3

    client = InfluxDBClient3(
        host=os.getenv("INFLUX_URL"),
        token=os.getenv("INFLUX_TOKEN"),
        org=os.getenv("INFLUX_ORG"),
        database=bucket,
    )
    return client.query(query=sql, language="sql", mode="pandas")


def read_raw(device, minutes):
    sql = f"""
        SELECT time, temperature, humidity, light, distance_cm
        FROM sensor_raw
        WHERE device_id = '{device}'
          AND time >= now() - interval '{int(minutes)} minutes'
        ORDER BY time
    """
    df = query_df(sql, os.getenv("INFLUX_BUCKET_RAW"))
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.set_index("time")


def write_clean(df, device):
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import SYNCHRONOUS

    out = df.copy()
    out["device_id"] = device
    with InfluxDBClient(
        url=os.getenv("INFLUX_URL"),
        token=os.getenv("INFLUX_TOKEN"),
        org=os.getenv("INFLUX_ORG"),
    ) as client:
        api = client.write_api(write_options=SYNCHRONOUS)
        api.write(
            bucket=os.getenv("INFLUX_BUCKET_CLEAN"),
            record=out,
            data_frame_measurement_name="sensor_clean",
            data_frame_tag_columns=["device_id"],
        )


def iqr_mask(s, k=1.5):
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    return (s < q1 - k * iqr) | (s > q3 + k * iqr)


def zscore_mask(s, thr=3.0):
    std = s.std()
    if std == 0 or np.isnan(std):
        return pd.Series(False, index=s.index)
    return ((s - s.mean()) / std).abs() > thr

def process(raw, freq="10s", method="iqr", roll_window=5, interp_limit=3):
    """raw: DataFrame index thời gian UTC, cột SENSORS. Trả về (clean_df, summary)."""
    summary = {"rows_raw": int(len(raw))}

    
    dup = int(raw.index.duplicated().sum())
    df = raw[~raw.index.duplicated(keep="last")].sort_index().copy()
    summary["duplicates_removed"] = dup

    iqr_count, z_count = {}, {}
    for c in SENSORS:
        m_iqr, m_z = iqr_mask(df[c]), zscore_mask(df[c])
        iqr_count[c], z_count[c] = int(m_iqr.sum()), int(m_z.sum())
        df.loc[m_iqr if method == "iqr" else m_z, c] = np.nan
    summary["outliers_iqr"] = iqr_count
    summary["outliers_zscore"] = z_count
    summary["method_used"] = method

    rs = df[SENSORS].resample(freq).mean()
    summary["bins"] = int(len(rs))
    missing_before = rs[SENSORS].isna().any(axis=1)
    summary["bins_missing_before_fill"] = int(missing_before.sum())


    rs = rs.interpolate(method="time", limit=interp_limit, limit_area="inside")
    rs = rs.ffill(limit=interp_limit).bfill(limit=interp_limit)
    still = rs[SENSORS].isna().any(axis=1)
    summary["bins_still_missing_dropped"] = int(still.sum())
    rs["imputed"] = missing_before.astype(int)
    rs = rs[~still].copy()

    if rs.empty:
        return rs, summary

    for c in ["temperature", "humidity", "light"]:
        rs[f"{c}_roll"] = rs[c].rolling(roll_window, min_periods=1).mean()
        rs[f"{c}_delta"] = rs[c].diff().fillna(0.0)

    norm = MinMaxScaler().fit_transform(rs[SENSORS])
    for i, c in enumerate(SENSORS):
        rs[f"{c}_norm"] = norm[:, i]

    summary["rows_clean"] = int(len(rs))
    return rs, summary


def run_preprocess(device="esp32-sim", minutes=30, freq="10s", method="iqr", write=True):
    raw = read_raw(device, minutes)
    if raw.empty:
        return None, {"error": f"Khong co du lieu raw cho {device} trong {minutes} phut"}
    clean, summary = process(raw, freq=freq, method=method)
    if write and not clean.empty:
        write_clean(clean, device)
        summary["written_to_bucket"] = os.getenv("INFLUX_BUCKET_CLEAN")
    return clean, summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="esp32-sim")
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--freq", default="10s")
    ap.add_argument("--method", choices=["iqr", "zscore"], default="iqr")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()

    clean, summary = run_preprocess(a.device, a.minutes, a.freq, a.method, not a.no_write)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    os.makedirs("results", exist_ok=True)
    with open("results/preprocess_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    if clean is not None and not clean.empty:
        clean.to_csv("results/clean_sample.csv")
        print("Da luu results/preprocess_summary.json va results/clean_sample.csv")