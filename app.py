import os, sys, time, subprocess
import assemblyai as aai
import yt_dlp

# --- ENVIRONMENT VARIABLES FROM GITHUB ACTIONS ---
ACTION = os.environ.get('ACTION', 'video_1080p')
YOUTUBE_URL = os.environ.get('YOUTUBE_URL')
ASSEMBLYAI_API_KEY = os.environ.get('ASSEMBLYAI_API_KEY')
LANGUAGE_CODE = os.environ.get('LANGUAGE_CODE', 'en')

if not YOUTUBE_URL:
    print("❌ ERROR: No YouTube URL provided.")
    sys.exit(1)

OUTPUT_BASE = "output_file"
YOUTUBE_COOKIES_PATH = "cookies_yt.txt"

# Map out the final exact expected target file based on the selected action
if 'video' in ACTION:
    final_target = f"{OUTPUT_BASE}.mp4"
else:
    final_target = f"{OUTPUT_BASE}.mp3"

# Wipe any corrupt or leftover files from prior runs before starting a clean loop
for file_to_clear in [f"{OUTPUT_BASE}.mp4", f"{OUTPUT_BASE}.mp3", f"{OUTPUT_BASE}.m4a", f"{OUTPUT_BASE}.webm", "transcript.txt"]:
    if os.path.exists(file_to_clear): 
        os.remove(file_to_clear)

# --- EXACT ORIGINAL PROXY & CLIENT CONFIGS ---
configs = [
    {'client': 'tv', 'proxy': None, 'use_cookies': False},
    {'client': 'android', 'proxy': None, 'use_cookies': False},
    {'client': 'ios', 'proxy': None, 'use_cookies': False},
    {'client': 'tv', 'proxy': 'socks5://127.0.0.1:40000', 'use_cookies': False},
    {'client': 'android', 'proxy': 'socks5://127.0.0.1:40000', 'use_cookies': False},
    {'client': 'tv', 'proxy': None, 'use_cookies': True},
    {'client': 'tv', 'proxy': 'socks5://127.0.0.1:40000', 'use_cookies': True}
]

# --- DOWNLOAD LOGIC WITH WARP CYCLING ---
download_success = False
MAX_ATTEMPTS = 10

for attempt in range(1, MAX_ATTEMPTS + 1):
    if attempt > 1:
        print("\n🔄 Cycling Cloudflare WARP...")
        subprocess.run("warp-cli --accept-tos disconnect", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        subprocess.run("warp-cli --accept-tos connect", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)
        
    print(f"\n🚀 --- YT-DLP DOWNLOAD ATTEMPT {attempt}/{MAX_ATTEMPTS} ---")

    for cfg in configs:
        network = "WARP Proxy" if cfg['proxy'] else "GitHub Native IP"
        print(f"🎥 Trying client: {cfg['client']} | Network: {network} | Cookies: {cfg['use_cookies']}")
        
        # --- ISOLATED PLATFORM ROUTING ---
        is_facebook = "facebook.com" in YOUTUBE_URL.lower() or "fb.watch" in YOUTUBE_URL.lower()

        if is_facebook and 'video' in ACTION:
            print("📘 Detected Facebook URL: Removing format limits to force maximum resolution...")
            format_str = 'bestvideo+bestaudio/best'
        else:
            # Using 'res' instead of 'height' properly evaluates both horizontal (1920x1080) and vertical (1080x1920) streams.
            if ACTION == 'video_1080p':
                format_str = 'bestvideo[res<=1080][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[res<=1080]+bestaudio/best'
            elif ACTION == 'video_720p':
                format_str = 'bestvideo[res<=720][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[res<=720]+bestaudio/best'
            elif ACTION == 'video_480p':
                format_str = 'bestvideo[res<=480][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[res<=480]+bestaudio/best'
            else:
                format_str = 'bestaudio/best'

        ydl_opts = {
            'format': format_str,
            'outtmpl': f"{OUTPUT_BASE}.%(ext)s", # ALWAYS download using native extensions to prevent container conflicts
            'extractor_args': {'youtube': [f"player_client={cfg['client']}", "player_skip=web,web_embedded"]},
            'quiet': False, 
            'no_warnings': True,
            'noplaylist': True,
        }
        
        if 'video' in ACTION:
            ydl_opts['merge_output_format'] = 'mp4'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}]
        else:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        if cfg['proxy']: 
            ydl_opts['proxy'] = cfg['proxy']
        if cfg['use_cookies'] and os.path.exists(YOUTUBE_COOKIES_PATH): 
            ydl_opts['cookiefile'] = YOUTUBE_COOKIES_PATH

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: 
                ydl.download([YOUTUBE_URL])
        except Exception as e:
            print(f"   ⚠️ Note: yt-dlp reported a terminal warning or minor block: {e}")
            
        # --- EXPLICIT SUCCESS TARGET CHECK ---
        if os.path.exists(final_target) and os.path.getsize(final_target) > 50000:
            print(f"✅ YT-DLP Download Success! Secured file: {final_target}")
            download_success = True
            break
        else:
            print("   ❌ Final expected file target was not found. Cleaning up cache for next block jump...")
            for file_to_clear in [f"{OUTPUT_BASE}.mp4", f"{OUTPUT_BASE}.mp3", f"{OUTPUT_BASE}.m4a", f"{OUTPUT_BASE}.webm"]:
                if os.path.exists(file_to_clear): 
                    os.remove(file_to_clear)
            
    if download_success: break

if not download_success: 
    print("❌ Download failed completely after all proxy attempts.")
    sys.exit(1)

# --- ASSEMBLYAI TRANSCRIPTION LOGIC ---
if ACTION == 'audio_transcript':
    if not ASSEMBLYAI_API_KEY:
        print("❌ ERROR: ASSEMBLYAI_API_KEY is missing. Add it to your repository secrets.")
        sys.exit(1)

    print(f"\n📝 Transcribing audio with AssemblyAI... (Language Code: {LANGUAGE_CODE})")
    aai.settings.api_key = ASSEMBLYAI_API_KEY
    
    config = aai.TranscriptionConfig(speech_models=["universal-2"], language_code=LANGUAGE_CODE, speaker_labels=True)
    transcript = aai.Transcriber(config=config).transcribe(final_target)
    
    if transcript.status == aai.TranscriptStatus.error:
        print(f"❌ Transcription failed: {transcript.error}")
        sys.exit(1)

    transcript_text = ""
    for u in transcript.utterances:
        transcript_text += f"[Start: {u.start} ms, End: {u.end} ms] Speaker {u.speaker}: {u.text}\n"
    
    with open("transcript.txt", "w", encoding="utf-8") as f:
        f.write(transcript_text)
        
    print("✅ AssemblyAI Transcription complete. Saved to transcript.txt")

print("\n✨ ALL DONE. WORKFLOW COMPLETE.")
