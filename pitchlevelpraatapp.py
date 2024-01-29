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

    available_criteria_count = 2 
    positive_criteria_count = (1 if pitch_result == "Balanced" else 0) + (1 if volume_result == "Volume is ideal" else 0)

    overall_score = calculate_score(positive_criteria_count, available_criteria_count)

    return {
        "pitch_characteristic": pitch_result,
        "volume_characteristic": volume_result,
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

    std_dev = analyze_pitch(audio_file_path)
    pitch_result = classify_speaker(std_dev)

    volume_result = analyze_volume_praat(audio_file_path)

    available_criteria_count = 2  
    positive_criteria_count = (1 if pitch_result == "Balanced" else 0) + (1 if volume_result == "Volume is ideal" else 0)
    overall_score = calculate_score(positive_criteria_count, available_criteria_count)

    
    os.unlink(video_file_path)
    os.unlink(audio_file_path)

    return {
        "pitch_characteristic": pitch_result,
        "volume_characteristic": volume_result,
        "overall_score": overall_score
    }

