import json
import os

STATS_FILE = "stats.json"

def update_stats(is_fast=False):
    stats = {"total_processed": 0, "fast_modes": 0, "full_stems": 0}
    
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            try:
                stats = json.load(f)
            except json.JSONDecodeError:
                pass
    
    stats["total_processed"] += 1
    if is_fast:
        stats["fast_modes"] += 1
    else:
        stats["full_stems"] += 1
        
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)

def get_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return None
    return None