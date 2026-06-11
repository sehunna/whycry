import os
import time
import json
from pydantic import BaseModel, Field
from typing import List
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL

class VideoObservation(BaseModel):
    hand_to_mouth: bool = Field(description="아기가 손을 입이나 얼굴 주변으로 가져가는 행동 여부")
    mouth_movement: bool = Field(description="아기가 빠는 듯한 입 모양을 하거나 혀를 내미는 등의 움직임을 보이는지 여부")
    eye_closing: str = Field(description="눈을 질끈 감고 있거나 졸린 듯 감고 있는 강도/빈도 ('none', 'low', 'moderate', 'high')")
    facial_grimace: bool = Field(description="얼굴을 찡그리고 찌푸리는 표정 여부")
    body_squirming: bool = Field(description="몸을 비틀거나 꼼지락거리며 불편해하는 행동 여부")
    leg_pull_to_belly: str = Field(description="다리를 배 쪽으로 오므리거나 끌어당기는 행동 여부 ('no', 'possible', 'evident')")
    back_arching: str = Field(description="등을 뒤로 활처럼 젖히는 행동 여부 ('no', 'possible', 'evident')")
    movement_level: str = Field(description="전반적인 신체 움직임 강도 ('calm', 'active', 'hyperactive')")
    face_visible: bool = Field(description="영상 내 아기의 얼굴이 식별 가능한 정도로 노출되는지 여부")
    upper_body_visible: bool = Field(description="영상 내 아기의 상반신이 식별 가능한지 여부")
    visible_red_flags: List[str] = Field(description="즉각적인 소아과 검진이 필요해 보이는 심각한 징후 (예: 청색증 'cyanosis', 호흡 곤란 'breathing_difficulty' 등. 관찰되지 않으면 빈 배열)")

def analyze_video(video_path: str) -> dict:
    """
    Gemini Video Understanding API를 사용해 영상에서 아기의 시각적 행동 상태를 분석하여 구조화된 JSON 데이터로 변환합니다.
    서버 일시적 에러(503) 또는 일시적 한도 초과(429) 시 자동으로 재시도합니다.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"비디오 파일을 찾을 수 없습니다: {video_path}")

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY 환경 변수가 정의되지 않았습니다.")

    # GenAI 클라이언트 초기화
    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"[Video Analyzer] '{video_path}' 파일을 Gemini File API로 업로드합니다...")
    video_file = client.files.upload(file=video_path)
    print(f"[Video Analyzer] 업로드 완료. 파일명: {video_file.name}. ACTIVE 상태 대기 중...")

    # 파일이 ACTIVE 상태가 될 때까지 폴링
    while video_file.state.name == "PROCESSING":
        time.sleep(1)
        video_file = client.files.get(name=video_file.name)
        print(f"[Video Analyzer] 파일 상태 체크: {video_file.state.name}")

    if video_file.state.name == "FAILED":
        raise ValueError("Gemini가 동영상 파일을 처리하는 데 실패했습니다.")

    print("[Video Analyzer] 파일 처리 완료. 비디오 상태 분석을 수행합니다...")

    prompt = (
        "아기가 우는 10~15초 분량의 영상입니다. 아기의 미세한 행동, 표정, 손동작, 다리 움직임, "
        "눈의 상태 등을 자세히 분석하여 제공된 스키마 형식에 맞춰 관찰 결과를 JSON 데이터로 출력해 주세요."
    )

    result_json = None
    max_retries = 5
    retry_delay = 3

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[video_file, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=VideoObservation,
                    temperature=0.1,
                ),
            )
            result_json = json.loads(response.text)
            break  # 성공 시 루프 탈출
        except Exception as e:
            err_msg = str(e)
            # 503 Unavailable 또는 429 Rate Limit 발생 시 재시도 수행
            if ("503" in err_msg or "429" in err_msg) and attempt < max_retries - 1:
                print(f"[Video Analyzer][경고] 서버 일시적 혼잡 또는 할당량 초과 발생. {retry_delay}초 후 재시도합니다... (시도 {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2  # 점진적 지연 시간 증가 (Exponential Backoff)
            else:
                # 마지막 시도이거나 다른 에러인 경우 파일 정리 후 예외 상위 전파
                try:
                    client.files.delete(name=video_file.name)
                except:
                    pass
                raise
    else:
        # 예외 없이 루프가 끝났지만 결과가 없는 극단적인 경우에 대한 방어
        try:
            client.files.delete(name=video_file.name)
        except:
            pass
        raise RuntimeError("재시도 한도를 초과하여 비디오 분석에 실패했습니다.")

    # 사용 완료한 비디오 파일 삭제 (Gemini 클라우드 저장소 공간 정리)
    try:
        client.files.delete(name=video_file.name)
        print("[Video Analyzer] Gemini 저장소에서 임시 동영상 파일 제거 완료.")
    except Exception as delete_error:
        print(f"[Video Analyzer] 임시 파일 제거 실패: {delete_error}")

    return result_json

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("사용법: python video_analyzer.py <video_path>")
        sys.exit(1)
        
    test_video = sys.argv[1]
    try:
        result = analyze_video(test_video)
        print("\n--- [Video] 분석 결과 ---")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as err:
        print(f"오류 발생: {err}")
