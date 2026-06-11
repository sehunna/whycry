import streamlit as st
import os
import json
import datetime
import tempfile
import pandas as pd
import concurrent.futures
from google.genai.errors import APIError

# 핵심 분석 파이프라인 임포트
from video.video_analyzer import analyze_video
from audio.audio_extractor import extract_audio
from audio.audio_analyzer import analyze_audio
from analysis.scorer import calculate_scores
from analysis.reasoner import reason_cry_cause
from analysis.personalizer import (
    initialize_baby,
    get_personal_biases,
    update_personal_biases,
    save_feedback_log,
    find_similar_cases,
    BABY_STATUS_FILE
)

# 1. 페이지 설정 및 파스텔톤 CSS 인젝션
st.set_page_config(
    page_title="WhyCry - 아기 울음 분석 서비스",
    page_icon="👶",
    layout="centered"
)

# 감성적인 파스텔 핑크/블루 테마 및 둥글고 세련된 카드 UI 스타일 정의
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&family=Noto+Sans+KR:wght@300;400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', 'Noto Sans KR', sans-serif;
    }
    
    .stApp {
        background-color: #FAF6F6; /* 포근한 미색 */
    }
    
    /* 카드 컨테이너 */
    .baby-card {
        background: white;
        padding: 24px;
        border-radius: 20px;
        box-shadow: 0 4px 20px rgba(230, 200, 200, 0.25);
        border: 1px solid #F3ECEC;
        margin-bottom: 20px;
    }
    
    .card-title {
        color: #FF8A8A; /* 파스텔 핑크 */
        font-size: 1.3rem;
        font-weight: 600;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    /* 둥근 버튼 및 파스텔 디자인 */
    div.stButton > button {
        background-color: #EBF3FC; /* 부드러운 파스텔 블루 */
        color: #4A607A;
        border: 1px solid #D2E3F7;
        border-radius: 12px;
        padding: 8px 16px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    
    div.stButton > button:hover {
        background-color: #DDEBFB;
        border-color: #B5D2F5;
        color: #2F4257;
        transform: translateY(-1px);
    }
    
    /* 비상(Panic) 모드 강조 버튼 */
    .panic-header {
        color: #FF6B6B;
        font-weight: 600;
        font-size: 1rem;
        margin-top: 15px;
    }
    
    /* 최종 리포트 카드 */
    .report-box {
        background: #FDF9F5;
        border-left: 5px solid #FFAD60; /* 파스텔 오렌지 */
        padding: 15px;
        border-radius: 4px 12px 12px 4px;
        margin-top: 15px;
    }
    
    .alert-box {
        background: #FFF2F2;
        border-left: 5px solid #FF8A8A;
        padding: 15px;
        border-radius: 4px 12px 12px 4px;
        margin-top: 15px;
        color: #D32F2F;
    }
</style>
""", unsafe_allow_html=True)

# 2. 타이틀 영역
st.write("<h1 style='text-align: center; color: #FFA3A3;'>👶 WhyCry</h1>", unsafe_allow_html=True)
st.write("<p style='text-align: center; color: #8C8282;'>아기의 울음소리와 행동을 분석하여 원인을 확률로 추론하고 따뜻한 대처법을 제공합니다.</p>", unsafe_allow_html=True)

# 3. 세션 초기화 및 아기 정보 관리
LAST_BABY_FILE = "last_baby.txt"

def get_last_baby_id() -> str:
    if os.path.exists(LAST_BABY_FILE):
        try:
            with open(LAST_BABY_FILE, "r", encoding="utf-8") as f:
                name = f.read().strip()
                if name:
                    return name
        except:
            pass
    return "서준"

def save_last_baby_id(name: str):
    try:
        with open(LAST_BABY_FILE, "w", encoding="utf-8") as f:
            f.write(name)
    except:
        pass

if "analyzed" not in st.session_state:
    st.session_state.analyzed = False
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = None
if "last_predicted_probs" not in st.session_state:
    st.session_state.last_predicted_probs = None
if "current_baby_id" not in st.session_state:
    st.session_state.current_baby_id = ""

# 피드백 제출을 위한 E2E 상태 세션 캐싱 초기화
if "last_video_obs" not in st.session_state:
    st.session_state.last_video_obs = None
if "last_audio_obs" not in st.session_state:
    st.session_state.last_audio_obs = None
if "last_context_data" not in st.session_state:
    st.session_state.last_context_data = None

# 아기 식별자 입력
st.markdown("<div class='baby-card'>", unsafe_allow_html=True)
st.write("<div class='card-title'>📝 아기 프로필 & 기질 설정</div>", unsafe_allow_html=True)

col1, col2 = st.columns([2, 1])
with col1:
    last_baby = get_last_baby_id()
    baby_id = st.text_input("아기 이름 또는 고유 ID", value=last_baby).strip()
    if baby_id != last_baby:
        save_last_baby_id(baby_id)

# 아기 ID가 바뀐 경우 세션 초기화
if baby_id != st.session_state.current_baby_id:
    st.session_state.current_baby_id = baby_id
    st.session_state.analyzed = False
    st.session_state.analysis_results = None

# 아기 프로필 데이터를 먼저 로드합니다.
profile = initialize_baby(baby_id)

with col2:
    # 저장된 프로필에서 생후 일수를 로드하여 기본값으로 사용합니다 (기본값 38)
    saved_age_days = int(profile.get("age_days", 38))
    age_days = st.number_input("생후 일수", min_value=1, max_value=1000, value=saved_age_days)

col3, col4 = st.columns(2)
with col3:
    feeding_type = st.selectbox(
        "수유 방식",
        ["breast", "formula", "mixed"],
        index=["breast", "formula", "mixed"].index(profile.get("feeding_type", "mixed")),
        help="수유 방식에 따라 아기의 소화 텀과 배앓이(가스) 확률이 자동 차등 적용됩니다."
    )
with col4:
    # 기질 체크박스
    frequent_colic = st.checkbox("평소에 배앓이(영아산통)가 잦은 편인가요?", value=profile.get("parent_settings", {}).get("frequent_colic", False))
    high_comfort_need = st.checkbox("졸릴 때 유독 많이 안아달라고 칭얼대나요?", value=profile.get("parent_settings", {}).get("high_comfort_need", False))

# 프로필 업데이트 및 저장
if st.button("프로필 및 기질 설정 저장"):
    # 파일 로드 후 갱신
    with open(BABY_STATUS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    data[baby_id]["age_days"] = age_days
    data[baby_id]["feeding_type"] = feeding_type
    data[baby_id]["parent_settings"] = {
        "frequent_colic": frequent_colic,
        "high_comfort_need": high_comfort_need
    }
    
    with open(BABY_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    st.success(f"'{baby_id}'의 기질 및 설정이 저장되었습니다. (추론 가중치에 즉시 반영)")

st.markdown("</div>", unsafe_allow_html=True)


# 4. 아기 일기 (Diary Mode - 평시 빠른 기록)
st.markdown("<div class='baby-card'>", unsafe_allow_html=True)
st.write("<div class='card-title'>🍼 아기 일기 (평시 퀵 기록)</div>", unsafe_allow_html=True)
st.write("<small style='color: #8C8282;'>평소 수유나 기저귀 교체 시 탭해두시면 아기가 울 때 복잡한 입력 없이 경과 시간이 자동으로 계산됩니다.</small>", unsafe_allow_html=True)

# 최근 기록 타임스탬프 계산 함수
def get_time_ago_str(timestamp_str) -> str:
    if not timestamp_str:
        return "기록 없음"
    dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    diff = datetime.datetime.now() - dt
    diff_mins = int(diff.total_seconds() / 60)
    
    if diff_mins < 60:
        return f"{diff_mins}분 전"
    else:
        return f"{diff_mins // 60}시간 {diff_mins % 60}분 전"

# 상태 갱신을 위해 파일 재로드
profile = initialize_baby(baby_id)

col_d1, col_d2, col_d3 = st.columns(3)
with col_d1:
    st.write(f"**최근 수유**: {get_time_ago_str(profile.get('last_feeding_timestamp'))}")
    if st.button("🍼 방금 수유 완료"):
        with open(BABY_STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data[baby_id]["last_feeding_timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(BABY_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        st.rerun()

with col_d2:
    st.write(f"**최근 기저귀**: {get_time_ago_str(profile.get('last_diaper_timestamp'))}")
    if st.button("🧷 방금 기저귀 교체"):
        with open(BABY_STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data[baby_id]["last_diaper_timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(BABY_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        st.rerun()

with col_d3:
    st.write(f"**최근 수면 종료**: {get_time_ago_str(profile.get('last_sleep_timestamp'))}")
    if st.button("💤 방금 잠에서 깸"):
        with open(BABY_STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data[baby_id]["last_sleep_timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(BABY_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        st.rerun()

st.markdown("</div>", unsafe_allow_html=True)


# 5. 비상 입력 (Panic Mode) & 비디오 업로드
st.markdown("<div class='baby-card'>", unsafe_allow_html=True)
st.write("<div class='card-title'>🚨 비상 진단 (영상 분석)</div>", unsafe_allow_html=True)

# 비디오 파일 업로더
uploaded_file = st.file_uploader("아기 우는 동영상 업로드 (10~15초 권장)", type=["mp4", "mov"])

# 평시 기록 데이터가 누락된 경우를 위한 간편 비상 입력 폼
st.write("<p class='panic-header'>⏱️ 최근 기록이 누락되었다면 탭해 주세요 (비상 입력)</p>", unsafe_allow_html=True)

col_p1, col_p2, col_p3 = st.columns(3)
with col_p1:
    feeding_panic = st.selectbox(
        "수유는 언제 하셨나요?",
        ["일기 자동 역산", "방금 전 (1시간 이내)", "대략 2시간 전", "대략 3시간 전", "한참 됨 (4시간 이상)", "잘 모름"]
    )
with col_p2:
    diaper_panic = st.selectbox(
        "기저귀는 언제 갈아주셨나요?",
        ["일기 자동 역산", "방금 갈아줌", "한참 됨 (2~3시간 이상)", "축축함/대변 확인됨", "잘 모름"]
    )
with col_p3:
    burp_panic = st.selectbox(
        "수유 후 트림을 했나요?",
        ["트림함", "트림 안 함", "잘 모름", "자동 추정"]
    )

def process_video_local(input_path: str, audio_path: str, compressed_path: str) -> str:
    """
    영상 파일에서 오디오를 추출하고, 비디오를 압축하여 다이어트합니다.
    리소스 락 및 여러 번 열기로 인한 Windows 권한 오류를 방지하기 위해 단 한 번만 파일을 열어 처리합니다.
    """
    try:
        try:
            from moviepy.editor import VideoFileClip
        except ImportError:
            from moviepy import VideoFileClip
    except ImportError as imp_err:
        print(f"[Local Processor][경고] MoviePy 임포트 실패: {imp_err}")
        # 임포트 실패 시 백업으로 개별 오디오 추출만 시도
        try:
            extract_audio(input_path, audio_path)
        except Exception as ae:
            print(f"[Local Processor][오류] 백업 오디오 추출 실패: {ae}")
        return input_path

    clip = None
    clip_resized = None
    try:
        print(f"[Local Processor] 파일 열기 -> {input_path}")
        clip = VideoFileClip(input_path)
        
        # 1. 오디오 추출
        if clip.audio is not None:
            print(f"[Local Processor] 오디오 추출 중 -> {audio_path}")
            clip.audio.write_audiofile(
                audio_path,
                codec='pcm_s16le',
                ffmpeg_params=["-ac", "1"], # 모노 채널
                logger=None
            )
            try:
                clip.audio.close()
            except:
                pass
        else:
            print(f"[Local Processor][경고] 영상 파일에 오디오 트랙이 존재하지 않습니다.")

        # 2. 비디오 압축
        print(f"[Local Processor] 비디오 다운사이징 시작 -> {compressed_path}")
        w, h = clip.size if hasattr(clip, 'size') else (clip.w, clip.h)
        
        if h > 360:
            new_h = 360
            new_w = int(w * 360 / h)
            if new_w % 2 != 0:
                new_w += 1
            
            if hasattr(clip, 'resized'):
                clip_resized = clip.resized((new_w, new_h))
            elif hasattr(clip, 'resize'):
                clip_resized = clip.resize((new_w, new_h))
            else:
                clip_resized = clip
        else:
            clip_resized = clip

        clip_resized.write_videofile(
            compressed_path,
            fps=15,
            codec="libx264",
            audio=False,  
            bitrate="500k",
            preset="ultrafast",
            logger=None
        )
        
        # 리소스 닫기
        if clip_resized != clip:
            clip_resized.close()
        clip.close()
        print(f"[Local Processor] 오디오 추출 및 비디오 압축 완료.")
        return compressed_path

    except Exception as e:
        import traceback
        import moviepy
        print(f"[Local Processor][DEBUG] MoviePy version: {getattr(moviepy, '__version__', 'unknown')}, file: {getattr(moviepy, '__file__', 'unknown')}")
        print(f"[Local Processor][경고] 처리 중 에러 발생하여 원본 비디오를 사용하고 오디오는 별도 추출을 시도합니다: {e}")
        traceback.print_exc()
        
        # 리소스 안전 종료
        try:
            if clip_resized and clip_resized != clip:
                clip_resized.close()
        except:
            pass
        try:
            if clip:
                clip.close()
        except:
            pass
            
        # 백업으로 개별 오디오 추출만 시도 (오디오는 API 호출에 필수적이므로)
        try:
            extract_audio(input_path, audio_path)
        except Exception as ae:
            print(f"[Local Processor][오류] 백업 오디오 추출마저 실패했습니다: {ae}")
            
        return input_path

# 6. E2E 분석 실행
if uploaded_file is not None:
    if st.button("🔍 아기 울음 종합 분석 시작", use_container_width=True):
        st.session_state.analyzed = False
        
        # 0. 입력 상황 정보 분(minutes) 데이터로 환산
        now = datetime.datetime.now()
        
        # 수유 시간 계산
        if feeding_panic == "일기 자동 역산" and profile.get("last_feeding_timestamp"):
            dt_feed = datetime.datetime.strptime(profile.get("last_feeding_timestamp"), "%Y-%m-%d %H:%M:%S")
            last_feeding_mins = int((now - dt_feed).total_seconds() / 60)
        else:
            mapping = {
                "방금 전 (1시간 이내)": 30,
                "대략 2시간 전": 120,
                "대략 3시간 전": 180,
                "한참 됨 (4시간 이상)": 240,
                "잘 모름": 120
            }
            last_feeding_mins = mapping.get(feeding_panic, 120)
            
        # 기저귀 시간 계산
        diaper_state = "unknown"
        if diaper_panic == "일기 자동 역산" and profile.get("last_diaper_timestamp"):
            dt_diaper = datetime.datetime.strptime(profile.get("last_diaper_timestamp"), "%Y-%m-%d %H:%M:%S")
            last_diaper_mins = int((now - dt_diaper).total_seconds() / 60)
        else:
            mapping = {
                "방금 갈아줌": 30,
                "한참 됨 (2~3시간 이상)": 150,
                "축축함/대변 확인됨": 180,
                "잘 모름": 90
            }
            last_diaper_mins = mapping.get(diaper_panic, 90)
            if diaper_panic == "축축함/대변 확인됨":
                diaper_state = "wet"

        # 수면 시간 계산
        if profile.get("last_sleep_timestamp"):
            dt_sleep = datetime.datetime.strptime(profile.get("last_sleep_timestamp"), "%Y-%m-%d %H:%M:%S")
            last_sleep_mins = int((now - dt_sleep).total_seconds() / 60)
        else:
            last_sleep_mins = 60 # 기본값
            
        # 트림 여부 판단
        if burp_panic == "자동 추정":
            burped_val = profile.get("last_feeding_timestamp") is not None and not profile.get("last_sleep_timestamp")
        elif burp_panic == "트림함":
            burped_val = True
        elif burp_panic == "트림 안 함":
            burped_val = False
        else: # 잘 모름
            burped_val = True # 보수적으로 패널티 없음 처리

        context_data = {
            "age_days": age_days,
            "feeding_type": feeding_type,
            "last_feeding_minutes_ago": last_feeding_mins,
            "last_diaper_change_minutes_ago": last_diaper_mins,
            "last_sleep_ended_minutes_ago": last_sleep_mins,
            "burped_after_last_feeding": burped_val,
            "temperature_celsius": 36.8,
            "diaper_state": diaper_state
        }
        
        # 1. 파일 임시 저장 (Windows 호환 스트림 즉시 해제 적용)
        temp_video_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
                temp_video.write(uploaded_file.read())
                temp_video_path = temp_video.name
            # with 블록을 완전히 벗어남으로써 파일 쓰기 핸들이 해제되어 Windows 락이 발생하지 않습니다.
        except Exception as file_err:
            st.error(f"임시 파일 저장에 실패했습니다: {file_err}")
            st.stop()

        base_name, _ = os.path.splitext(temp_video_path)
        temp_audio_path = f"{base_name}.wav"
        temp_compressed_video_path = f"{base_name}_compressed.mp4"

        try:
            # 2. 로컬 파일 처리 (추출 및 압축)
            # Windows OS의 동일 파일 동시 읽기/쓰기 락(Lock) 충돌 방지를 위해, 
            # 로컬 CPU 연산은 메인 스레드에서 순차적으로 안전하고 신속히(수초 이내) 처리합니다.
            actual_video_path = temp_video_path
            with st.spinner("1&2단계: 영상 분석 준비 중 (오디오 추출 및 비디오 압축)..."):
                actual_video_path = process_video_local(temp_video_path, temp_audio_path, temp_compressed_video_path)

            print(f"[DEBUG] temp_video_path: {temp_video_path}")
            print(f"[DEBUG] temp_compressed_video_path: {temp_compressed_video_path}")
            print(f"[DEBUG] actual_video_path: {actual_video_path}")

            # 3. 네트워크 API 호출 (Gemini 업로드 및 대기)
            # 오랜 시간이 걸리는 Gemini 업로드 및 API 추론 분석 단계만 ThreadPoolExecutor로 완벽히 병렬 처리합니다.
            def run_video_api(video_path):
                return analyze_video(video_path)

            def run_audio_api(audio_path):
                return analyze_audio(audio_path)

            with concurrent.futures.ThreadPoolExecutor() as executor:
                with st.spinner("🚀 Gemini API를 통해 비디오와 오디오를 실시간 병렬 분석 중입니다..."):
                    future_video = executor.submit(run_video_api, actual_video_path)
                    future_audio = executor.submit(run_audio_api, temp_audio_path)
                    
                    video_obs = future_video.result()
                    audio_obs = future_audio.result()

            with st.spinner("⚖️ 개인화 스코어 계산 중..."):
                scores = calculate_scores(video_obs, audio_obs, context_data, baby_id=baby_id)
                
            with st.spinner("📝 최종 AI 육아 진단서 작성 중 (유사 해결 전례 Few-shot 반영)..."):
                similar_cases = find_similar_cases(baby_id, context_data, video_obs, audio_obs, top_k=3)
                analysis_result = reason_cry_cause(scores, video_obs, audio_obs, context_data, similar_cases=similar_cases)
                
            # E2E 성공 결과 저장 및 피드백용 세션 캐싱
            st.session_state.analysis_results = analysis_result
            st.session_state.last_predicted_probs = analysis_result.get("probabilities", {})
            st.session_state.last_video_obs = video_obs
            st.session_state.last_audio_obs = audio_obs
            st.session_state.last_context_data = context_data
            st.session_state.analyzed = True
            
            # output.log 에 누적 기록
            log_entry = {
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "baby_id": baby_id,
                "video_file": uploaded_file.name,
                "parent_context": context_data,
                "video_observation": video_obs,
                "audio_observation": audio_obs,
                "calculated_scores": scores,
                "comprehensive_analysis": analysis_result
            }
            with open("output.log", "a", encoding="utf-8") as log_file:
                log_file.write(f"=== ANALYSIS RUN AT {log_entry['timestamp']} FOR {uploaded_file.name} ===\n")
                log_file.write(json.dumps(log_entry, indent=2, ensure_ascii=False))
                log_file.write("\n======================================================================\n\n")

        except Exception as e:
            st.error(f"E2E 분석 과정에서 장애가 발생했습니다: {e}")
        finally:
            # 로컬 임시 파일 자원 완전 해제 및 삭제 진행 (Windows WinError 32 안전 방어)
            if temp_video_path and os.path.exists(temp_video_path):
                try: os.remove(temp_video_path)
                except Exception as del_err: print(f"temp_video 삭제 실패: {del_err}")
                
            if 'temp_audio_path' in locals() and os.path.exists(temp_audio_path):
                try: os.remove(temp_audio_path)
                except Exception as del_err: print(f"temp_audio 삭제 실패: {del_err}")
                
            if 'temp_compressed_video_path' in locals() and os.path.exists(temp_compressed_video_path):
                try: os.remove(temp_compressed_video_path)
                except Exception as del_err: print(f"temp_compressed_video 삭제 실패: {del_err}")
                
st.markdown("</div>", unsafe_allow_html=True)


# 7. E2E 결과 렌더링 및 피드백 폼 노출
if st.session_state.analyzed and st.session_state.analysis_results:
    res = st.session_state.analysis_results
    
    st.markdown("<div class='baby-card'>", unsafe_allow_html=True)
    st.write("<div class='card-title'>📊 종합 진단 리포트</div>", unsafe_allow_html=True)
    
    # 1위 원인 카드
    st.markdown(f"""
    <div class='report-box'>
        <h3 style='margin: 0; color: #E07A5F;'>🎯 유력 원인: {res.get('primary_reason')}</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # 확률 차트 드로잉
    st.write("#### [원인별 예측 확률 분포]")
    probs = res.get("probabilities", {})
    korean_labels = {
        "hunger": "🍼 배고픔",
        "gas_or_burp": "💨 배앓이",
        "sleepy": "💤 졸림",
        "diaper": "🧷 기저귀",
        "comfort_and_attachment": "🧸 안아주기",
        "pain_or_discomfort": "🌡️ 아픔"
    }
    chart_data = {korean_labels.get(k, k): v * 100 for k, v in probs.items()}
    df = pd.DataFrame(list(chart_data.items()), columns=["원인", "확률 (%)"])
    
    import altair as alt
    chart = alt.Chart(df).mark_bar(color="#FFA3A3").encode(
        x=alt.X('원인:N', title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y('확률 (%):Q', title="확률 (%)")
    ).properties(
        height=300
    )
    st.altair_chart(chart, use_container_width=True)
    
    # 추론 세부 근거
    st.write("#### [추론 상세 근거]")
    st.info(res.get("reasoning_details"))
    
    # 행동 가이드 지침
    st.write("#### [초보 아빠를 위한 권장 행동 요령]")
    for action in res.get("care_actions", []):
        st.markdown(f"**{action.get('priority')}. {action.get('title')}**")
        st.write(action.get('description'))
        st.write("---")
        
    # 경고창
    st.write("#### [의학적 안전 안내]")
    st.markdown(f"<div class='alert-box'>🚨 {res.get('warning_or_red_flags')}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # 8. 복합 피드백 수집 폼 (Multi-select)
    st.markdown("<div class='baby-card'>", unsafe_allow_html=True)
    st.write("<div class='card-title'>❤️ 실제 어떤 조치로 아기가 그쳤나요? (복수 선택 가능)</div>", unsafe_allow_html=True)
    st.write("<small style='color: #8C8282;'>아기는 배가 아프면서 동시에 안아주기를 바랄 수 있습니다. 실제 효과를 본 모든 항목을 선택해주세요.</small>", unsafe_allow_html=True)
    
    col_fb1, col_fb2 = st.columns(2)
    with col_fb1:
        f_hunger = st.checkbox("🍼 수유를 주니 그쳤어요")
        f_gas = st.checkbox("💨 트림을 시키거나 배 마사지를 해주니 그쳤어요")
        f_sleepy = st.checkbox("💤 토닥이며 재워주니 그쳤어요")
    with col_fb2:
        f_diaper = st.checkbox("🧷 기저귀를 갈아주니 그쳤어요")
        f_comfort = st.checkbox("🫂 수유나 기저귀 변경 없이 그냥 안아만 주었는데도 그쳤어요")
        f_pain = st.checkbox("🌡️ 해열제를 투약하거나 옷을 가볍게 입혀주니 그쳤어요")

    if st.button("피드백 제출 및 개인화 학습 완료", use_container_width=True):
        actual_remedies = []
        if f_hunger: actual_remedies.append("hunger")
        if f_gas: actual_remedies.append("gas_or_burp")
        if f_sleepy: actual_remedies.append("sleepy")
        if f_diaper: actual_remedies.append("diaper")
        if f_comfort: actual_remedies.append("comfort_and_attachment")
        if f_pain: actual_remedies.append("pain_or_discomfort")
        
        if not actual_remedies:
            st.warning("선택된 조치 사항이 없습니다. 최소 하나 이상의 조치 사항을 선택해 주세요.")
        else:
            # 개인화 피드백 반영 (기존 저장 구조 갱신)
            update_personal_biases(
                baby_id=baby_id,
                predicted_probs=st.session_state.last_predicted_probs,
                actual_remedies=actual_remedies
            )
            # feedbacks.json 에 E2E 상세 상황까지 누적 (KNN / Few-shot 데이터 원천 확보)
            save_feedback_log(
                baby_id=baby_id,
                predicted_probs=st.session_state.last_predicted_probs,
                actual_remedies=actual_remedies,
                parent_context=st.session_state.last_context_data,
                video_obs=st.session_state.last_video_obs,
                audio_obs=st.session_state.last_audio_obs
            )
            
            st.success(f"🎉 '{baby_id}'의 대처 이력 피드백과 E2E 상황 로그가 성공적으로 저장되었습니다! 다음 진단부터 KNN 상황 검색 및 Few-shot 러닝에 연동되어 최적화됩니다.")
            st.session_state.analyzed = False # 폼 리셋용
    st.markdown("</div>", unsafe_allow_html=True)
