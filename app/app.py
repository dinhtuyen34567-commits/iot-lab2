
import os
import sys
import time

import numpy as np
import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


KEYS = ["INFLUX_URL", "INFLUX_ORG", "INFLUX_TOKEN", "INFLUX_BUCKET_RAW", "INFLUX_BUCKET_CLEAN"]
try:
    for k in KEYS:
        if k in st.secrets:
            os.environ[k] = str(st.secrets[k])
except Exception:
    pass

from preprocess.preprocess import query_df, run_preprocess  

RAW = os.getenv("INFLUX_BUCKET_RAW", "raw")
CLEAN = os.getenv("INFLUX_BUCKET_CLEAN", "clean")

st.set_page_config(page_title="IoT Lab 2 - Giam sat", layout="wide")
st.title("IoT Lab 2: Thu thập, lưu trữ, tiền xử lý dữ liệu")


def q(sql, bucket):
    try:
        df = query_df(sql, bucket)
        if df is not None and not df.empty and "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], utc=True)
            df = df.set_index("time")
        return df
    except Exception as e: 
        st.warning(f"Khong doc duoc du lieu: {str(e)[:200]}")
        return pd.DataFrame()



st.sidebar.header("Cấu hình")
devs = q("SELECT DISTINCT device_id FROM sensor_raw WHERE time >= now() - interval '1 day'", RAW)
dev_list = sorted(devs["device_id"].tolist()) if not devs.empty else ["esp32-01", "esp32-sim"]
device = st.sidebar.selectbox("Thiết bị", dev_list)
minutes = st.sidebar.slider("Khoảng thời gian (phút)", 5, 180, 15)
auto = st.sidebar.checkbox("Tự làm mới", value=False)
refresh = st.sidebar.number_input("Chu kỳ làm mới (giây)", 3, 60, 5)

tab1, tab2, tab3, tab4 = st.tabs(["Real-time (raw)", "Đã xử lý (clean)", "Độ trễ", "Sức khỏe pipeline"])


with tab1:
    raw = q(f"""SELECT time, temperature, humidity, light, distance_cm
                FROM sensor_raw
                WHERE device_id = '{device}' AND time >= now() - interval '{minutes} minutes'
                ORDER BY time""", RAW)
    if raw.empty:
        st.info("Chưa có dữ liệu raw trong khoảng thời gian này.")
    else:
        last = raw.iloc[-1]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Nhiệt độ (°C)", f"{last['temperature']:.1f}")
        c2.metric("Độ ẩm (%)", f"{last['humidity']:.1f}")
        c3.metric("Ánh sáng", f"{int(last['light'])}")
        c4.metric("Khoảng cách (cm)", f"{last['distance_cm']:.1f}")
        c5.metric("Số điểm", len(raw))
        a, b = st.columns(2)
        a.subheader("Nhiệt độ"); a.line_chart(raw["temperature"])
        b.subheader("Độ ẩm"); b.line_chart(raw["humidity"])
        a.subheader("Ánh sáng"); a.line_chart(raw["light"])
        b.subheader("Khoảng cách"); b.line_chart(raw["distance_cm"])


with tab2:
    c1, c2 = st.columns(2)
    freq = c1.selectbox("Cửa sổ resample", ["5s", "10s", "30s", "1min"], index=1)
    method = c2.selectbox("Phương pháp outlier", ["iqr", "zscore"])
    if st.button("Chạy tiền xử lý và ghi vào bucket clean"):
        with st.spinner("Đang xử lý..."):
            try:
                clean_df, summary = run_preprocess(device, minutes, freq, method, write=True)
                st.session_state["summary"] = summary
            except Exception as e:
                st.error(f"Loi tien xu ly: {e}")
    if "summary" in st.session_state:
        st.subheader("Tóm tắt lần xử lý gần nhất")
        st.json(st.session_state["summary"])

    clean = q(f"""SELECT time, temperature, humidity, light, distance_cm,
                         temperature_roll, temperature_delta, temperature_norm, imputed
                  FROM sensor_clean
                  WHERE device_id = '{device}' AND time >= now() - interval '{minutes} minutes'
                  ORDER BY time""", CLEAN)
    if clean.empty:
        st.info("Chưa có dữ liệu clean. Bấm nút phía trên để chạy tiền xử lý.")
    else:
        st.subheader("Nhiệt độ: raw so với clean")
        cmp_df = pd.DataFrame({"clean": clean["temperature"], "rolling_mean": clean["temperature_roll"]})
        if not raw.empty:
            cmp_df["raw"] = raw["temperature"]
        st.line_chart(cmp_df)
        a, b = st.columns(2)
        a.subheader("Delta nhiệt độ"); a.line_chart(clean["temperature_delta"])
        b.subheader("Nhiệt độ chuẩn hóa (min-max)"); b.line_chart(clean["temperature_norm"])
        st.caption(f"Số bin được nội suy: {int(clean['imputed'].sum())} / {len(clean)}")


with tab3:
    lat = q(f"""SELECT time, mqtt_ms, db_ms, e2e_ms FROM latency
                WHERE device_id = '{device}' AND time >= now() - interval '{minutes} minutes'
                ORDER BY time""", RAW)
    if lat.empty:
        st.info("Chưa có dữ liệu độ trễ.")
    else:
        stats = pd.DataFrame({
            "trung bình": lat.mean(),
            "trung vị": lat.median(),
            "p95": lat.quantile(0.95),
            "lớn nhất": lat.max(),
        }).round(1)
        st.subheader("Thống kê độ trễ (ms)")
        st.dataframe(stats)
        st.subheader("Độ trễ end-to-end theo thời gian")
        st.line_chart(lat["e2e_ms"])
        counts, edges = np.histogram(lat["e2e_ms"], bins=15)
        hist = pd.DataFrame({"so goi": counts}, index=[f"{int(e)}" for e in edges[:-1]])
        st.subheader("Phân bố e2e_ms")
        st.bar_chart(hist)
        st.caption("Độ trễ = (giờ máy collector) - (giờ ESP32 lúc publish); sai số vài chục ms do lệch đồng hồ NTP.")


with tab4:
    n_raw = q(f"SELECT device_id, COUNT(*) AS so_diem FROM sensor_raw "
              f"WHERE time >= now() - interval '{minutes} minutes' GROUP BY device_id", RAW)
    n_clean = q(f"SELECT device_id, COUNT(*) AS so_diem FROM sensor_clean "
                f"WHERE time >= now() - interval '{minutes} minutes' GROUP BY device_id", CLEAN)
    a, b = st.columns(2)
    a.subheader("Bucket raw"); a.dataframe(n_raw)
    b.subheader("Bucket clean"); b.dataframe(n_clean)
    st.caption("Mất gói và gói trùng được collector đếm trong log (stats: lost, duplicates).")

if auto:
    time.sleep(int(refresh))
    st.rerun()