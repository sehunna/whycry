import json
import time
from pydantic import BaseModel, Field
from typing import List
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL

class ProbabilityDistribution(BaseModel):
    hunger: float = Field(description="배고픔 확률 (0.0 ~ 1.0)")
    gas_or_burp: float = Field(description="가스 참/트림 필요 확률 (0.0 ~ 1.0)")
    sleepy: float = Field(description="졸림 확률 (0.0 ~ 1.0)")
    diaper: float = Field(description="기저귀 문제 확률 (0.0 ~ 1.0)")
    comfort_and_attachment: float = Field(description="정서적 안아주기 및 애착 요구 확률 (0.0 ~ 1.0)")
    pain_or_discomfort: float = Field(description="통증/신체적 불편함 확률 (0.0 ~ 1.0)")

class CareAction(BaseModel):
    priority: int = Field(description="조치 우선순위 (1이 가장 높음)")
    title: str = Field(description="행동 지침 제목")
    description: str = Field(description="부모가 지금 바로 시도해볼 상세 행동 요령 (최대 2문장 이내로 매우 간결하게 핵심만 작성)")

class ComprehensiveAnalysis(BaseModel):
    probabilities: ProbabilityDistribution = Field(description="각 원인별 추론 확률 분포 (모든 원인의 확률 합계가 1.0이 되도록 배분)")
    primary_reason: str = Field(description="가장 유력한 원인에 대한 짤막한 핵심 한 줄 요약")
    reasoning_details: str = Field(description="입력된 관찰 점수, 비디오/오디오 단서, 아기 연령 및 컨텍스트에 근거한 추론 과정 설명 (핵심 오사 및 원인 분석 위주로 3~4문장 이내로 매우 명확하고 짧게 작성)")
    care_actions: List[CareAction] = Field(description="부모가 당장 순서대로 취해야 할 가이드 행동 지침 목록 (최대 4개 이내)")
    warning_or_red_flags: str = Field(description="의학적 경고 징후나 긴급 응급 상황 안내 (1~2문장 이내로 매우 짧고 간결하게 작성)")

def reason_cry_cause(scores: dict, video_obs: dict, audio_obs: dict, context: dict, similar_cases: list = None) -> dict:
    """
    1차 스코어 계산 결과와 원천 관찰 데이터, 그리고 과거 유사 상황 해결 사례들(Few-shot)을 활용하여
    Gemini LLM을 통해 종합적인 우는 원인 분석 확률과 조치 방안을 생성합니다.
    서버 일시적 오류(503) 또는 일시적 한도 초과(429) 시 자동으로 재시도합니다.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY 환경 변수가 정의되지 않았습니다.")

    client = genai.Client(api_key=GEMINI_API_KEY)

    # 0. 과거 유사 사례 텍스트 포맷팅 (Few-Shot Context 구성)
    similar_cases_prompt = ""
    if similar_cases:
        similar_cases_prompt = "\n[이 아기(baby_id)의 과거 유사 상황 대처 전례 (Few-shot Examples)]\n"
        for idx, case in enumerate(similar_cases):
            rem = ", ".join([r.upper() for r in case.get("actual_remedies", [])])
            ctx = case.get("parent_context", {})
            v_obs = case.get("video_observation", {})
            a_obs = case.get("audio_observation", {})
            
            similar_cases_prompt += (
                f"- 사례 {idx + 1}: 수유 후 {ctx.get('last_feeding_minutes_ago')}분 경과, "
                f"기저귀 교체 후 {ctx.get('last_diaper_change_minutes_ago')}분 경과한 상태. "
                f"신체 동작 특징(손가락 입에 가져감: {v_obs.get('hand_to_mouth')}, 표정 찌푸림: {v_obs.get('facial_grimace')}, "
                f"다리 배로 당김: {v_obs.get('leg_pull_to_belly')}), 울음 소리 특징(패턴: {a_obs.get('cry_pattern')}). "
                f"➡️ 당시 실제로 아기를 울음 그치게 했던 조치: {rem}\n"
            )
    else:
        similar_cases_prompt = "\n[이 아기(baby_id)의 과거 대처 사례 정보가 아직 없습니다. 일반 소아과 진단 지침을 따릅니다.]\n"

    # 현재 상황 데이터 포맷팅
    input_summary = f"""
    [현재 분석 중인 상황 정보]
    [1차 계산된 원인 점수 (가중치 기반)]
    - 배고픔(Hunger): {scores.get('hunger')}점
    - 가스 참/트림 필요(Gas/Burp): {scores.get('gas_or_burp')}점
    - 졸림(Sleepy): {scores.get('sleepy')}점
    - 기저귀(Diaper): {scores.get('diaper')}점
    - 정서적 안아주기/애착(Comfort & Attachment): {scores.get('comfort_and_attachment')}점
    - 통증/불편함(Pain/Discomfort): {scores.get('pain_or_discomfort')}점

    [비디오 관찰 데이터 (시각 정보)]
    - 손을 입으로 가져감: {video_obs.get('hand_to_mouth')}
    - 입을 빠는 듯 오물거림: {video_obs.get('mouth_movement')}
    - 눈 감음 상태: {video_obs.get('eye_closing')}
    - 얼굴 찌푸림: {video_obs.get('facial_grimace')}
    - 몸을 비틂: {video_obs.get('body_squirming')}
    - 다리를 배로 당김: {video_obs.get('leg_pull_to_belly')}
    - 등을 활처럼 젖힘: {video_obs.get('back_arching')}
    - 움직임 레벨: {video_obs.get('movement_level')}
    - 긴급 관찰 증상(시각 위험 징후): {video_obs.get('visible_red_flags')}

    [오디오 관찰 데이터 (음성 정보)]
    - 아기 울음 감지: {audio_obs.get('cry_present')}
    - 울음 강도: {audio_obs.get('cry_intensity')}
    - 울음 패턴: {audio_obs.get('cry_pattern')}
    - 울음 추정 감정: {audio_obs.get('estimated_emotion')}

    [아기 기본 상황 컨텍스트]
    - 아기 생후 일수: {context.get('age_days')}일
    - 수유 형태: {context.get('feeding_type')}
    - 마지막 수유 후 경과 시간: {context.get('last_feeding_minutes_ago')}분
    - 마지막 기저귀 변경 후 경과 시간: {context.get('last_diaper_change_minutes_ago')}분
    - 마지막 수면 종료 후 깨어 있는 시간: {context.get('last_sleep_ended_minutes_ago')}분
    - 최근 수유 후 트림 여부: {context.get('burped_after_last_feeding')}
    - 아기 체온: {context.get('temperature_celsius')}°C
    """

    prompt = f"""
    당신은 소아과 의사이자 유아 행동 분석 전문가, 베테랑 육아 상담사입니다.
    제시된 1차 스코어링 점수와 비디오/오디오 관찰 정보, 그리고 아기의 컨텍스트 정보(수유 형태 및 시간, 체온 등)를 종합적으로 분석해 주세요.
    
    특히 아래의 과거 해결 전례(Few-shot Examples)들을 면밀히 읽고, 현재 아기의 신체 특징 및 상황과 과거에 해결된 울음 상황의 정합성을 비교 대조하여 아기 고유의 개인적 특성을 최종 확률 분포에 가산 혹은 보정해 주세요.
    
    출력 필드의 설명(description) 조건에 제시된 글자 수/문장 수 제한을 엄격하게 준수하여 군더더기 없이 간결하게 대답해 주세요.
    
    과거 기록 정보:
    {similar_cases_prompt}
    
    분석할 데이터:
    {input_summary}
    """

    result_json = None
    max_retries = 5
    retry_delay = 3

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ComprehensiveAnalysis,
                    temperature=0.2,
                )
            )
            result_json = json.loads(response.text)
            break
        except Exception as e:
            err_msg = str(e)
            if ("503" in err_msg or "429" in err_msg) and attempt < max_retries - 1:
                print(f"[Reasoner][경고] 서버 일시적 혼잡 또는 할당량 초과 발생. {retry_delay}초 후 재시도합니다... (시도 {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise

    return result_json

if __name__ == "__main__":
    mock_scores = {"hunger": 75, "gas_or_burp": 15, "sleepy": 0, "diaper": 20, "comfort_and_attachment": 40, "pain_or_discomfort": 0}
    mock_video = {"hand_to_mouth": True, "mouth_movement": True, "eye_closing": "low", "facial_grimace": False, "body_squirming": False, "leg_pull_to_belly": "no", "back_arching": "no", "movement_level": "active", "visible_red_flags": []}
    mock_audio = {"cry_present": True, "cry_intensity": "moderate", "cry_pattern": "intermittent", "estimated_emotion": "hungry"}
    mock_context = {"age_days": 38, "feeding_type": "formula", "last_feeding_minutes_ago": 165, "last_diaper_change_minutes_ago": 80, "last_sleep_ended_minutes_ago": 45, "burped_after_last_feeding": False, "temperature_celsius": 36.8}
    
    try:
        res = reason_cry_cause(mock_scores, mock_video, mock_audio, mock_context)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    except Exception as err:
        print(f"테스트 실패: {err}")
