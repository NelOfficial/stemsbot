import librosa
import numpy as np
import soundfile as sf
import os
import scipy.signal
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

def extract_one_shots(drums_path, output_folder):
    y, sr = librosa.load(drums_path, sr=44100)
    
    onsets = librosa.onset.onset_detect(y=y, sr=sr, hop_length=512, backtrack=True, delta=0.07)
    onset_samples = librosa.frames_to_samples(onsets)
    
    slices = []
    features = []
    
    for i in range(len(onset_samples)):
        start = onset_samples[i]
        
        next_onset = onset_samples[i+1] if i < len(onset_samples) - 1 else len(y)
        max_end = min(start + int(sr * 0.4), len(y))
        
        end = min(max_end, next_onset)
        
        audio_slice = y[start:end]
        
        # gate 40db
        audio_slice, _ = librosa.effects.trim(audio_slice, top_db=40)
        
        # ignore micro clicks less than 50ms
        if len(audio_slice) < int(sr * 0.05):
            continue
            
        fade_in_len = min(int(sr * 0.002), len(audio_slice))
        if fade_in_len > 0:
            audio_slice[:fade_in_len] *= np.linspace(0.0, 1.0, fade_in_len)
            
        fade_out_len = min(int(sr * 0.1), len(audio_slice))
        if fade_out_len > 0:
            curve = np.exp(np.linspace(0, -5, fade_out_len))
            audio_slice[-fade_out_len:] *= curve
            
        mfcc = librosa.feature.mfcc(y=audio_slice, sr=sr, n_mfcc=13)
        centroid = librosa.feature.spectral_centroid(y=audio_slice, sr=sr)
        
        feat_vector = np.append(np.mean(mfcc.T, axis=0), np.mean(centroid))
        
        slices.append(audio_slice)
        features.append(feat_vector)

    if len(slices) < 3:
        return 0

    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)

    kmeans = KMeans(n_clusters=min(3, len(slices)), n_init=10)
    labels = kmeans.fit_predict(scaled_features)
    
    cluster_brightness = {}
    for i in range(3):
        cluster_indices = np.where(labels == i)[0]
        if len(cluster_indices) > 0:
            cluster_brightness[i] = np.mean([features[idx][-1] for idx in cluster_indices])
        else:
            cluster_brightness[i] = 0
            
    sorted_clusters = sorted(cluster_brightness.keys(), key=lambda k: cluster_brightness[k])
    
    hats_label = sorted_clusters[2]
    class_names = {sorted_clusters[0]: "kicks", sorted_clusters[1]: "snares & claps", sorted_clusters[2]: "hats"}
    
    clustered_samples = {0: [], 1: [], 2: []}
    
    for audio, label in zip(slices, labels):
        peak_amp = np.max(np.abs(audio))
        clustered_samples[label].append({"audio": audio, "peak": peak_amp})
        
    extracted_count = 0
    
    for label, items in clustered_samples.items():
        if not items:
            continue
            
        folder_name = class_names[label]
        target_dir = os.path.join(output_folder, folder_name)
        os.makedirs(target_dir, exist_ok=True)
        
        items.sort(key=lambda x: x["peak"], reverse=True)
        top_items = items[:10]
        
        for i, item in enumerate(top_items):
            audio = item["audio"]
            
            if label == hats_label:
                sos = scipy.signal.butter(4, 1000, btype='highpass', fs=sr, output='sos')
                audio = scipy.signal.sosfiltfilt(sos, audio)
            
            max_val = np.max(np.abs(audio))
            if max_val > 0:
                audio = audio / max_val * 0.9
                
            file_path = os.path.join(target_dir, f"{folder_name}_{i+1}.wav")
            sf.write(file_path, audio, sr)
            extracted_count += 1
        
    return extracted_count