import math
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim


# =========================================================
# 공공데이터 기반 보육서비스 취약지역 분석 프로그램
#
# 주제:
# 저출산 시대에도 특정 지역·기관에 보육 수요가 몰리는 현상을
# 공공데이터를 활용해 분석한다.
#
# 핵심 기능:
# 1. 사용자가 입력한 주소를 위도·경도로 변환
# 2. 기준 위치 주변 어린이집 검색
# 3. 정원·현원 데이터를 이용해 충원율과 혼잡도 계산
# 4. 주변 어린이집 수, 평균 충원율, 국공립 비율을 바탕으로
#    돌봄 취약도를 판단
# 5. 지도에 어린이집 혼잡도를 시각화
# =========================================================


st.set_page_config(
    page_title="보육서비스 취약지역 분석",
    layout="wide"
)

CSV_FILE = "csv/어린이집기본정보조회.csv"

DEFAULT_LAT = 37.5250
DEFAULT_LNG = 126.8964


def read_csv_safely(path):
    encodings = ["utf-8-sig", "cp949", "utf-8"]

    for encoding in encodings:
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception:
            pass

    raise ValueError("CSV 파일을 읽을 수 없습니다. 파일 경로나 인코딩을 확인하세요.")


def to_number(series):
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce"
    )


def calculate_distance(lat1, lon1, lat2, lon2):
    if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
        return 999.0

    radius = 6371.0

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return radius * c


@st.cache_data(ttl=3600)
def geocode_address(address):
    try:
        geolocator = Nominatim(user_agent="childcare_access_project")
        location = geolocator.geocode(address, timeout=10)

        if location:
            return location.latitude, location.longitude
    except Exception:
        pass

    return None, None


def get_status_label(occupancy_rate):
    if occupancy_rate >= 95:
        return "혼잡"
    elif occupancy_rate >= 80:
        return "주의"
    else:
        return "여유"


def get_marker_color(status):
    if status == "혼잡":
        return "red"
    elif status == "주의":
        return "orange"
    else:
        return "blue"


def classify_vulnerability(facility_count, average_occupancy, public_ratio, radius):
    score = 0
    reasons = []

    expected_count = max(3, int(radius * 3))

    if facility_count < expected_count:
        score += 35
        reasons.append("주변 어린이집 수가 적음")
    elif facility_count < expected_count + 3:
        score += 20
        reasons.append("주변 어린이집 수가 충분하지 않을 수 있음")
    else:
        reasons.append("주변 어린이집 수는 비교적 충분함")

    if average_occupancy >= 95:
        score += 40
        reasons.append("평균 충원율이 매우 높음")
    elif average_occupancy >= 85:
        score += 25
        reasons.append("평균 충원율이 높은 편")
    elif average_occupancy >= 75:
        score += 10
        reasons.append("평균 충원율이 보통 수준")
    else:
        reasons.append("평균 충원율이 낮아 여유가 있음")

    if public_ratio < 20:
        score += 25
        reasons.append("국공립 어린이집 비율이 낮음")
    elif public_ratio < 35:
        score += 15
        reasons.append("국공립 어린이집 비율이 다소 낮음")
    else:
        reasons.append("국공립 어린이집 비율은 비교적 양호함")

    if score >= 70:
        level = "취약"
        comment = "보육서비스 접근성과 입소 가능성 측면에서 행정적 관심이 필요한 지역입니다."
    elif score >= 40:
        level = "주의"
        comment = "일부 조건에서 보육서비스 이용이 어려울 가능성이 있습니다."
    else:
        level = "양호"
        comment = "현재 데이터 기준으로는 보육서비스 접근성이 비교적 양호합니다."

    return score, level, comment, reasons


@st.cache_data
def load_childcare_data():
    df = read_csv_safely(CSV_FILE)

    required_columns = [
        "어린이집명",
        "어린이집유형구분",
        "운영현황",
        "주소",
        "정원수",
        "현원수",
        "위도",
        "경도"
    ]

    missing = [col for col in required_columns if col not in df.columns]

    if missing:
        raise ValueError(f"CSV에 필요한 열이 없습니다: {missing}")

    df = df[df["운영현황"] == "정상"].copy()

    number_columns = ["정원수", "현원수", "위도", "경도"]

    for col in number_columns:
        df[col] = to_number(df[col])

    df = df.dropna(subset=["정원수", "현원수", "위도", "경도"])
    df = df[df["정원수"] > 0].copy()

    return df


try:
    childcare_df = load_childcare_data()
except Exception as e:
    st.error(f"데이터를 불러오는 중 문제가 발생했습니다: {e}")
    st.stop()


st.title("공공데이터 기반 보육서비스 취약지역 분석")

st.write(
    "저출산 시대에도 일부 지역과 특정 보육기관에 수요가 몰리는 현상을 "
    "어린이집 위치, 정원, 현원, 기관 유형 데이터를 활용해 분석합니다."
)

st.sidebar.header("분석 조건")

address = st.sidebar.text_input(
    "기준 주소",
    value="서울특별시 영등포구 당산로 123",
    help="주소 변환에 실패하면 영등포구청 인근 좌표를 기준으로 분석합니다."
)

radius = st.sidebar.slider(
    "분석 반경",
    min_value=0.5,
    max_value=5.0,
    value=2.0,
    step=0.5,
    format="%.1f km"
)


lat, lng = geocode_address(address)

if lat is None or lng is None:
    lat, lng = DEFAULT_LAT, DEFAULT_LNG
    address_status = "주소 변환 실패 · 기본 좌표 사용"
else:
    address_status = "주소 인식 완료"


analysis_df = childcare_df.copy()

analysis_df["거리(km)"] = analysis_df.apply(
    lambda row: calculate_distance(
        lat,
        lng,
        row["위도"],
        row["경도"]
    ),
    axis=1
)

analysis_df["충원율"] = (analysis_df["현원수"] / analysis_df["정원수"] * 100).round(1)
analysis_df["여유인원"] = analysis_df["정원수"] - analysis_df["현원수"]
analysis_df["혼잡도"] = analysis_df["충원율"].apply(get_status_label)

analysis_df["국공립여부"] = analysis_df["어린이집유형구분"].apply(
    lambda x: "국공립" if "국공립" in str(x) else "기타"
)

analysis_df["거리(km)"] = analysis_df["거리(km)"].round(2)

near_df = analysis_df[analysis_df["거리(km)"] <= radius].copy()
near_df = near_df.sort_values("거리(km)").reset_index(drop=True)

if near_df.empty:
    st.warning("분석 반경 안에 어린이집이 없습니다. 반경을 넓히거나 주소를 확인해 주세요.")
    st.stop()


facility_count = len(near_df)
average_occupancy = near_df["충원율"].mean().round(1)
high_occupancy_count = len(near_df[near_df["충원율"] >= 95])
public_count = len(near_df[near_df["국공립여부"] == "국공립"])
public_ratio = round(public_count / facility_count * 100, 1)

vulnerability_score, vulnerability_level, vulnerability_comment, vulnerability_reasons = classify_vulnerability(
    facility_count=facility_count,
    average_occupancy=average_occupancy,
    public_ratio=public_ratio,
    radius=radius
)


col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("주소 상태", address_status)

with col2:
    st.metric("주변 어린이집 수", f"{facility_count}곳")

with col3:
    st.metric("평균 충원율", f"{average_occupancy}%")

with col4:
    st.metric("돌봄 취약도", vulnerability_level)

st.caption(
    "※ 돌봄 취약도는 실제 입소 대기자 수가 아니라, 주변 어린이집 수·평균 충원율·국공립 비율을 바탕으로 한 참고용 분석 지표입니다."
)


tab_summary, tab_map, tab_detail = st.tabs([
    "취약도 분석",
    "지도 시각화",
    "상세 데이터"
])


with tab_summary:
    st.subheader("기준 지역 보육서비스 취약도 분석")

    st.info(f"취약도 점수: {vulnerability_score}점 / 판단 결과: {vulnerability_level}")
    st.write(vulnerability_comment)

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("혼잡 어린이집 수", f"{high_occupancy_count}곳")

    with c2:
        st.metric("국공립 어린이집 수", f"{public_count}곳")

    with c3:
        st.metric("국공립 비율", f"{public_ratio}%")

    st.subheader("분석 근거")

    for reason in vulnerability_reasons:
        st.write(f"- {reason}")

    st.subheader("행정학적 해석")

    st.write(
        "저출산으로 전체 아동 수가 감소하더라도 보육 수요가 모든 지역에서 동일하게 줄어드는 것은 아닙니다. "
        "특정 지역에 어린이집 수가 적거나, 주변 어린이집의 충원율이 높거나, 국공립 비율이 낮다면 "
        "해당 지역은 보육서비스 접근성이 낮은 돌봄 취약지역으로 해석할 수 있습니다."
    )

    st.subheader("가까운 어린이집 중 혼잡도 높은 곳")

    crowded_df = near_df.sort_values(["충원율", "거리(km)"], ascending=[False, True]).head(5)

    for _, row in crowded_df.iterrows():
        st.markdown(
            f"""
            **{row['어린이집명']}**  
            유형: {row['어린이집유형구분']} / 혼잡도: {row['혼잡도']} / 거리: {row['거리(km)']}km  
            정원 {int(row['정원수'])}명 · 현원 {int(row['현원수'])}명 · 충원율 {row['충원율']}% · 여유인원 {int(row['여유인원'])}명  
            주소: {row['주소']}
            """
        )
        st.markdown("---")


with tab_map:
    st.subheader("어린이집 혼잡도 지도")

    m = folium.Map(
        location=[lat, lng],
        zoom_start=14,
        tiles="OpenStreetMap"
    )

    folium.Marker(
        location=[lat, lng],
        popup="분석 기준 위치",
        tooltip="기준 위치",
        icon=folium.Icon(color="purple", icon="star")
    ).add_to(m)

    folium.Circle(
        location=[lat, lng],
        radius=radius * 1000,
        color="purple",
        fill=True,
        fill_opacity=0.05,
        popup=f"분석 반경 {radius}km"
    ).add_to(m)

    for _, row in near_df.iterrows():
        color = get_marker_color(row["혼잡도"])

        popup_html = f"""
        <div style="width:240px; line-height:1.55;">
            <b>{row['어린이집명']}</b><br>
            유형: {row['어린이집유형구분']}<br>
            거리: {row['거리(km)']}km<br>
            정원: {int(row['정원수'])}명<br>
            현원: {int(row['현원수'])}명<br>
            충원율: {row['충원율']}%<br>
            혼잡도: {row['혼잡도']}
        </div>
        """

        folium.Marker(
            location=[row["위도"], row["경도"]],
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=row["어린이집명"],
            icon=folium.Icon(color=color, icon="home")
        ).add_to(m)

    st_folium(m, width=1100, height=620)

    st.caption("파랑: 여유 · 노랑: 주의 · 빨강: 혼잡 · 보라색 별: 분석 기준 위치")


with tab_detail:
    st.subheader("분석 대상 어린이집 상세 데이터")

    display_columns = [
        "어린이집명",
        "어린이집유형구분",
        "주소",
        "거리(km)",
        "정원수",
        "현원수",
        "여유인원",
        "충원율",
        "혼잡도",
        "국공립여부"
    ]

    detail_df = near_df[display_columns].copy()

    st.dataframe(detail_df, use_container_width=True)

    st.subheader("혼잡도 기준")

    st.write("- 충원율 95% 이상: 혼잡")
    st.write("- 충원율 80% 이상 95% 미만: 주의")
    st.write("- 충원율 80% 미만: 여유")

    st.subheader("취약도 판단 기준")

    st.write(
        """
        본 프로그램은 다음 세 가지 요소를 바탕으로 돌봄 취약도를 계산합니다.

        1. 주변 어린이집 수: 반경 안 어린이집이 적으면 접근성이 낮다고 판단
        2. 평균 충원율: 충원율이 높으면 실제 입소 가능성이 낮다고 판단
        3. 국공립 비율: 국공립 어린이집 비율이 낮으면 공공보육 접근성이 낮다고 판단

        이 기준은 실제 정책 결정을 대신하는 것이 아니라,
        공공데이터를 활용해 보육서비스 수급 불균형을 파악하기 위한 참고용 지표입니다.
        """
    )