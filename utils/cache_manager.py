import json
import os

CACHE_FILE = "cache.json"

def get_cache(file_uniq_id):
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r") as f:
        try:
            data = json.load(f)
            return data.get(file_uniq_id, {})
        except:
            return {}

def update_cache(file_uniq_id, new_data):
    data = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            try:
                data = json.load(f)
            except:
                pass
                
    if file_uniq_id not in data:
        data[file_uniq_id] = {}
        
    data[file_uniq_id].update(new_data)
    
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=4)