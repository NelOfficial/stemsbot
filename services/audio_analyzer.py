import librosa
import numpy as np
import asyncio
import scipy.signal

MIN_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
MAJ_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
PITCHES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

RELATIVE_KEYS = {
    "C Major": "A Minor", "C# Major": "A# Minor", "D Major": "B Minor", "D# Major": "C Minor",
    "E Major": "C# Minor", "F Major": "D Minor", "F# Major": "D# Minor", "G Major": "E Minor",
    "G# Major": "F Minor", "A Major": "F# Minor", "A# Major": "G Minor", "B Major": "G# Minor",
    "A Minor": "C Major", "A# Minor": "C# Major", "B Minor": "D Major", "C Minor": "D# Major",
    "C# Minor": "E Major", "D Minor": "F Major", "D# Minor": "F# Major", "E Minor": "G Major",
    "F Minor": "G# Major", "F# Minor": "A Major", "G Minor": "A# Major", "G# Minor": "B Major"
}

# dsp
def _calculate_bpm(y, sr, duration):
    sos = scipy.signal.butter(4, [400, 1000], btype='bandpass', fs=sr, output='sos')
    y_filt = scipy.signal.sosfilt(sos, y)
    onset_env = librosa.onset.onset_strength(y=y_filt, sr=sr, hop_length=256)
    
    if duration < 10.0:
        peaks = librosa.util.peak_pick(onset_env, pre_max=3, post_max=3, pre_avg=3, post_avg=5, delta=0.5, wait=10)
        if len(peaks) > 1:
            times = librosa.frames_to_time(peaks, sr=sr, hop_length=256)
            avg_diff = np.median(np.diff(times))
            base_bpm = round(60.0 / avg_diff) if avg_diff > 0 else 120
        else:
            base_bpm = 120
    else:
        tempo = librosa.feature.tempo(onset_envelope=onset_env, sr=sr, hop_length=256)[0]
        base_bpm = round(float(tempo))
        
    if base_bpm < 95: return base_bpm * 2
    elif 95 <= base_bpm < 120: return round(base_bpm * 1.5)
    elif base_bpm > 190: return round(base_bpm / 2)
    return base_bpm

def _calculate_key_and_detune(y, sr):
    y_harm, _ = librosa.effects.hpss(y)
    tuning = librosa.estimate_tuning(y=y_harm, sr=sr)
    if abs(tuning) < 0.15: tuning = 0.0
    
    freq_hz = 440.0 * (2.0 ** (tuning / 12.0))
    detune_str = f"{round(freq_hz)} Hz" if abs(440 - round(freq_hz)) >= 1 else "440 Hz (Ok)"

    chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr, tuning=tuning, fmin=librosa.note_to_hz('C1'), n_octaves=6)
    chroma_sum = np.sum(chroma, axis=1)
    
    best_corr, best_key = -1.0, ""
    for i in range(12):
        c_min = np.corrcoef(chroma_sum, np.roll(MIN_PROFILE, i))[0, 1] * 1.1
        c_maj = np.corrcoef(chroma_sum, np.roll(MAJ_PROFILE, i))[0, 1]
        if c_min > best_corr: best_corr, best_key = c_min, f"{PITCHES[i]} Minor"
        if c_maj > best_corr: best_corr, best_key = c_maj, f"{PITCHES[i]} Major"
        
    return best_key, detune_str

# fast mode
async def analyze_track_async(file_path: str, progress_callback=None) -> dict:
    try:
        y, sr = await asyncio.to_thread(librosa.load, file_path, sr=22050, mono=True)
        y_hd, sr_hd = await asyncio.to_thread(librosa.load, file_path, sr=44100, mono=True)
        duration = librosa.get_duration(y=y_hd, sr=sr_hd)

        bpm = await asyncio.to_thread(_calculate_bpm, y_hd, sr_hd, duration)
        key, detune = await asyncio.to_thread(_calculate_key_and_detune, y, sr)

        return {"bpm": bpm, "key": key, "relative_key": RELATIVE_KEYS.get(key, "Unknown"), "detune": detune}
    except Exception as e:
        return {"error": str(e)}

# advanced mode
async def analyze_stems_async(drums_path: str, bass_path: str, other_path: str, progress_callback=None) -> dict:
    try:
        if progress_callback: await progress_callback("bpm analyze...")
        
        y_drums, sr_hd = await asyncio.to_thread(librosa.load, drums_path, sr=44100, mono=True)
        duration = librosa.get_duration(y=y_drums, sr=sr_hd)
        bpm = await asyncio.to_thread(_calculate_bpm, y_drums, sr_hd, duration)

        if progress_callback: await progress_callback("analyzing key...")
        
        def load_and_mix_stems():
            y_bass, sr = librosa.load(bass_path, sr=22050, mono=True)
            y_other, _ = librosa.load(other_path, sr=22050, mono=True)
            min_len = min(len(y_bass), len(y_other))
            return y_bass[:min_len] + y_other[:min_len], sr
            
        y_mixed, sr = await asyncio.to_thread(load_and_mix_stems)
        key, detune = await asyncio.to_thread(_calculate_key_and_detune, y_mixed, sr)

        return {"bpm": bpm, "key": key, "relative_key": RELATIVE_KEYS.get(key, "Unknown"), "detune": detune}
    except Exception as e:
        return {"error": str(e)}