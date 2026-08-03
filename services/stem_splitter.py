import asyncio
import os
import re


async def split_audio_async(file_path: str, output_dir: str = "stems", progress_callback=None) -> str:
    filename = os.path.basename(file_path).split('.')[0]

    cmd = [
        "python", "-m", "demucs",
        "-n", "htdemucs",
        "-d", "cuda",
        "--flac",
        "-o", output_dir,
        file_path
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    error_log = []

    if progress_callback:
        while True:
            line = await process.stderr.readline()
            if not line:
                break

            line_str = line.decode('utf-8', errors='ignore').strip()

            if line_str:
                error_log.append(line_str)
                if len(error_log) > 5:
                    error_log.pop(0)

            match = re.search(r'(\d{1,3})%', line_str)

            if match:
                percent = int(match.group(1))
                await progress_callback(percent)

    await process.wait()

    # 0 == success
    if process.returncode != 0:
        actual_error = "\n".join(error_log) if error_log else "unknown error"
        raise RuntimeError(f"Demucs error\nLog:\n{actual_error}")

    return os.path.join(output_dir, "htdemucs", filename)