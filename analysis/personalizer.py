import os
import json
import datetime

BABY_STATUS_FILE = "baby_status.json"
FEEDBACKS_FILE = "feedbacks.json"

def _load_json(file_path: str, default_value) -> dict:
    if not os.path.exists(file_path):
        return default_value
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Personalizer][경고] {file_path} 로드 실패: {e}")
        return default_value

def _save_json(file_path: str, data: dict or list):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Personalizer][오류] {file_path} 저장 실패: {e}")

def initialize_baby(baby_id: str) -> dict:
    data = _load_json(BABY_STATUS_FILE, {})
    if baby_id not in data:
        data[baby_id] = {
            "age_days": 30,
            "feeding_type": "mixed",
            "last_feeding_timestamp": None,
            "last_diaper_timestamp": None,
            "last_sleep_timestamp": None,
            "parent_settings": {
                "frequent_colic": False,
                "high_comfort_need": False
            },
            "personal_biases": {
                "hunger": 0,
                "gas_or_burp": 0,
                "sleepy": 0,
                "diaper": 0,
                "comfort_and_attachment": 0,
                "pain_or_discomfort": 0
            }
        }
        _save_json(BABY_STATUS_FILE, data)
    return data[baby_id]

def get_personal_biases(baby_id: str) -> dict:
    """
    아기의 기본적인 부모 기질 설정 보정치만 반환합니다.
    (글로벌 수치 바이어스로 인한 오작동 왜곡을 방지하기 위해 피드백 누적 Bias는 KNN/Few-shot으로 대체되었습니다.)
    """
    baby_profile = initialize_baby(baby_id)
    biases = {
        "hunger": 0,
        "gas_or_burp": 0,
        "sleepy": 0,
        "diaper": 0,
        "comfort_and_attachment": 0,
        "pain_or_discomfort": 0
    }
    settings = baby_profile.get("parent_settings", {})
    if settings.get("frequent_colic", False):
        biases["gas_or_burp"] = 15
    if settings.get("high_comfort_need", False):
        biases["comfort_and_attachment"] = 15
    return biases

def find_similar_cases(baby_id: str, current_context: dict, current_video: dict, current_audio: dict, top_k: int = 3) -> list:
    """
    피드백 로그(feedbacks.json)에서 현재의 상황과 가장 수학적으로 유사한 과거 해결 케이스 N개를 찾습니다. (KNN)
    """
    feedbacks = _load_json(FEEDBACKS_FILE, [])
    
    # 해당 아기의 과거 피드백 기록만 필터링
    baby_history = [fb for fb in feedbacks if fb.get("baby_id") == baby_id]
    if not baby_history:
        return []
        
    scored_cases = []
    
    # 가중치 변수 선언
    W_FEEDING = 0.5
    W_DIAPER = 0.2
    W_SLEEP = 0.3
    W_VIDEO = 2.0
    W_AUDIO = 1.5
    
    for past in baby_history:
        past_context = past.get("parent_context", {})
        # 과거 피드백 스키마 호환성 방어
        if not past_context:
            continue
            
        past_video = past.get("video_observation", {})
        past_audio = past.get("audio_observation", {})
        
        # 1. 수유/기저귀/수면 경과 시간 차이 계산
        diff_feeding = abs(current_context.get("last_feeding_minutes_ago", 120) - past_context.get("last_feeding_minutes_ago", 120)) / 60.0
        diff_diaper = abs(current_context.get("last_diaper_change_minutes_ago", 90) - past_context.get("last_diaper_change_minutes_ago", 90)) / 60.0
        diff_sleep = abs(current_context.get("last_sleep_ended_minutes_ago", 60) - past_context.get("last_sleep_ended_minutes_ago", 60)) / 60.0
        
        distance = (diff_feeding * W_FEEDING) + (diff_diaper * W_DIAPER) + (diff_sleep * W_SLEEP)
        
        # 2. 비디오 시각 관찰 일치도 계산
        video_keys_bool = ["hand_to_mouth", "mouth_movement", "facial_grimace", "body_squirming"]
        for k in video_keys_bool:
            if current_video.get(k) != past_video.get(k):
                distance += 1.0 * W_VIDEO
                
        video_keys_enum = ["eye_closing", "leg_pull_to_belly", "back_arching", "movement_level"]
        for k in video_keys_enum:
            if current_video.get(k) != past_video.get(k):
                distance += 1.0 * W_VIDEO
                
        # 3. 오디오 음성 관찰 일치도 계산
        audio_keys = ["cry_pattern", "cry_intensity"]
        for k in audio_keys:
            if current_audio.get(k) != past_audio.get(k):
                distance += 1.0 * W_AUDIO
                
        scored_cases.append((distance, past))
        
    # 거리(distance)가 짧을수록(유사도가 높을수록) 앞서도록 정렬
    scored_cases.sort(key=lambda x: x[0])
    
    # 상위 top_k 개의 과거 사례 반환
    return [item[1] for item in scored_cases[:top_k]]

def update_personal_biases(baby_id: str, predicted_probs: dict, actual_remedies: list):
    """
    (과거 전역 Bias 업데이트 함수 유지 - 스키마 호환 목적)
    실제 피드백을 기록하여 feedbacks.json 에 누적하는 핵심 흐름으로 사용됩니다.
    """
    initialize_baby(baby_id)
    data = _load_json(BABY_STATUS_FILE, {})
    profile = data[baby_id]
    biases = profile.get("personal_biases", {})
    
    sorted_predictions = sorted(predicted_probs.items(), key=lambda x: x[1], reverse=True)
    top2_predicted = [item[0] for item in sorted_predictions[:2]]
    top1_predicted = sorted_predictions[0][0] if sorted_predictions else None
    
    if not actual_remedies:
        return
        
    intersection = set(top2_predicted).intersection(set(actual_remedies))
    if not intersection and top1_predicted:
        biases[top1_predicted] = biases.get(top1_predicted, 0) - 10
        
    for remedy in actual_remedies:
        if remedy in biases:
            biases[remedy] = biases.get(remedy, 0) + 10
            
    for cause in biases:
        biases[cause] = max(-100, min(100, biases[cause]))
        
    profile["personal_biases"] = biases
    data[baby_id] = profile
    _save_json(BABY_STATUS_FILE, data)

def save_feedback_log(baby_id: str, predicted_probs: dict, actual_remedies: list, parent_context: dict = None, video_obs: dict = None, audio_obs: dict = None):
    """
    부모의 피드백 결과와 함께, 당시 상황인 context, video, audio 원천 데이터를 feedbacks.json에 함께 저장합니다.
    이는 추후 KNN 유사 상황 매칭의 중요한 데이터 셋이 됩니다.
    """
    feedbacks = _load_json(FEEDBACKS_FILE, [])
    log_entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "baby_id": baby_id,
        "parent_context": parent_context,
        "video_observation": video_obs,
        "audio_observation": audio_obs,
        "predicted_probabilities": predicted_probs,
        "actual_remedies": actual_remedies
    }
    feedbacks.append(log_entry)
    _save_json(FEEDBACKS_FILE, feedbacks)
    print(f"[Personalizer] E2E 상황을 포함한 피드백 로그가 feedbacks.json에 누적 저장되었습니다.")
