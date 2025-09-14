import json
import hashlib
import os

DB_FILE = 'password_db.json'

def load_database():
    """
    加载数据库。确保返回的结构包含 'archives', 'archives_by_name', 和 'passwords' 三个键。
    """
    if not os.path.exists(DB_FILE):
        return {'archives': {}, 'archives_by_name': {}, 'passwords': []}
    
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 兼容旧的数据库，确保新键存在
            if 'archives' not in data:
                data['archives'] = {}
            if 'archives_by_name' not in data:
                data['archives_by_name'] = {}
            if 'passwords' not in data:
                data['passwords'] = []
            return data
    except (json.JSONDecodeError, IOError):
        return {'archives': {}, 'archives_by_name': {}, 'passwords': []}

def save_database(data):
    """将整个数据库保存回 JSON 文件。"""
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def calculate_file_hash(archive_path):
    """计算文件的 SHA-256 哈希值。"""
    sha256 = hashlib.sha256()
    try:
        with open(archive_path, 'rb') as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256.update(byte_block)
            return sha256.hexdigest()
    except IOError as e:
        print(f"无法读取文件进行哈希计算 {archive_path}: {e}")
        return None

# --- 压缩包密码记忆相关 (哈希) ---
def get_password_for_archive(db, archive_hash):
    """根据哈希值从数据库中查找密码。"""
    return db.get('archives', {}).get(archive_hash)

def save_password_for_archive(db, archive_hash, password):
    """将新的 哈希->密码 对保存到数据库中。"""
    if 'archives' not in db:
        db['archives'] = {}
    db['archives'][archive_hash] = password
    save_database(db)

# --- 压缩包密码记忆相关 (文件名) ---
def get_password_for_archive_by_name(db, filename):
    """根据文件名从数据库中查找密码。"""
    return db.get('archives_by_name', {}).get(filename)

def save_password_for_archive_by_name(db, filename, password):
    """将新的 文件名->密码 对保存到数据库中。"""
    if 'archives_by_name' not in db:
        db['archives_by_name'] = {}
    db['archives_by_name'][filename] = password
    save_database(db)

# --- 密码本相关 ---
def get_password_book(db):
    """获取密码本列表。"""
    return db.get('passwords', [])

def add_password_to_book(db, password):
    """向密码本添加一个新密码，如果它不存在的话。"""
    if 'passwords' not in db:
        db['passwords'] = []
    if password and password not in db['passwords']:
        db['passwords'].append(password)
        save_database(db)
        return True
    return False

def remove_password_from_book(db, password):
    """从密码本中移除一个密码。"""
    if 'passwords' in db and password in db['passwords']:
        db['passwords'].remove(password)
        save_database(db)
        return True
    return False