import os, sys, time, subprocess
import assemblyai as aai
import yt_dlp

# --- ENVIRONMENT VARIABLES FROM GITHUB ACTIONS ---
ACTION = os.environ.get('ACTION', 'video_1080p')
YOUTUBE_URL = os.environ.get('YOUTUBE_URL')
ASSEMBLYAI_API_KEY = os.environ.get('ASSEMBLYAI_API_KEY')

if not YOUTUBE_URL:
    print("❌ ERROR: No YouTube URL provided.")
    sys.exit(1)

OUTPUT_BASE = "output_file"
YOUTUBE_COOKIES_PATH = "cookies_yt.txt"

# --- DETERMINE YT-DLP FORMAT BASED ON ACTION ---
if ACTION == 'video_1080p':
    format_str = 'bestvideo[height<=1080][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best'
    ext = 'mp4'
elif ACTION == 'video_720p':
    format_str = 'bestvideo[height<=720][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best'
    ext = 'mp4'
elif ACTION == 'video_480p':
    format_str = 'bestvideo[height<=480][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best'
    ext = 'mp4'
elif ACTION in ['audio', 'audio_transcript']:
    format_str = 'bestaudio[ext=m4a]/bestaudio/best'
    ext = 'm4a'
else:
    print(f"❌ ERROR: Unknown action '{ACTION}'")
    sys.exit(1)

local_source = f"{OUTPUT_BASE}.{ext}"

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
        
        ydl_opts = {
            'format': format_str,
            'merge_output_format': 'mp4' if 'video' in ACTION else None,
            'outtmpl': local_source,
            'extractor_args': {'youtube': [f"player_client={cfg['client']}", "player_skip=web,web_embedded"]},
            'quiet': False, 'no_warnings': True,
        }
        
        # Only use postprocessors for video to ensure it's mp4
        if 'video' in ACTION:
            ydl_opts['postprocessors'] = [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}]
        else:
            # For audio, extract to mp3 cleanly
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
            local_source = f"{OUTPUT_BASE}.mp3" # Update expected filename

        if cfg['proxy']: 
            ydl_opts['proxy'] = cfg['proxy']
        if cfg['use_cookies'] and os.path.exists(YOUTUBE_COOKIES_PATH): 
            ydl_opts['cookiefile'] = YOUTUBE_COOKIES_PATH

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: 
                ydl.download([YOUTUBE_URL])
            if os.path.exists(local_source) and os.path.getsize(local_source) > 50000: # Ensure it's not a tiny error file
                print(f"✅ YT-DLP Download Success!")
                download_success = True
                break
        except Exception as e:
            print(f"⚠️ Failed: {e}")
            os.system(f"rm -rf {local_source}*")
            
    if download_success: break

if not download_success: 
    print("❌ Download failed completely after all proxy attempts.")
    sys.exit(1)

# --- ASSEMBLYAI TRANSCRIPTION LOGIC ---
if ACTION == 'audio_transcript':
    if not ASSEMBLYAI_API_KEY:
        print("❌ ERROR: ASSEMBLYAI_API_KEY is missing. Add it to your repository secrets.")
        sys.exit(1)

    print("\n📝 Transcribing audio with AssemblyAI... (Waiting on AssemblyAI servers to analyze speech)")
    aai.settings.api_key = ASSEMBLYAI_API_KEY
    
    # Using English ("en") as requested, with the exact same config approach
    config = aai.TranscriptionConfig(speech_models=["universal-2"], language_code="en", speaker_labels=True)
    transcript = aai.Transcriber(config=config).transcribe(local_source)
    
    if transcript.status == aai.TranscriptStatus.error:
        print(f"❌ Transcription failed: {transcript.error}")
        sys.exit(1)

    transcript_text = ""
    for u in transcript.utterances:
        # Original format: [Start: X ms, End: Y ms] Speaker A: Text
        transcript_text += f"[Start: {u.start} ms, End: {u.end} ms] Speaker {u.speaker}: {u.text}\n"
    
    with open("transcript.txt", "w", encoding="utf-8") as f:
        f.write(transcript_text)
        
    print("✅ AssemblyAI Transcription complete. Saved to transcript.txt")

print("\n✨ ALL DONE. WORKFLOW COMPLETE.")
