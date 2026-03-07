from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_user, login_required, logout_user, current_user
from .models import User
from . import db

import os
import re
from gtts import gTTS
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


# ----------- TIME CONVERT FUNCTION -----------
def srt_time_to_ms(time_str):
    h, m, s_ms = time_str.split(":")
    s, ms = s_ms.split(",")
    return (int(h)*3600 + int(m)*60 + int(s)) * 1000 + int(ms)


# ---------------- SUBTITLE TO VOICE ----------------
@main.route("/subtitle-to-voice", methods=["GET", "POST"])
@login_required
def subtitle_to_voice():

    if request.method == "POST":

        file = request.files.get("subtitle_file")
        voice = request.form.get("voice", "en")

        if not file:
            return "No subtitle file uploaded", 400

        content = file.read().decode("utf-8")

        pattern = re.compile(
            r"\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\d+\n|\Z)",
            re.DOTALL
        )

        matches = pattern.findall(content)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        voices_dir = os.path.join(base_dir, "static", "voices")

        if not os.path.exists(voices_dir):
            os.makedirs(voices_dir)

        output_path = os.path.join(voices_dir, "output.mp3")

        final_audio = AudioSegment.silent(duration=0)

        extracted_text_list = []

        for start, end, text in matches:

            clean_text = text.replace("\n", " ").strip()
            extracted_text_list.append(clean_text)

            start_ms = srt_time_to_ms(start)
            end_ms = srt_time_to_ms(end)

            subtitle_duration = end_ms - start_ms

            # Generate speech
            tts = gTTS(text=clean_text, lang=voice)

            temp_path = os.path.join(voices_dir, "temp.mp3")
            tts.save(temp_path)

            speech = AudioSegment.from_mp3(temp_path)

            # add silence until start
            if len(final_audio) < start_ms:
                silence = AudioSegment.silent(duration=start_ms - len(final_audio))
                final_audio += silence

            speech_duration = len(speech)

            # trim speech if longer than subtitle
            if speech_duration > subtitle_duration:
                speech = speech[:subtitle_duration]

            # add silence if speech shorter
            elif speech_duration < subtitle_duration:
                silence_needed = subtitle_duration - speech_duration
                speech += AudioSegment.silent(duration=silence_needed)

            final_audio += speech

        final_audio.export(output_path, format="mp3")

        return render_template(
            "subtitle.html",
            extracted_text=" ".join(extracted_text_list),
            audio_file="voices/output.mp3"
        )

    return render_template("subtitle.html")


# ---------------- LOGOUT ----------------
@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))