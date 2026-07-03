"""
Seed the province reference table (and the Regional Manager / PSO Coordinator
accounts) from the authoritative mapping supplied by the project owner.

Run once after migrating:

    python seed_provinces.py

It is idempotent — re-running updates the CRA region / owner links on existing
provinces and never duplicates accounts. Newly-created RM/Coordinator accounts
get a random one-time password, printed once; the Admin should have each person
reset it (and correct their placeholder e-mail) on first sign-in.

The province primary key is the SAME deterministic UUID the CPM importer
derives from the province name, so existing Site rows link to these provinces
with no importer change.
"""

import secrets
import sys
import uuid

from auth import hash_password
from database import SessionLocal, init_db
from enums import UserRole
from models import Province, User

# --- Same derivation the CPM importer uses (import_cpm._province_uuid) ---
def _province_uuid(label: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"province::{label}")


# province (exact CPM spelling) | Regional Manager | PSO Coordinator | CRA Region
PROVINCE_MAP = [
    ("خوزستان",            "Loveimi",      "Zohreh",  "South West"),
    ("اردبیل",             "Pirayesh",     "Hossein", "Azar"),
    ("آذربایجان شرقی",     "Pirayesh",     "Hossein", "Azar"),
    ("آذربایجان غربی",     "Pirayesh",     "Hossein", "Azar"),
    ("خراسان جنوبی",       "Bahramizadeh", "Zohreh",  "North East"),
    ("بوشهر",              "Torabi",       "Zohreh",  "South"),
    ("البرز",              "Allahyar",     "Amir",    "North"),
    ("خراسان شمالی",       "Bahramizadeh", "Zohreh",  "North East"),
    ("گیلان",              "Fazl Talab",   "Amir",    "North West"),
    ("کهگیلویه و بویراحمد", "Torabi",       "Zohreh",  "South"),
    ("سیستان و بلوچستان",  "Bastegani",    "Farid",   "South East"),
    ("چهارمحال و بختیاری", "Rojhan",       "Hossein", "Central"),
    ("کرمان",              "Bastegani",    "Farid",   "South East"),
    ("هرمزگان",            "Bastegani",    "Farid",   "South East"),
    ("فارس",               "Torabi",       "Zohreh",  "South"),
    ("زنجان",              "Pirayesh",     "Amir",    "North West"),
    ("اصفهان",             "Rojhan",       "Hossein", "Central"),
    ("یزد",                "Rojhan",       "Hossein", "Central"),
    ("کردستان",            "Rouhi",        "Hossein", "West"),
    ("لرستان",             "Rouhi",        "Zohreh",  "South West"),
    ("سمنان",              "Allahyar",     "Amir",    "North"),
    ("کرمانشاه",           "Rouhi",        "Hossein", "West"),
    ("تهران",              "Allahyar",     "Amir",    "North"),
    ("همدان",              "Rouhi",        "Hossein", "West"),
    ("قزوین",              "Rouhi",        "Amir",    "North West"),
    ("ایلام",              "Rouhi",        "Zohreh",  "South West"),
    ("مازندران",           "Nobakht",      "Amir",    "North"),
    ("خراسان رضوی",        "Bahramizadeh", "Zohreh",  "North East"),
    ("قم",                 "Allahyar",     "Hossein", "Central"),
    ("مرکزی",              "Rouhi",        "Hossein", "Central"),
    ("گلستان",             "Nobakht",      "Zohreh",  "North East"),
]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "")


def _get_or_create_user(db, full_name: str, role: UserRole, prefix: str, created_log: list) -> User:
    email = f"{prefix}-{_slug(full_name)}@uso.ir"
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    temp_password = secrets.token_urlsafe(9)
    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name=full_name,
        role=role.value,
        hashed_password=hash_password(temp_password),
    )
    db.add(user)
    db.flush()  # assign id for province FK
    created_log.append((full_name, role.value, email, temp_password))
    return user


def seed_provinces():
    init_db()
    db = SessionLocal()
    created_users: list = []
    provinces_created = provinces_updated = 0
    try:
        # Resolve/creating the distinct RM and Coordinator accounts first.
        rm_by_name: dict = {}
        coord_by_name: dict = {}
        for _name, rm, coord, _cra in PROVINCE_MAP:
            if rm not in rm_by_name:
                rm_by_name[rm] = _get_or_create_user(db, rm, UserRole.REGIONAL_MANAGER, "rm", created_users)
            if coord not in coord_by_name:
                coord_by_name[coord] = _get_or_create_user(db, coord, UserRole.DT_COORDINATOR, "coord", created_users)

        for name, rm, coord, cra in PROVINCE_MAP:
            pid = _province_uuid(name)
            prov = db.get(Province, pid)
            if prov is None:
                prov = Province(id=pid, name=name)
                db.add(prov)
                provinces_created += 1
            else:
                provinces_updated += 1
            prov.cra_region = cra
            prov.regional_manager_id = rm_by_name[rm].id
            prov.pso_coordinator_id = coord_by_name[coord].id

        db.commit()
    finally:
        db.close()

    print(f"Provinces: {provinces_created} created, {provinces_updated} updated "
          f"({len(PROVINCE_MAP)} total).")
    if created_users:
        print(f"\nCreated {len(created_users)} account(s) — TEMPORARY passwords, "
              f"shown once. Have each person reset their password and correct "
              f"their e-mail after first sign-in:\n")
        for full_name, role, email, pw in created_users:
            print(f"  {role:18s} {full_name:14s} {email:32s} {pw}")
    else:
        print("No new accounts (RM/Coordinator accounts already existed).")


if __name__ == "__main__":
    if len(sys.argv) != 1:
        print("Usage: python seed_provinces.py")
        sys.exit(1)
    seed_provinces()
