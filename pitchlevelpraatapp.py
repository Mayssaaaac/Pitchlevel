from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from moviepy.editor import VideoFileClip
import parselmouth
import numpy as np
import noisereduce as nr
import os
import tempfile

app = FastAPI()

TOTAL_CRITERIA = 4


def analyze_pitch(audio_data):
    sound = parselmouth.Sound(audio_data)

    sound_values = sound.values
    reduced_noise = nr.reduce_noise(y=sound_values, sr=sound.sampling_frequency)
    sound_reduced_noise = parselmouth.Sound(reduced_noise, sampling_frequency=sound.sampling_frequency)
    pitch = sound_reduced_noise.to_pitch()

    pitch_values = pitch.selected_array['frequency']
    pitch_values = pitch_values[(pitch_values >= 75) & (pitch_values <= 400)]

    std_dev = np.std(pitch_values)
    return std_dev

def classify_speaker(std_dev):
    if 10 <= std_dev <= 60:
        return "Balanced"
    else:
        return "Unbalanced"

def analyze_volume_praat(audio_data):
    snd = parselmouth.Sound(audio_data)

    intensity = snd.to_intensity()
    average_intensity = np.mean(intensity.values)

    low_threshold = 45  
    high_threshold = 75 

    if average_intensity < low_threshold:
        return "Volume too low"
    elif average_intensity > high_threshold:
        return "Volume too loud"
    else:
        return "Volume is ideal"    

def analyze_silences_praat(sound, noise_reduction=True, silence_threshold=40, min_silence_duration=0.5):

    if noise_reduction:
        audio_data = sound.values[0]
        sampling_rate = sound.sampling_frequency
        noise_clip = audio_data[:int(sampling_rate * 0.5)]
        reduced_noise_audio = nr.reduce_noise(audio_data, sr=sampling_rate)
        sound = parselmouth.Sound(reduced_noise_audio, sampling_rate)

    intensity = sound.to_intensity()
    intensity_values = intensity.values[0]
    times = intensity.xs()

    silences = []
    current_silence = None
    for time, value in zip(times, intensity_values):
        if value < silence_threshold:
            if current_silence is None:
                current_silence = [time, None]
            continue
        if current_silence is not None:
            current_silence[1] = time
            if current_silence[1] - current_silence[0] >= min_silence_duration:
                silences.append(current_silence)
            current_silence = None

    if current_silence is not None and current_silence[1] is None:
        current_silence[1] = time
        if current_silence[1] - current_silence[0] >= min_silence_duration:
            silences.append(current_silence)

    return silences

def classify_silences(silences, total_duration_threshold=15, initial_delay_threshold=5, long_silence_threshold=9):

    total_silence_duration = sum(end - start for start, end in silences)
    longest_silence = max((end - start for start, end in silences), default=0)
    initial_delay = silences[0][0] if silences and silences[0][0] == 0 else 0


    if longest_silence >= long_silence_threshold:
        return "silence too long"
    if total_silence_duration > total_duration_threshold:
        return "too much silence"
    if initial_delay >= initial_delay_threshold:
        return "delay"
    else:
        return "normal"


def calculate_score(positive_criteria_count, available_criteria_count):
    if available_criteria_count == 0:
        return 0  
    return (positive_criteria_count / available_criteria_count) * 100    

@app.post("/analyze_audio/")  
async def analyze_pitch_endpoint(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(await file.read())
        temp_file_path = temp_file.name

    std_dev = analyze_pitch(temp_file_path)
    pitch_result = classify_speaker(std_dev)

    volume_result = analyze_volume_praat(temp_file_path)
    pitch_result = classify_speaker(std_dev)

    sound = parselmouth.Sound(temp_file_path)
    silences = analyze_silences_praat(sound)
    silence_result = classify_silences(silences)
    
    available_criteria_count = 3
    positive_criteria_count = (1 if pitch_result == "Balanced" else 0) + \
                              (1 if volume_result == "Volume is ideal" else 0) + \
                              (1 if silence_result == "normal" else 0)

    overall_score = calculate_score(positive_criteria_count, available_criteria_count)

    return {
        "pitch_characteristic": pitch_result,
        "volume_characteristic": volume_result,
        "silence_characteristic": silence_result,
        "overall_score": overall_score
    }



@app.post("/analyze_video/")
async def analyze_video_pitch(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as video_file:
        video_file.write(await file.read())
        video_file_path = video_file.name

    video_clip = VideoFileClip(video_file_path)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
        video_clip.audio.write_audiofile(audio_file.name)
        audio_file_path = audio_file.name
        
    sound = parselmouth.Sound(audio_file_path)
    std_dev = analyze_pitch(audio_file_path)
    pitch_result = classify_speaker(std_dev)

    volume_result = analyze_volume_praat(audio_file_path)

    silences = analyze_silences_praat(sound)
    silence_result = classify_silences(silences)

    available_criteria_count = 3  
    positive_criteria_count = (1 if pitch_result == "Balanced" else 0) + \
                              (1 if volume_result == "Volume is ideal" else 0) + \
                              (1 if silence_result == "normal" else 0)
    overall_score = calculate_score(positive_criteria_count, available_criteria_count)

    
    os.unlink(video_file_path)
    os.unlink(audio_file_path)

    return {
        "pitch_characteristic": pitch_result,
        "volume_characteristic": volume_result,
        "silence_characteristic": silence_result,
        "overall_score": overall_score
    }

