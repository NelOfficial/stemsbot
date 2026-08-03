import os
import shutil
import asyncio
import time
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile

from config import DUMP_CHAT_ID
from utils.file_manager import download_file, cleanup_files
from utils.stats_manager import update_stats
from utils.cache_manager import get_cache, update_cache
from services.audio_analyzer import analyze_track_async, analyze_stems_async
from services.stem_splitter import split_audio_async
from services.one_shot_extractor import extract_one_shots

router = Router()

temp_tracks = {}

def get_action_keyboard(msg_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="scan (bpm/key)", callback_data=f"act_scan_{msg_id}")],
        [InlineKeyboardButton(text="stems & dsp", callback_data=f"act_stems_{msg_id}")],
        [InlineKeyboardButton(text="cut oneshots", callback_data=f"act_shots_{msg_id}")]
    ])

@router.message(F.audio | F.document)
async def process_audio_message(message: Message):
    file_obj = message.audio or message.document
    
    if message.document and not file_obj.mime_type.startswith('audio/'):
        await message.answer("send me mp3, wav, flac")
        return

    temp_tracks[message.message_id] = {
        "file_id": file_obj.file_id,
        "file_uniq_id": file_obj.file_unique_id,
        "file_name": file_obj.file_name or "track.mp3"
    }
    
    await message.answer("track received. choose action:", reply_markup=get_action_keyboard(message.message_id))

@router.callback_query(F.data.startswith("act_"))
async def handle_actions(callback: CallbackQuery):
    await callback.answer()
    
    parts = callback.data.split("_")
    if len(parts) < 3: return
    action = parts[1]
    msg_id = int(parts[2])
    
    track_data = temp_tracks.get(msg_id)
    if not track_data:
        return await callback.message.answer("session expired. upload track again.")
        
    file_id = track_data["file_id"]
    file_uniq_id = track_data["file_uniq_id"]
    file_name = track_data["file_name"].replace(" ", "_")
    
    cache = get_cache(file_uniq_id)
    
    # cache output
    if action == "scan" and "bpm" in cache:
        text = f"bpm: {cache['bpm']}\nkey: {cache['key']}\ndetune: {cache['detune']}\n\n(loaded from cache)"
        return await callback.message.edit_text(text)
        
    if action == "stems" and "stems_file_ids" in cache:
        await callback.message.delete()
        for fid in cache["stems_file_ids"]:
            await callback.message.answer_document(fid)
        if "bpm" in cache:
            await callback.message.answer(f"bpm: {cache['bpm']}\nkey: {cache['key']}\ndetune: {cache['detune']}\n\n(loaded from cache)")
        return
        
    if action == "shots" and "shots_file_id" in cache:
        await callback.message.delete()
        return await callback.message.answer_document(cache["shots_file_id"], caption="(loaded from cache)")

    # full process loop
    await callback.message.edit_text("downloading...")
    os.makedirs("temp", exist_ok=True)
    start_total_time = time.time()
    
    try:
        async def update_progress(text):
            try: await callback.message.edit_text(text)
            except: pass

        input_path = os.path.join("temp", f"raw_{msg_id}.{file_name.split('.')[-1]}")
        output_dir = os.path.join("temp", f"stems_{msg_id}")
        await download_file(callback.bot, file_id, input_path)

        if action == "scan":
            await update_progress("analyzing audio...")
            res = await analyze_track_async(input_path)
            if "error" in res: raise ValueError(res["error"])
            
            update_cache(file_uniq_id, {"bpm": res["bpm"], "key": res["key"], "detune": res["detune"]})
            total_time = round(time.time() - start_total_time, 1)
            text = f"bpm: {res['bpm']}\nkey: {res['key']} (parallel {res.get('relative_key', 'Unknown')})\ndetune: {res['detune']}\n\ntotal time: {total_time}s"
            await callback.message.edit_text(text)
            update_stats(is_fast=True)

        else:
            await update_progress("starting demucs...")
            await split_audio_async(input_path, output_dir=output_dir, progress_callback=update_progress)
            
            htdemucs_dir = os.path.join(output_dir, "htdemucs")
            if not os.path.exists(htdemucs_dir): raise ValueError("demucs error: output not found")
            folders = os.listdir(htdemucs_dir)
            if not folders: raise ValueError("demucs error: output is empty")
                
            track_folder = os.path.join(htdemucs_dir, folders[0])
            
            # flac + wav
            ext = "flac" if os.path.exists(os.path.join(track_folder, "drums.flac")) else "wav"
            drums = os.path.join(track_folder, f"drums.{ext}")
            bass = os.path.join(track_folder, f"bass.{ext}")
            other = os.path.join(track_folder, f"other.{ext}")
            vocals = os.path.join(track_folder, f"vocals.{ext}")
            
            await update_progress("analyzing stems dsp...")
            res = await analyze_stems_async(drums, bass, other)
            if "error" in res: raise ValueError(res["error"])

            # oneshots
            await update_progress("cutting oneshots...")
            shots_dir = os.path.join("temp", f"shots_{msg_id}")
            os.makedirs(shots_dir, exist_ok=True)
            await asyncio.to_thread(extract_one_shots, drums, shots_dir)
            zip_path = os.path.join("temp", f"oneshots_{msg_id}")
            shutil.make_archive(zip_path, 'zip', shots_dir)

            # file manage
            await callback.message.delete()
            stems_ids = []
            shots_id = None
            stem_files = [f for f in [drums, bass, other, vocals] if os.path.exists(f)]

            # output
            if action == "shots":
                sent_shots = await callback.message.answer_document(FSInputFile(f"{zip_path}.zip", filename="oneshots.zip"))
                shots_id = sent_shots.document.file_id
            elif action == "stems":
                for stem_path in stem_files:
                    sent_stem = await callback.message.answer_document(FSInputFile(stem_path))
                    stems_ids.append(sent_stem.document.file_id)
                
                total_time = round(time.time() - start_total_time, 1)
                await callback.message.answer(f"bpm: {res['bpm']}\nkey: {res['key']}\ndetune: {res['detune']}\n\ntotal time: {total_time}s")

            # backup to telegram channel (cache)
            if DUMP_CHAT_ID and DUMP_CHAT_ID != 0:
                try:
                    dump_msg = await callback.bot.copy_message(
                        chat_id=DUMP_CHAT_ID,
                        from_chat_id=callback.message.chat.id,
                        message_id=msg_id,
                        caption=f"bpm: {res['bpm']} | key: {res['key']}"
                    )
                    
                    if not shots_id:
                        dump_shots = await callback.bot.send_document(DUMP_CHAT_ID, FSInputFile(f"{zip_path}.zip", filename="oneshots.zip"), reply_to_message_id=dump_msg.message_id)
                        shots_id = dump_shots.document.file_id
                    else:
                        await callback.bot.send_document(DUMP_CHAT_ID, shots_id, reply_to_message_id=dump_msg.message_id)
                        
                    if not stems_ids:
                        for stem_path in stem_files:
                            dump_stem = await callback.bot.send_document(DUMP_CHAT_ID, FSInputFile(stem_path), reply_to_message_id=dump_msg.message_id)
                            stems_ids.append(dump_stem.document.file_id)
                    else:
                        for sid in stems_ids:
                            await callback.bot.send_document(DUMP_CHAT_ID, sid, reply_to_message_id=dump_msg.message_id)
                except Exception as e:
                    print(f"dump error: {e}")

            update_data = {"bpm": res["bpm"], "key": res["key"], "detune": res["detune"]}
            if shots_id: update_data["shots_file_id"] = shots_id
            if stems_ids: update_data["stems_file_ids"] = stems_ids
            update_cache(file_uniq_id, update_data)
            update_stats(is_fast=False)

    except Exception as e:
        await callback.message.edit_text(f"error:\n`{e}`")
    finally:
        if 'input_path' in locals() and 'output_dir' in locals():
            cleanup_files(input_path, output_dir)
        if 'shots_dir' in locals() and os.path.exists(shots_dir):
            shutil.rmtree(shots_dir)
        if 'zip_path' in locals() and os.path.exists(f"{zip_path}.zip"):
            os.remove(f"{zip_path}.zip")