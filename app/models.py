from . import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin, db.Model):

    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(
        db.String(150),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(200),
        nullable=False
    )

    # Hash password before saving
    def set_password(self, password):
        self.password = generate_password_hash(password)

    # Verify password during login
    def check_password(self, password):
        return check_password_hash(self.password, password)