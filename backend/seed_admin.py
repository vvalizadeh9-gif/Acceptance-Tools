"""
BRIEF: run this exactly once, right after the database first starts.
Every other user gets created through the app (by an Admin, via the
/users route) — but the very first Admin has to be created directly,
since nobody exists yet to be allowed to create them.
"""

import sys
import uuid

from auth import hash_password
from database import SessionLocal, init_db
from models import User


def seed_admin(email: str, full_name: str, password: str):
    init_db()
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            print(f"User {email} already exists — nothing to do.")
            return
        admin = User(
            id=uuid.uuid4(),
            email=email,
            full_name=full_name,
            role="admin",
            hashed_password=hash_password(password),
        )
        db.add(admin)
        db.commit()
        print(f"Admin account created: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python seed_admin.py <email> <full_name> <password>")
        sys.exit(1)
    seed_admin(sys.argv[1], sys.argv[2], sys.argv[3])
