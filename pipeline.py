"""
pipeline.py - Prepared75 Daily Prepper YouTube Automation
Niche: Survival/Prepping | Channel: Prepared75
Runs via GitHub Actions daily at 9AM EST
"""

import os
import sys
import json
import time
import random
import pickle
import argparse
import requests
import textwrap
from datetime import datetime
from pathlib import Path

# ── Third-party ──────────────────────────────────────────────────────────────
import anthropic
from gtts import gTTS
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── Config ───────────────────────────────────────────────────────────────────
CHANNEL_NAME   = "Prepared75"
NICHE          = "survival and prepping"
ANTHROPIC_KEY  = os.environ["ANTHROPIC_API_KEY"]
SHOTSTACK_KEY  = os.environ.get("SHOTSTACK_API_KEY", "")

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

# ── Step 1: Generate Script via Claude ───────────────────────────────────────

def pick_topic() -> str:
    """Pick a pseudo-random topic based on today's date (consistent per day)."""
    today_index = datetime.utcnow().timetuple().tm_yday  # 1–365
    return PREPPER_TOPICS[today_index % len(PREPPER_TOPICS)]


def generate_script_and_metadata(topic: str) -> dict:
    """Call Claude to produce script + title + description + tags."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""
You are the scriptwriter for "{CHANNEL_NAME}", a popular YouTube channel about {NICHE}.

Today's video topic: "{topic}"

Produce a JSON object with EXACTLY these keys (no extra keys, no markdown fences):
{{
  "title": "YouTube video title (max 100 chars, click-worthy, SEO-rich)",
  "description": "YouTube description (150-300 words). Include the channel name Prepared75, what viewers will learn, and a call-to-action to like/subscribe. Add 10 relevant hashtags at the end.",
  "tags": ["tag1","tag2",...],   // 15 single/short-phrase tags
  "script": "Full voiceover script 400-600 words. Conversational, authoritative, urgent tone. No stage directions. Start with a hook sentence. End with a subscribe call-to-action mentioning Prepared75."
}}

Return ONLY the raw JSON. No preamble, no markdown, no explanation.
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    # Strip accidental markdown fences
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
    """Convert script to MP3 using gTTS."""
    tts = gTTS(text=script, lang="en", slow=False)
    tts.save(output_path)
    print(f"✅ Voiceover saved: {output_path}")
    return output_path


# ── Step 3: Build Video via Shotstack ────────────────────────────────────────

PREPPER_STOCK_CLIPS = [
    "https://cdn.coverr.co/videos/coverr-a-man-hiking-through-the-mountains-1647/1080p.mp4",
    "https://cdn.coverr.co/videos/coverr-aerial-view-of-forest-2373/1080p.mp4",
    "https://cdn.coverr.co/videos/coverr-campfire-in-the-forest-at-night-3577/1080p.mp4",
    "https://cdn.coverr.co/videos/coverr-man-looking-at-a-map-outdoor-5553/1080p.mp4",
    "https://cdn.coverr.co/videos/coverr-sun-shining-through-trees-4085/1080p.mp4",
    "https://cdn.coverr.co/videos/coverr-survival-supplies-and-tools-outdoor-9641/1080p.mp4",
    "https://cdn.coverr.co/videos/coverr-rain-in-the-forest-3583/1080p.mp4",
    "https://cdn.coverr.co/videos/coverr-person-chopping-wood-2428/1080p.mp4",
]


def build_video_shotstack(audio_url: str, title: str, duration_seconds: int = 90) -> str:
    """Submit a render job to Shotstack and return the rendered video URL."""
    if not SHOTSTACK_KEY:
        raise ValueError("SHOTSTACK_API_KEY secret not set.")

    clips = []
    clip_duration = duration_seconds / len(PREPPER_STOCK_CLIPS)

    for i, src in enumerate(PREPPER_STOCK_CLIPS):
        clips.append({
            "asset": {"type": "video", "src": src, "volume": 0},
            "start": i * clip_duration,
            "length": clip_duration,
            "fit": "cover",
            "transition": {"in": "fade", "out": "fade"}
        })

    # Title card overlay
    clips.append({
        "asset": {
            "type": "title",
            "text": title,
            "style": "future",
            "color": "#FFFFFF",
            "size": "x-large",
            "background": "rgba(0,0,0,0.55)",
            "position": "center"
        },
        "start": 0,
        "length": 4,
        "transition": {"in": "fade", "out": "fade"}
    })

    # Watermark / channel name
    clips.append({
        "asset": {
            "type": "text",
            "text": "Prepared75",
            "style": "minimal",
            "color": "#FF6600",
            "size": "small"
        },
        "start": 0,
        "length": duration_seconds,
        "position": "bottomRight",
        "offset": {"x": -0.05, "y": 0.05}
    })

    # Audio track
    soundtrack = {
        "src": audio_url,
        "effect": "fadeOut",
        "volume": 1
    }

    payload = {
        "timeline": {
            "tracks": [{"clips": clips}],
            "soundtrack": soundtrack
        },
        "output": {
            "format": "mp4",
            "resolution": "hd"
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": SHOTSTACK_KEY
    }

    print("🎬 Submitting render to Shotstack...")
    resp = requests.post(
        "https://api.shotstack.io/v1/render",
        json=payload,
        headers=headers,
        timeout=30
    )
    resp.raise_for_status()
    render_id = resp.json()["response"]["id"]
    print(f"   Render ID: {render_id}")

    # Poll until done (max 10 minutes)
    for attempt in range(120):
        time.sleep(5)
        poll = requests.get(
            f"https://api.shotstack.io/v1/render/{render_id}",
            headers=headers,
            timeout=15
        )
        poll.raise_for_status()
        status = poll.json()["response"]["status"]
        print(f"   [{attempt*5}s] Status: {status}")
        if status == "done":
            url = poll.json()["response"]["url"]
            print(f"✅ Video rendered: {url}")
            return url
        if status == "failed":
            raise RuntimeError("Shotstack render failed.")

    raise TimeoutError("Shotstack render timed out after 10 minutes.")


def download_video(url: str, path: str = "output.mp4") -> str:
    """Download rendered video to disk."""
    print(f"⬇️  Downloading video from {url}...")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"✅ Video downloaded: {path}")
    return path


# ── Step 4: YouTube Upload ────────────────────────────────────────────────────

def get_youtube_service():
    """Authenticate using OAuth2 refresh token flow (no browser needed)."""
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
    """Upload video and return YouTube video ID."""
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": "26"   # How-to & Style (closest to prepping)
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


# ── Optional: Upload audio to a public host for Shotstack ────────────────────

def upload_audio_to_tmpfiles(audio_path: str) -> str:
    """Upload MP3 to tmpfiles.org (free, no account) and return public URL."""
    print("☁️  Uploading voiceover to public host...")
    with open(audio_path, "rb") as f:
        resp = requests.post(
            "https://tmpfiles.org/api/v1/upload",
            files={"file": (audio_path, f, "audio/mpeg")},
            timeout=60
        )
    resp.raise_for_status()
    # tmpfiles returns: https://tmpfiles.org/XXXXX/voiceover.mp3
    url = resp.json()["data"]["url"].replace(
        "https://tmpfiles.org/", "https://tmpfiles.org/dl/"
    )
    print(f"✅ Audio URL: {url}")
    return url


# ── Main Pipeline ─────────────────────────────────────────────────────────────

def main():
    print(f"\n🚀 Prepared75 Daily Pipeline — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")

    # 1. Pick topic
    topic = pick_topic()
    print(f"📌 Today's topic: {topic}\n")

    # 2. Generate script + metadata
    meta = generate_script_and_metadata(topic)
    title       = meta["title"]
    description = meta["description"]
    tags        = meta["tags"]
    script      = meta["script"]

    # 3. Text-to-speech
    audio_path = text_to_speech(script, "voiceover.mp3")

    # 4. Build video
    if SHOTSTACK_KEY:
        audio_url  = upload_audio_to_tmpfiles(audio_path)
        video_url  = build_video_shotstack(audio_url, title, duration_seconds=90)
        video_path = download_video(video_url, "output.mp4")
    else:
        print("⚠️  No SHOTSTACK_API_KEY — skipping video render. Using placeholder.")
        # Fallback: just upload audio as-is for testing
        video_path = audio_path   # Will fail YT upload; for local testing only

    # 5. Upload to YouTube
    yt = get_youtube_service()
    video_id = upload_to_youtube(yt, video_path, title, description, tags)

    print(f"\n🎉 Done! Watch your video: https://www.youtube.com/watch?v={video_id}\n")
    return video_id


if __name__ == "__main__":
    main()
