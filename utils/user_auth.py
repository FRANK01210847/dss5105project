import json, os, hashlib

USER_DB_PATH = os.path.join("db", "users.json")

def _init_user_db():
    os.makedirs("db", exist_ok=True)
    if not os.path.exists(USER_DB_PATH) or os.path.getsize(USER_DB_PATH)==0:
        with open(USER_DB_PATH, "w", encoding="utf-8") as f:
            json.dump({"landlords": {}, "tenants": {}}, f, indent=4, ensure_ascii=False)

def _hash_password(p: str) -> str:
    return hashlib.sha256(p.encode("utf-8")).hexdigest()

def register_user(username: str, password: str, role: str, email: str=""):
    _init_user_db()
    with open(USER_DB_PATH, "r", encoding="utf-8") as f: users = json.load(f)
    if role not in users: return False, "Invalid user role."
    # Check if username exists in either tenants or landlords
    if username in users["tenants"] or username in users["landlords"]:
        return False, f"Username {username} already exists."
    users[role][username] = {"password": _hash_password(password), "email": email}
    with open(USER_DB_PATH, "w", encoding="utf-8") as f: json.dump(users, f, indent=4, ensure_ascii=False)
    return True, f"Registration successful, welcome {username}!"

def authenticate_user(username: str, password: str, role: str):
    _init_user_db()
    with open(USER_DB_PATH, "r", encoding="utf-8") as f: users = json.load(f)
    if role not in users: return False, "Invalid user role."
    if username not in users[role]: return False, "User does not exist."
    if users[role][username]["password"] != _hash_password(password): return False, "Incorrect password."
    return True, "Login successful!"
