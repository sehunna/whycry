def calculate_scores(video_obs: dict, audio_obs: dict, context: dict, baby_id: str = None) -> dict:
    """
    비디오 관찰 데이터, 오디오 관찰 데이터 및 부모 입력 컨텍스트를 결합하여
    아기가 우는 원인별 6대 점수(Hunger, Gas/Burp, Sleepy, Diaper, Comfort/Attachment, Pain/Discomfort)를 계산합니다.
    수유 형태(모유/분유/혼합)에 따라 배고픔 및 배앓이 가중치가 조절됩니다.
    아기 식별자(baby_id)가 제공되면, 과거 피드백 기반 누적 보정치(Bias)를 추가 가산합니다.
    """
    
    # 0. 컨텍스트 데이터 안전 추출
    last_feeding = context.get("last_feeding_minutes_ago", 0)
    last_diaper = context.get("last_diaper_change_minutes_ago", 0)
    last_sleep = context.get("last_sleep_ended_minutes_ago", 0)
    burped = context.get("burped_after_last_feeding", True)
    temp = context.get("temperature_celsius")
    diaper_state = context.get("diaper_state", "unknown") # wet, dirty, dry, unknown
    feeding_type = context.get("feeding_type", "mixed")    # breast (모유), formula (분유), mixed (혼합)

    # 0. 비디오 관찰 데이터 추출
    hand_to_mouth = video_obs.get("hand_to_mouth", False)
    mouth_movement = video_obs.get("mouth_movement", False)
    eye_closing = video_obs.get("eye_closing", "none")
    facial_grimace = video_obs.get("facial_grimace", False)
    body_squirming = video_obs.get("body_squirming", False)
    leg_pull = video_obs.get("leg_pull_to_belly", "no")
    back_arching = video_obs.get("back_arching", "no")
    movement_level = video_obs.get("movement_level", "calm")

    # 0. 오디오 관찰 데이터 추출
    cry_pattern = audio_obs.get("cry_pattern", "none")

    # 1. Hunger Score (배고픔)
    hunger_score = 0
    # 모유/분유 여부에 따른 소화 속도 반영 시간 가중치 차등
    if feeding_type == "breast":
        if last_feeding >= 120:
            hunger_score += 40
        elif last_feeding >= 90:
            hunger_score += 20
    elif feeding_type == "formula":
        if last_feeding >= 150:
            hunger_score += 40
        elif last_feeding >= 120:
            hunger_score += 20
    else: # mixed
        if last_feeding >= 135:
            hunger_score += 40
        elif last_feeding >= 110:
            hunger_score += 20
        
    if hand_to_mouth:
        hunger_score += 20
    if mouth_movement:
        hunger_score += 15
    if cry_pattern == "intermittent":
        hunger_score += 15
    if last_feeding <= 60:
        hunger_score -= 50
    hunger_score = max(0, hunger_score)

    # 2. Gas or Burp Score (가스/트림)
    gas_score = 0
    if body_squirming:
        gas_score += 15
    if leg_pull == "possible":
        gas_score += 15
    elif leg_pull == "evident":
        gas_score += 25
    if facial_grimace:
        gas_score += 15
    if not burped:
        gas_score += 25
        
    # 분유 수유 아기는 젖병 수유 특성상 공기를 더 많이 삼키므로 배앓이 확률 가중치 상승
    if feeding_type == "formula":
        if last_feeding <= 60:
            gas_score += 35
    elif feeding_type == "breast":
        if last_feeding <= 60:
            gas_score += 10
    else: # mixed
        if last_feeding <= 60:
            gas_score += 20

    # 3. Sleepy Score (졸림)
    sleepy_score = 0
    if eye_closing == "moderate":
        sleepy_score += 15
    elif eye_closing == "high":
        sleepy_score += 30
    if movement_level in ["calm", "low"]:
        sleepy_score += 15
    if last_sleep >= 120:
        sleepy_score += 30
    if cry_pattern == "whimpering":
        sleepy_score += 25

    # 4. Diaper Score (기저귀)
    diaper_score = 0
    if last_diaper >= 180:
        diaper_score += 40
    elif last_diaper >= 120:
        diaper_score += 20
    if body_squirming:
        diaper_score += 15
    if hunger_score < 40:
        diaper_score += 20
        
    # 기저귀 젖음 상태가 명시적으로 기입된 경우 강력한 증거로 처리
    if diaper_state in ["wet", "dirty"]:
        diaper_score = max(diaper_score, 80)

    # 5. Comfort & Attachment Score (정서적 요구 및 안아주기)
    comfort_score = 0
    if cry_pattern == "whimpering":
        comfort_score += 25
    if movement_level in ["calm", "low"]:
        comfort_score += 15
        
    # 물리적인 다른 불만족 요인(배고픔, 젖은 기저귀, 수면부족)이 없을수록 단순 애착 요구일 확률이 증가
    if hunger_score < 30:
        comfort_score += 25
    if last_diaper < 90:
        comfort_score += 20
    if last_sleep < 90:
        comfort_score += 15

    # 6. Pain or Discomfort Score (통증/신체적 질병)
    pain_score = 0
    if temp is not None:
        if temp >= 38.0:
            pain_score += 60
        elif temp >= 37.5:
            pain_score += 30
    if back_arching == "possible":
        pain_score += 15
    elif back_arching == "evident":
        pain_score += 30
    if cry_pattern == "sudden_intense":
        pain_score += 30

    scores = {
        "hunger": hunger_score,
        "gas_or_burp": gas_score,
        "sleepy": sleepy_score,
        "diaper": diaper_score,
        "comfort_and_attachment": comfort_score,
        "pain_or_discomfort": pain_score
    }

    # 아기 식별자(baby_id)가 제공되면 로드한 개인화 보정치(Biases) 가산
    if baby_id:
        from analysis.personalizer import get_personal_biases
        biases = get_personal_biases(baby_id)
        for cause in scores:
            scores[cause] = max(0, scores[cause] + biases.get(cause, 0))

    return scores
