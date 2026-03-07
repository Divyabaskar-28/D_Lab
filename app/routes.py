from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_user, login_required, logout_user, current_user
from .models import User
from . import db

import os
import re
from gtts import gTTS  # Free TTS
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
        voice = request.form.get("voice", "en")  # default gTTS voice

        if not file:
            return "No subtitle file uploaded", 400

        # Read SRT content
        content = file.read().decode("utf-8")

        # Extract text ignoring timestamps and numbers
        pattern = re.compile(
            r"\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\d+\n|\Z)",
            re.DOTALL
        )
        matches = pattern.findall(content)

        extracted_full_text = []
        full_text_for_tts = ""

        for _, _, text in matches:
            clean_text = text.replace("\n", " ").strip()
            extracted_full_text.append(clean_text)
            full_text_for_tts += clean_text + " "

        if not full_text_for_tts.strip():
            return "No text found in subtitle", 400

        # Generate audio using gTTS
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(base_dir, "static", "voices", "output.mp3")

        tts = gTTS(text=full_text_for_tts, lang="en")
        tts.save(output_path)

        return render_template(
            "subtitle.html",
            extracted_text=" ".join(extracted_full_text),
            audio_file="voices/output.mp3"
        )

    return render_template("subtitle.html")


# ---------------- LOGOUT ----------------
@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))