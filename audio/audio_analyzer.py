import os
import time
import json
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL

class AudioObservation(BaseModel):
    cry_present: bool = Field(description="울음소리 존재 여부")
    cry_intensity: str = Field(description="울음 강도 ('low', 'moderate', 'high')")
    cry_pattern: str = Field(description="울음 패턴 ('intermittent', 'continuous', 'whimpering', 'sudden_intense')")
    audio_clear: bool = Field(description="음질이 깨끗하고 분석 가능한지 여부")
    estimated_emotion: str = Field(description="울음소리 톤 및 음색 기반 추정 감정/상태 (예: 'hungry', 'sleepy', 'irritated', 'pain', 'scared', 'unknown')")

def analyze_audio(audio_path: str) -> dict:
    """
    Gemini Multimodal API를 사용하여 분리된 아기 울음소리 오디오(.wav)를 분석하고 구조화된 JSON 데이터를 리턴합니다.
    서버 일시적 오류(503) 또는 일시적 한도 초과(429) 시 자동으로 재시도합니다.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {audio_path}")

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY 환경 변수가 정의되지 않았습니다.")

    # GenAI 클라이언트 초기화
    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"[Audio Analyzer] '{audio_path}' 파일을 Gemini File API로 업로드합니다...")
    audio_file = client.files.upload(file=audio_path)
    print(f"[Audio Analyzer] 업로드 완료. 파일명: {audio_file.name}. ACTIVE 상태 대기 중...")

    # 파일이 ACTIVE 상태가 될 때까지 폴링
    while audio_file.state.name == "PROCESSING":
        time.sleep(1)
        audio_file = client.files.get(name=audio_file.name)
        print(f"[Audio Analyzer] 파일 상태 체크: {audio_file.state.name}")

    if audio_file.state.name == "FAILED":
        raise ValueError("Gemini가 오디오 파일을 처리하는 데 실패했습니다.")

    print("[Audio Analyzer] 파일 처리 완료. 오디오 소리 분석을 수행합니다...")

    prompt = (
        "아기의 울음소리 오디오 파일입니다. 울음소리의 주파수, 높낮이 변화 패턴, 리듬 및 강도를 면밀히 분석하여 "
        "제공된 JSON 스키마 형식에 맞춰 아기의 울음 상태 관찰 결과를 출력해 주세요."
    )

    result_json = None
    max_retries = 5
    retry_delay = 3

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[audio_file, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AudioObservation,
                    temperature=0.1,
                ),
            )
            result_json = json.loads(response.text)
            break
        except Exception as e:
            err_msg = str(e)
            if ("503" in err_msg or "429" in err_msg) and attempt < max_retries - 1:
                print(f"[Audio Analyzer][경고] 서버 일시적 혼잡 또는 할당량 초과 발생. {retry_delay}초 후 재시도합니다... (시도 {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                try:
                    client.files.delete(name=audio_file.name)
                except:
                    pass
                raise
    else:
        try:
            client.files.delete(name=audio_file.name)
        except:
            pass
        raise RuntimeError("재시도 한도를 초과하여 오디오 분석에 실패했습니다.")

    # 임시 업로드 파일 삭제
    try:
        client.files.delete(name=audio_file.name)
        print("[Audio Analyzer] Gemini 저장소에서 임시 오디오 파일 제거 완료.")
    except Exception as delete_error:
        print(f"[Audio Analyzer] 임시 파일 제거 실패: {delete_error}")

    return result_json

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("사용법: python audio_analyzer.py <audio_path>")
        sys.exit(1)
        
    test_audio = sys.argv[1]
    try:
        result = analyze_audio(test_audio)
        print("\n--- [Audio] 분석 결과 ---")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as err:
        print(f"오류 발생: {err}")
