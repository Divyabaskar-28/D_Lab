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
cancel_flag = {"stop": False}


# ---------------- PROGRESS ----------------
@main.route("/progress")
def progress():
    return jsonify(progress_data)


# ---------------- CANCEL ----------------
@main.route("/cancel", methods=["POST"])
def cancel():
    cancel_flag["stop"] = True
    return jsonify({"status": "cancelled"})


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


# -------- GROUP --------
def group_subtitles(matches, chunk_size=1):
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

        try:
            progress_data["percent"] = 0
            cancel_flag["stop"] = False

            file = request.files.get("subtitle_file")
            voice = request.form.get("voice")

            if not file:
                return jsonify({"error": "No file uploaded"}), 400

            content = file.read().decode("utf-8").replace("\r\n", "\n")

            pattern = re.compile(
                r"\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\d+\n|\Z)",
                re.DOTALL
            )

            matches = pattern.findall(content)

            if not matches:
                return jsonify({"error": "Invalid SRT file"}), 400

            base_dir = os.path.dirname(os.path.abspath(__file__))
            voices_dir = os.path.join(base_dir, "static", "voices")
            os.makedirs(voices_dir, exist_ok=True)

            output_path = os.path.join(voices_dir, "output.mp3")

            if os.path.exists(output_path):
                os.remove(output_path)

            final_audio = AudioSegment.silent(duration=0)
            extracted_text = []

            total = len(matches)

            for i, m in enumerate(matches):

                if cancel_flag["stop"]:
                    progress_data["percent"] = 0
                    return jsonify({"status": "cancelled"})

                text = m[2].replace("\n", " ").strip()
                text = re.sub(r"[^\w\s.,!?'-]", "", text)

                if not text:
                    continue

                extracted_text.append(text)

                start_ms = srt_time_to_ms(m[0])
                end_ms = srt_time_to_ms(m[1])
                duration = end_ms - start_ms

                temp_path = os.path.join(voices_dir, f"temp_{i}.mp3")

                success = False

                for attempt in range(3):
                    try:
                        asyncio.run(generate_voice(text, voice, temp_path))

                        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                            success = True
                            break

                    except Exception as e:
                        print("Retry:", e)
                        time.sleep(0.5)

                if not success:
                    print(f"Skipping chunk {i}")
                    continue

                speech = AudioSegment.from_mp3(temp_path)
                os.remove(temp_path)

                if len(final_audio) < start_ms:
                    final_audio += AudioSegment.silent(start_ms - len(final_audio))

                if len(speech) > duration:
                    speech = speech[:duration]
                else:
                    speech += AudioSegment.silent(duration - len(speech))

                final_audio += speech

                progress_data["percent"] = int(((i + 1) / total) * 100)

            progress_data["percent"] = 100

            if len(final_audio) < 500:
                return jsonify({"error": "Final audio too small"}), 500

            final_audio.export(output_path, format="mp3")

            return jsonify({
                "text": " ".join(extracted_text),
                "audio": "voices/output.mp3",
                "voice": voice
            })

        except Exception as e:
            print("🔥 FULL ERROR:", str(e))
            return jsonify({"error": str(e)}), 500

    return render_template("subtitle.html")


# ---------------- LOGOUT ----------------
@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))