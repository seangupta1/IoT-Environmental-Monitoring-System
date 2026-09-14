from schemas.user import User
from db import db
from typing import List, Tuple, Literal
from datetime import datetime
from sqlalchemy import cast, Float
from flask_bcrypt import Bcrypt

def create(username: str, password:str, role: Literal["User", "Admin"], bcrypt: Bcrypt):
    if not User.query.filter_by(username=username).first():
        try:
            hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
            new_user = User(username=username, password_hash=hashed_pw, role=role)
            db.session.add(new_user)
            db.session.commit()
            return new_user
        except Exception as e:
            db.session.rollback()
            print("Error:", e)
            
def read(username: str, password:str, bcrypt: Bcrypt):
    # grab user from the database with that username
    # If no user has that username, this will be None
    user = User.query.filter_by(username=username).first()

    # If user exists, see if their typed password matches the database hash
    # login and send them to the dashboard/index
    if user and bcrypt.check_password_hash(user.password_hash, password):
        return user