import math
import pandas as pd
from pathlib import Path
import streamlit as st
import folium
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium

ROOT_DIR = Path(__file__).resolve().parent.parent
CSV_FILE = ROOT_DIR / "csv" / "childcare.csv"
DEFAULT_LOCATION = (37.5250, 126.8964)

st.set_page_config(page_title="보육 취약지역 분석", layout="wide")
st.title("공공데이터 기반 보육 취약지역 분석")
st.caption("어린이집의 거리·충원율·국공립 비율을 결합해 지역별 보육 접근성을 분석합니다.")


@st.cache_data
def load_data():
    for encoding in ("utf-8-sig", "cp949", "utf-8"):
        try:
            df = pd.read_csv(CSV_FILE, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV 파일의 인코딩을 확인하세요.")

    columns = ["어린이집명", "어린이집유형구분", "운영현황", "주소",
               "정원수", "현원수", "위도", "경도"]
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"필요한 열이 없습니다: {missing}")

    df = df[df["운영현황"] == "정상"].copy()
    for column in ["정원수", "현원수", "위도", "경도"]:
        df[column] = pd.to_numeric(
            df[column].astype(str).str.replace(",", "", regex=False),
            errors="coerce"
        )

    return df.dropna(subset=["정원수", "현원수", "위도", "경도"]).query("정원수 > 0")


@st.cache_data(ttl=3600)
def geocode(address):
    try:
        location = Nominatim(
            user_agent="student_childcare_vulnerability_project"
        ).geocode(address, timeout=10)
        return (location.latitude, location.longitude) if location else DEFAULT_LOCATION
    except Exception:
        return DEFAULT_LOCATION


def haversine(lat1, lng1, lat2, lng2):
    """두 위·경도 사이의 직선거리를 km로 계산한다."""
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def vulnerability_index(count, occupancy, public_ratio, radius):
    """시설 부족 40%, 혼잡 40%, 공공성 부족 20%를 결합한 자체 지수."""
    expected = max(3, radius * 3)
    scarcity = max(0, 1 - count / expected)
    crowding = min(1, max(0, (occupancy - 70) / 30))
    public_deficit = max(0, 1 - public_ratio / 40)

    score = round(40 * scarcity + 40 * crowding + 20 * public_deficit)
    level = "취약" if score >= 60 else "주의" if score >= 35 else "양호"
    return score, level


def congestion(rate):
    return "혼잡" if rate >= 95 else "주의" if rate >= 80 else "여유"


try:
    df = load_data()
except Exception as error:
    st.error(error)
    st.stop()

address = st.sidebar.text_input("기준 주소", "서울특별시 영등포구 당산로 123")
radius = st.sidebar.slider("분석 반경(km)", 0.5, 5.0, 2.0, 0.5)
lat, lng = geocode(address)

df["거리(km)"] = df.apply(
    lambda row: haversine(lat, lng, row["위도"], row["경도"]), axis=1
).round(2)
df["충원율"] = (df["현원수"] / df["정원수"] * 100).round(1)
df["혼잡도"] = df["충원율"].apply(congestion)
df["국공립"] = df["어린이집유형구분"].astype(str).str.contains("국공립")

near = df[df["거리(km)"] <= radius].sort_values("거리(km)").copy()
if near.empty:
    st.warning("반경 안에 어린이집이 없습니다. 주소나 반경을 조정하세요.")
    st.stop()

count = len(near)
avg_occupancy = near["충원율"].mean()
public_ratio = near["국공립"].mean() * 100
score, level = vulnerability_index(count, avg_occupancy, public_ratio, radius)

c1, c2, c3, c4 = st.columns(4)
c1.metric("어린이집 수", f"{count}곳")
c2.metric("평균 충원율", f"{avg_occupancy:.1f}%")
c3.metric("국공립 비율", f"{public_ratio:.1f}%")
c4.metric("보육 취약도", f"{level} ({score}점)")

st.info(
    "취약도 지수 = 시설 부족 40% + 평균 혼잡 40% + 국공립 부족 20%\n\n"
    "점수가 높을수록 어린이집 접근성과 입소 가능성이 낮다고 해석합니다."
)

m = folium.Map(location=[lat, lng], zoom_start=14)
folium.Marker([lat, lng], tooltip="기준 위치", icon=folium.Icon(color="purple")).add_to(m)
folium.Circle([lat, lng], radius=radius * 1000, color="purple", fill=True,
              fill_opacity=0.05).add_to(m)

colors = {"여유": "blue", "주의": "orange", "혼잡": "red"}
for _, row in near.iterrows():
    popup = (
        f"<b>{row['어린이집명']}</b><br>"
        f"거리: {row['거리(km)']}km<br>"
        f"충원율: {row['충원율']}% ({row['혼잡도']})"
    )
    folium.Marker(
        [row["위도"], row["경도"]],
        tooltip=row["어린이집명"],
        popup=popup,
        icon=folium.Icon(color=colors[row["혼잡도"]], icon="home")
    ).add_to(m)

st_folium(m, width=1100, height=550)

st.subheader("가까운 어린이집")
st.dataframe(
    near[["어린이집명", "어린이집유형구분", "거리(km)", "충원율", "혼잡도"]].head(10),
    use_container_width=True,
    hide_index=True
)