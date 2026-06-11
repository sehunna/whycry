import os
try:
    from moviepy.editor import VideoFileClip
except ImportError:
    from moviepy import VideoFileClip

def extract_audio(video_path: str, output_audio_path: str = None) -> str:
    """
    영상 파일에서 오디오 스트림을 무손실 WAV 형식으로 추출하여 저장합니다.
    
    :param video_path: 원본 영상 파일 경로
    :param output_audio_path: 저장될 WAV 파일 경로 (지정하지 않으면 원본 영상 파일 이름의 확장자만 .wav로 변경)
    :return: 추출된 오디오 파일 경로
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"원본 영상 파일을 찾을 수 없습니다: {video_path}")
        
    if output_audio_path is None:
        base_name, _ = os.path.splitext(video_path)
        output_audio_path = f"{base_name}.wav"
        
    print(f"[Audio Extractor] '{video_path}'에서 오디오 추출 중 -> '{output_audio_path}'")
    
    try:
        video_clip = VideoFileClip(video_path)
        if video_clip.audio is None:
            raise ValueError("영상 파일에 오디오 트랙이 존재하지 않습니다.")
            
        # PCM 16-bit WAV 형식으로 오디오 추출
        # fps=16000(Gemini 및 음성인식 분석에 적합한 16kHz) 또는 기본 44100Hz로 추출합니다.
        # 여기서는 기본 CD 음질인 44100Hz로 추출합니다.
        video_clip.audio.write_audiofile(
            output_audio_path,
            codec='pcm_s16le',
            ffmpeg_params=["-ac", "1"] # 모노 채널로 변환하여 분석 효율 증가
        )
        video_clip.close()
    except Exception as e:
        print(f"[Audio Extractor] 오디오 추출 중 오류 발생: {e}")
        raise
        
    print(f"[Audio Extractor] 오디오 추출 완료: {output_audio_path}")
    return output_audio_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("사용법: python audio_extractor.py <video_path>")
        sys.exit(1)
    
    try:
        out_path = extract_audio(sys.argv[1])
        print(f"추출 성공: {out_path}")
    except Exception as err:
        print(f"추출 실패: {err}")
