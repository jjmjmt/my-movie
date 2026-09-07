import datetime
import requests
import pandas as pd
import pytz
import streamlit as st

# 페이지 기본 설정
st.set_page_config(
    page_title="일별 박스오피스 조회", page_icon="🎬", layout="wide"
)


# API 데이터를 요청하고 캐싱하는 함수 (TTL: 3600초 = 1시간)
@st.cache_data(ttl=3600)
def fetch_box_office_data(api_key, target_date):
    """KOBIS API에서 박스오피스 데이터를 가져오는 함수"""
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        # HTTP 응답 코드 확인
        if response.status_code != 200:
            return None, f"서버 응답 오류가 발생했습니다. (상태 코드: {response.status_code})"

        data = response.json()

        # 인증키 오류 등 API 내부 오류(faultInfo) 처리
        if "faultInfo" in data:
            message = data["faultInfo"].get(
                "message", "인증키 오류가 발생했습니다."
            )
            return (
                None,
                f"API 오류: {message}\n`secrets.toml`의 KOBIS_KEY를 확인해 주세요.",
            )

        # 박스오피스 데이터 추출
        box_office_result = data.get("boxOfficeResult", {})
        movie_list = box_office_result.get("dailyBoxOfficeList", [])

        # 영화 목록이 비어있는 경우 (집계 전이거나 데이터 없음)
        if not movie_list:
            return None, "그날은 아직 집계 전입니다."

        return movie_list, None

    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"


def format_rank_change(inten):
    """전날 대비 순위 증감(rankInten)에 따라 화살표 및 수치 반환"""
    if inten > 0:
        return f"🔴 ▲{inten}"
    elif inten < 0:
        return f"🔵 ▼{abs(inten)}"
    else:
        return "-"


def main():
    st.title("🎬 일별 박스오피스 조회")

    # 1. secrets에서 API 키 불러오기
    if "KOBIS_KEY" not in st.secrets:
        st.error(
            "🔑 `KOBIS_KEY`가 설정되지 않았습니다.\n\n"
            "Streamlit Cloud의 **Settings > Secrets**에서 `KOBIS_KEY`를 등록해 주세요."
        )
        return

    api_key = st.secrets["KOBIS_KEY"]

    # 2. 한국 시간(KST) 기준 날짜 계산
    kst_timezone = pytz.timezone("Asia/Seoul")
    today_kst = datetime.datetime.now(kst_timezone).date()
    yesterday_kst = today_kst - datetime.timedelta(days=1)

    # 3. 사이드바 날짜 선택 달력 (최대 선택 날짜: 어제)
    st.sidebar.header("🗓️ 날짜 선택")
    selected_date = st.sidebar.date_input(
        "조회할 날짜를 선택하세요",
        value=yesterday_kst,
        max_value=yesterday_kst,
        min_value=datetime.date(2004, 1, 1),  # KOBIS 제공 최소 연도
    )

    # API 요청용 YYYYMMDD 문자열 변환
    target_date_str = selected_date.strftime("%Y%m%d")
    display_date_str = selected_date.strftime("%Y년 %m월 %d일")

    st.caption(f"📅 조회 기준일: {display_date_str}")

    # 4. 데이터 가져오기
    movie_list, error_msg = fetch_box_office_data(api_key, target_date_str)

    # 에러 또는 빈 목록 메시지 출력
    if error_msg:
        if error_msg == "그날은 아직 집계 전입니다.":
            st.warning(f"⚠️ {error_msg}")
        else:
            st.error(f"🚨 데이터를 불러올 수 없습니다.\n\n**확인 사항:** {error_msg}")
        return

    # 5. 데이터프레임 생성 및 데이터 타입 변환
    df = pd.DataFrame(movie_list)

    # 문자열로 된 숫자 컬럼들을 정수형(int)으로 변환
    numeric_columns = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # 6. 트로피 및 순위 증감 가공
    # 누적 관객 100만 이상 시 영화명 옆에 🏆 표시
    df["movieNm_display"] = df.apply(
        lambda row: f"{row['movieNm']} 🏆"
        if row["audiAcc"] >= 1000000
        else row["movieNm"],
        axis=1,
    )

    # 순위 증감 컬럼 포맷팅 (🔴 ▲ / 🔵 ▼)
    df["rank_change"] = df["rankInten"].apply(format_rank_change)

    # 7. 1위 영화 지표 카드 (Metrics)
    top_1 = df.iloc[0]
    st.markdown("### 🏆 해당 일자 1위 영화")

    col1, col2, col3 = st.columns(3)
    col1.metric(label="영화명", value=top_1["movieNm_display"])
    col2.metric(label="일별 관객수", value=f"{top_1['audiCnt']:,} 명")
    col3.metric(label="누적 관객수", value=f"{top_1['audiAcc']:,} 명")

    st.divider()

    # 8. 상위 5편 관객수 막대그래프
    st.markdown("### 📊 관객수 TOP 5")
    top_5_df = df.head(5)

    # 차트용 데이터 가공 (🏆 가 붙은 영화명 사용)
    chart_data = top_5_df[["movieNm_display", "audiCnt"]].set_index(
        "movieNm_display"
    )
    chart_data.columns = ["일별 관객수"]
    st.bar_chart(chart_data)

    st.divider()

    # 9. 전체 TOP 10 데이터 표 (Table)
    st.markdown("### 📋 박스오피스 전체 순위")

    # 표시할 컬럼 및 컬럼명 변경
    display_df = df[
        [
            "rank",
            "rank_change",
            "movieNm_display",
            "openDt",
            "audiCnt",
            "audiAcc",
            "scrnCnt",
        ]
    ].copy()
    display_df.columns = [
        "순위",
        "순위 변동",
        "영화명",
        "개봉일",
        "일별 관객수",
        "누적 관객수",
        "스크린수",
    ]

    # 숫자에 쉼표(,) 포맷 적용 후 표 출력
    st.dataframe(
        display_df.style.format(
            {"일별 관객수": "{:,}", "누적 관객수": "{:,}", "스크린수": "{:,}"}
        ),
        use_container_width=True,
        hide_index=True,
    )


if __name__ == "__main__":
    main()
