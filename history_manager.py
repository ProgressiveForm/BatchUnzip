import json
import os

HISTORY_FILE = 'history_db.json'

def load_history():
    """
    加载历史记录数据库。
    """
    if not os.path.exists(HISTORY_FILE):
        return {'archives': [], 'passwords': []}
    
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'archives' not in data:
                data['archives'] = []
            if 'passwords' not in data:
                data['passwords'] = []
            return data
    except (json.JSONDecodeError, IOError):
        return {'archives': [], 'passwords': []}

def save_history(data):
    """将历史记录保存回 JSON 文件。"""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def add_archive_to_history(db, archive_path):
    """向历史记录中添加一个新的压缩包路径（如果不存在）。"""
    if 'archives' not in db:
        db['archives'] = []
    if archive_path and archive_path not in db['archives']:
        db['archives'].append(archive_path)
        save_history(db)
        return True
    return False

def add_password_to_history(db, password):
    """向历史记录中添加一个新密码（如果不存在）。"""
    if 'passwords' not in db:
        db['passwords'] = []
    if password and password not in db['passwords']:
        db['passwords'].append(password)
        save_history(db)
        return True
    return False