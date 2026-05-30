"""
pipeline.py - Prepared75 Daily Prepper YouTube Automation
Niche: Survival/Prepping | Channel: Prepared75
Runs via GitHub Actions daily at 9AM EST
Zero-cost stack: Groq (free) + gTTS (free) + ffmpeg (built-in)
"""

import os
import sys
import json
import time
import subprocess
import requests
from datetime import datetime
from gtts import gTTS
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── Config ───────────────────────────────────────────────────────────────────
CHANNEL_NAME      = "Prepared75"
NICHE             = "survival and prepping"
GROQ_API_KEY      = os.environ["GROQ_API_KEY"]
YT_CLIENT_ID      = os.environ["YOUTUBE_CLIENT_ID"]
YT_CLIENT_SECRET  = os.environ["YOUTUBE_CLIENT_SECRET"]
YT_REFRESH_TOKEN  = os.environ["YOUTUBE_REFRESH_TOKEN"]

PREPPER_TOPICS = [
    "72-hour bug-out bag essentials every family needs",
    "How to store a 1-year food supply on a $50/month budget",
    "Water purification methods that could save your life",
    "Off-grid power: solar vs generators vs hand-crank",
    "Home defense strategies for preppers",
    "Building a faraday cage to protect electronics from EMPs",
    "Best communication tools when cell networks go down",
    "Medicinal plants you can forage in most US states",
    "How to build a 3-month emergency food supply from scratch",
    "The 5 biggest prepping mistakes beginners make",
    "Urban survival: bugging out from a city in a crisis",
    "How to purify water in the wild with no gear",
    "Survival seeds: building a self-sustaining garden",
    "Ham radio basics every prepper should know",
    "Winter survival: staying warm when the power goes out",
    "Cash, gold, or barter? What to stockpile as currency",
    "Building a prepper community in your neighborhood",
    "First aid essentials every prepper must master",
    "Natural disaster prepping: hurricanes, tornadoes, earthquakes",
    "How to survive a grid-down scenario for 30+ days",
    "Prepping on a budget: maximum preparedness for minimum cost",
    "Essential tools every prepper should have in their garage",
    "How to make fire in any weather or condition",
    "Food preservation: canning, dehydrating, and freeze-drying",
    "Navigation without GPS: maps, compass, and celestial navigation",
    "Psychological prepping: mental resilience in a crisis",
    "Vehicle emergency kit: what to keep in your car",
    "Silent threats: radiation and biological prepping basics",
    "Chicken and livestock basics for backyard food independence",
    "How to choose and use a survival knife",
]

# ── Step 1: Generate Script via Groq ─────────────────────────────────────────

def pick_topic() -> str:
    today_index = datetime.utcnow().timetuple().tm_yday
    return PREPPER_TOPICS[today_index % len(PREPPER_TOPICS)]


def generate_script_and_metadata(topic: str) -> dict:
    prompt = f"""You are the scriptwriter for "{CHANNEL_NAME}", a popular YouTube channel about {NICHE}.

Today's video topic: "{topic}"

Produce a JSON object with EXACTLY these keys (no extra keys, no markdown fences):
{{
  "title": "YouTube video title (max 100 chars, click-worthy, SEO-rich)",
  "description": "YouTube description (150-300 words). Include the channel name Prepared75, what viewers will learn, and a call-to-action to like/subscribe. Add 10 relevant hashtags at the end.",
  "tags": ["tag1","tag2"],
  "script": "Full voiceover script 400-600 words. Conversational, authoritative, urgent tone. No stage directions. Start with a hook sentence. End with a subscribe call-to-action mentioning Prepared75."
}}

Return ONLY the raw JSON. No preamble, no markdown, no explanation."""

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama3-8b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
            "temperature": 0.7
        },
        timeout=60
    )
    resp.raise_for_status()

    raw = resp.json()["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("```").strip()

    data = json.loads(raw)
    print(f"✅ Script generated: {data['title']}")
    return data


# ── Step 2: Text-to-Speech ────────────────────────────────────────────────────

def text_to_speech(script: str, output_path: str = "voiceover.mp3") -> str:
    tts = gTTS(text=script, lang="en", slow=False)
    tts.save(output_path)
    print(f"✅ Voiceover saved: {output_path}")
    return output_path


# ── Step 3: Build Video via ffmpeg (free, built into Ubuntu runner) ───────────

def build_video(audio_path: str, title: str, output_path: str = "output.mp4") -> str:
    """Create a simple video: black background + white title text + audio."""
    safe_title = title.replace("'", "\\'").replace(":", "\\:")[:60]
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=black:size=1280x720:rate=24",
        "-i", audio_path,
        "-vf", (
            f"drawtext=text='{safe_title}':fontcolor=white:fontsize=48:"
            f"x=(w-text_w)/2:y=(h-text_h)/2,"
            f"drawtext=text='Prepared75':fontcolor=orange:fontsize=32:"
            f"x=(w-text_w)/2:y=h-80"
        ),
        "-shortest",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path
    ]
    print("🎬 Building video with ffmpeg...")
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"✅ Video built: {output_path}")
    return output_path


# ── Step 4: YouTube Upload ────────────────────────────────────────────────────

def get_youtube_service():
    creds = Credentials(
        token=None,
        refresh_token=YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(youtube, file_path: str, title: str, description: str, tags: list) -> str:
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": "26"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(file_path, chunksize=1024 * 1024, resumable=True)
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )

    print("📤 Uploading to YouTube...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   Uploaded {int(status.progress() * 100)}%")

    video_id = response.get("id")
    print(f"✅ Upload complete! https://www.youtube.com/watch?v={video_id}")
    return video_id


# ── Main Pipeline ─────────────────────────────────────────────────────────────

def main():
    print(f"\n🚀 Prepared75 Daily Pipeline — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")

    topic = pick_topic()
    print(f"📌 Today's topic: {topic}\n")

    meta        = generate_script_and_metadata(topic)
    title       = meta["title"]
    description = meta["description"]
    tags        = meta["tags"]
    script      = meta["script"]

    audio_path = text_to_speech(script, "voiceover.mp3")
    video_path = build_video(audio_path, title, "output.mp4")

    yt = get_youtube_service()
    video_id = upload_to_youtube(yt, video_path, title, description, tags)

    print(f"\n🎉 Done! https://www.youtube.com/watch?v={video_id}\n")
    return video_id


if __name__ == "__main__":
    main()
