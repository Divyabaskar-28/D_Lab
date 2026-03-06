from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_user, login_required, logout_user, current_user
from .models import User
from . import db

import subprocess
import os
import re
from pydub import AudioSegment

main = Blueprint("main", __name__)


@main.route("/")
def home():
    return redirect(url_for("main.login"))


# ---------------- SIGNUP ----------------
@main.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            return "User already exists"

        new_user = User(email=email)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for("main.login"))

    return render_template("signup.html")


# ---------------- LOGIN ----------------
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


# ---------------- DASHBOARD ----------------
@main.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", email=current_user.email)


# ---------------- SUBTITLE TO VOICE ----------------
@main.route("/subtitle-to-voice", methods=["GET", "POST"])
@login_required
def subtitle_to_voice():

    if request.method == "POST":

        file = request.files.get("subtitle_file")
        voice = request.form.get("voice")

        if not voice:
            voice = "en_US-joe-medium"

        if file:

            content = file.read().decode("utf-8")

            pattern = re.compile(
                r"\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\d+\n|\Z)",
                re.DOTALL
            )

            matches = pattern.findall(content)

            final_audio = AudioSegment.silent(duration=0)

            def time_to_ms(timestamp):
                h, m, s = timestamp.split(":")
                sec, ms = s.split(",")

                return (
                    int(h) * 3600000 +
                    int(m) * 60000 +
                    int(sec) * 1000 +
                    int(ms)
                )

            extracted_full_text = []

            for start, end, text in matches:

                text = text.replace("\n", " ").strip()
                extracted_full_text.append(text)

                start_ms = time_to_ms(start)
                end_ms = time_to_ms(end)

                subtitle_duration = end_ms - start_ms

                # ---------- PIPER TTS ----------
                voice_model = os.path.join(
                "app", "static", "voices", f"{voice}.onnx"
            )
                temp_file = os.path.join("app", "static", "temp.wav")

                cmd = [
                    "piper",
                    "--model",
                    voice_model,
                    "--output_file",
                    temp_file
                ]

                result = subprocess.run(
                    cmd,
                    input=text.encode("utf-8"),
                    capture_output=True
                )

                if result.returncode != 0:
                    print("Piper Error:", result.stderr.decode())
                    return "Piper failed to generate audio"

                if not os.path.exists(temp_file):
                    return "Audio file not created"

                audio_segment = AudioSegment.from_file(temp_file, format="wav")

                os.remove(temp_file)

                # Adjust subtitle timing
                if len(audio_segment) > subtitle_duration:
                    audio_segment = audio_segment[:subtitle_duration]

                elif len(audio_segment) < subtitle_duration:
                    silence_needed = subtitle_duration - len(audio_segment)
                    audio_segment += AudioSegment.silent(duration=silence_needed)

                if start_ms > len(final_audio):
                    silence = AudioSegment.silent(duration=start_ms - len(final_audio))
                    final_audio += silence

                final_audio += audio_segment

            output_path = os.path.join("app", "static", "output.wav")
            final_audio.export(output_path, format="wav")

            return render_template(
                "subtitle.html",
                extracted_text=" ".join(extracted_full_text),
                audio_file="output.wav"
            )

    return render_template("subtitle.html")


# ---------------- LOGOUT ----------------
@main.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(url_for("main.login"))