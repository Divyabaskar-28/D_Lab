from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os

# Database
db = SQLAlchemy()

# Login manager
login_manager = LoginManager()
login_manager.login_view = "main.login"


def create_app():

    app = Flask(__name__)

    # App configuration
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "supersecretkey")

    # Database configuration
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        "sqlite:///d_lab.db"
    )

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Import models
    from .models import User

    # Load user for login session
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register routes
    from .routes import main
    app.register_blueprint(main)

    # Create database tables automatically
    with app.app_context():
        db.create_all()

    return app