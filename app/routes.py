from flask import Blueprint, render_template, redirect, url_for, request, jsonify
from flask_login import login_user, login_required, logout_user, current_user
from .models import User
from . import db

import os
import re
import asyncio
import platform
import time
import edge_tts
from pydub import AudioSegment

# ffmpeg setup
if platform.system() == "Windows":
    AudioSegment.converter = "ffmpeg"
else:
    AudioSegment.converter = "/usr/bin/ffmpeg"

main = Blueprint("main", __name__)

progress_data = {"percent": 0}


@main.route("/progress")
def progress():
    return jsonify(progress_data)


@main.route("/")
def home():
    return redirect(url_for("main.login"))


# ---------------- AUTH ----------------
@main.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if User.query.filter_by(email=email).first():
            return "User already exists"

        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        return redirect(url_for("main.login"))

    return render_template("signup.html")


@main.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("main.dashboard"))

        return "Invalid credentials"

    return render_template("login.html")


@main.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", email=current_user.email)


# -------- TIME --------
def srt_time_to_ms(time_str):
    h, m, s_ms = time_str.split(":")
    s, ms = s_ms.split(",")
    return (int(h)*3600 + int(m)*60 + int(s))*1000 + int(ms)


# -------- EDGE TTS --------
async def generate_voice(text, voice, path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)


# -------- GROUP SUBTITLES --------
def group_subtitles(matches, chunk_size=5):
    grouped = []
    chunk = []

    for m in matches:
        if m[2].strip():
            chunk.append(m)

        if len(chunk) == chunk_size:
            grouped.append(chunk)
            chunk = []

    if chunk:
        grouped.append(chunk)

    return grouped


# ---------------- MAIN FEATURE ----------------
@main.route("/subtitle-to-voice", methods=["GET", "POST"])
@login_required
def subtitle_to_voice():

    if request.method == "POST":

        progress_data["percent"] = 0

        file = request.files.get("subtitle_file")
        voice = request.form.get("voice")

        if not file:
            return "No subtitle file uploaded", 400

        content = file.read().decode("utf-8").replace("\r\n", "\n")

        pattern = re.compile(
            r"\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\d+\n|\Z)",
            re.DOTALL
        )

        matches = pattern.findall(content)

        grouped_matches = group_subtitles(matches, chunk_size=5)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        voices_dir = os.path.join(base_dir, "static", "voices")

        os.makedirs(voices_dir, exist_ok=True)

        output_path = os.path.join(voices_dir, "output.mp3")

        if os.path.exists(output_path):
            os.remove(output_path)

        final_audio = AudioSegment.silent(duration=0)
        extracted_text_list = []

        total = len(grouped_matches)
        processed = 0

        for i, group in enumerate(grouped_matches):

            combined_text = " ".join([g[2].replace("\n", " ") for g in group])
            start_ms = srt_time_to_ms(group[0][0])
            end_ms = srt_time_to_ms(group[-1][1])
            duration = end_ms - start_ms

            extracted_text_list.append(combined_text)

            temp_path = os.path.join(voices_dir, f"temp_{i}.mp3")

            success = False

            for attempt in range(3):
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(generate_voice(combined_text, voice, temp_path))
                    loop.close()

                    if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                        success = True
                        break

                except Exception as e:
                    print("Retry error:", e)
                    time.sleep(1)

            if not success:
                continue

            # ✅ FIX: avoid PermissionError
            # 🔥 ensure file exists and valid
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) < 1000:
                print("Invalid audio skipped:", combined_text)
                continue

            time.sleep(0.5)  # 🔥 wait for file write complete

            try:
                speech = AudioSegment.from_mp3(temp_path)
            except Exception as e:
                print("Decode error, skipping:", e)
                continue

            # 🔥 safe delete
            try:
                os.remove(temp_path)
            except:
                pass

            if len(final_audio) < start_ms:
                final_audio += AudioSegment.silent(start_ms - len(final_audio))

            if len(speech) > duration:
                speech = speech[:duration]
            else:
                speech += AudioSegment.silent(duration - len(speech))

            final_audio += speech

            processed += 1
            progress_data["percent"] = int((processed / total) * 100)

        progress_data["percent"] = 100

        if len(final_audio) < 1000:
            return "Audio generation failed ❌", 500

        final_audio.export(output_path, format="mp3")

        # ✅ FIX: retain selected voice
        return render_template(
            "subtitle.html",
            extracted_text=" ".join(extracted_text_list),
            audio_file="voices/output.mp3",
            selected_voice=voice
        )

    return render_template("subtitle.html")
    

# ---------------- LOGOUT ----------------
@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))