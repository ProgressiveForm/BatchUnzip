import subprocess
import os
from subprocess import TimeoutExpired
import tempfile
import shutil
import sys

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

SEVEN_ZIP_PATH = os.path.join(application_path, "7z.exe")

def list_archive_contents(archive_path, password=None):
    if not os.path.exists(archive_path): return {'success': False, 'files': [], 'error': '压缩包文件不存在'}
    command = [SEVEN_ZIP_PATH, 'l', '-slt', '-sccUTF-8', archive_path]
    
    if password:
        command.append(f"-p{password}")
    else:
        command.append('-p-')

    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', timeout=10)
        
        output = result.stdout
        comment = None
        if "Comment =" in output:
            try:
                comment_block = output.split('Comment =', 1)[1].split('\n\n', 1)[0]
                comment = comment_block.strip()
            except IndexError:
                pass

        if "Wrong password" in result.stderr or "Enter password" in result.stdout:
            return {'success': False, 'files': [], 'comment': comment, 'error': '密码错误或需要密码'}
        if result.returncode != 0:
            return {'success': False, 'files': [], 'comment': comment, 'error': result.stderr.strip()}
        
        all_records = _parse_list_output_final_robust(output)
        files = all_records[1:] if len(all_records) > 1 else []
        
        return {'success': True, 'files': files, 'comment': comment, 'error': None}
    except TimeoutExpired:
        return {'success': False, 'files': [], 'error': f"读取压缩包信息超时，文件可能过大或已损坏: {os.path.basename(archive_path)}"}
    except Exception as e:
        return {'success': False, 'files': [], 'error': f"发生未知错误: {e}"}

# --- 新增功能：专门用于测试密码的函数 ---
def test_archive_password(archive_path, password):
    """
    使用 7z 的 't' (test) 命令来真实地测试密码是否能解密文件内容。
    这对于文件名未加密但内容加密的压缩包至关重要。
    """
    if not os.path.exists(archive_path):
        return {'success': False, 'error': '压缩包文件不存在'}
    if not password:
        return {'success': False, 'error': '未提供密码'}

    command = [SEVEN_ZIP_PATH, 't', archive_path, f"-p{password}", '-y']

    try:
        # 使用 capture_output=True 来简化 stdout 和 stderr 的捕获
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=20)

        # 检查 stderr 是否包含密码错误信息
        if "Wrong password" in result.stderr:
            return {'success': False, 'error': '密码错误'}
        
        # 检查返回码，0 表示成功
        if result.returncode == 0:
            return {'success': True, 'error': None}
        else:
            # 捕获其他可能的错误
            error_message = result.stderr.strip() if result.stderr else "未知测试错误"
            return {'success': False, 'error': error_message}
            
    except TimeoutExpired:
        return {'success': False, 'error': f"测试密码超时: {os.path.basename(archive_path)}"}
    except Exception as e:
        return {'success': False, 'error': f"测试密码时发生未知错误: {e}"}


def extract_files(archive_path, files_info, output_dir, password=None):
    if not os.path.exists(archive_path):
        return {'success': False, 'error': '压缩包文件不存在'}
    if not files_info:
        return {'success': False, 'error': '没有指定要提取的文件'}

    files_to_extract = list(set(item['path'] for item in files_info))
    listfile_path = None
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="batchunzip_extract_")
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8-sig', suffix='.txt', newline='\r\n') as listfile:
            listfile_path = listfile.name
            for file_path in files_to_extract:
                listfile.write(file_path + '\n')

        command = [SEVEN_ZIP_PATH, 'x', archive_path, f'-o{temp_dir}', '-y', '-scsUTF-8', f'@{listfile_path}']
        if password: command.insert(-1, f"-p{password}")

        result = subprocess.run(command, capture_output=True)
        if result.returncode != 0:
            error_msg = result.stderr.decode('gbk', errors='ignore').strip()
            return {'success': False, 'error': f"7z解压失败: {error_msg}"}

        files_info.sort(key=lambda item: len(item['path']), reverse=True)
        for item in files_info:
            full_path_in_archive = os.path.normpath(item['path'])
            source_path = os.path.join(temp_dir, full_path_in_archive)
            if not os.path.exists(source_path): continue
            
            strip_path_for_this_file = item.get('strip', '')
            
            start_path = strip_path_for_this_file or '.'
            relative_path = os.path.relpath(full_path_in_archive, start_path)
            destination_path = os.path.join(output_dir, relative_path)
            
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            if os.path.lexists(destination_path):
                if os.path.isdir(destination_path) and not os.path.islink(destination_path): shutil.rmtree(destination_path)
                else: os.remove(destination_path)
            shutil.move(source_path, destination_path)
            
        return {'success': True, 'error': None}
    except Exception as e:
        return {'success': False, 'error': f"发生未知错误: {e}"}
    finally:
        if listfile_path and os.path.exists(listfile_path): os.remove(listfile_path)
        if temp_dir and os.path.exists(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True)

def _parse_list_output_final_robust(output):
    records_str = output.strip().replace('\r\n', '\n').split('\n\n')
    all_records = []
    for record_str in records_str:
        current_record = {}
        lines = record_str.strip().split('\n')
        for line in lines:
            if ' = ' in line:
                parts = line.strip().split(' = ', 1)
                if len(parts) == 2:
                    current_record[parts[0]] = parts[1]
        if current_record and 'Path' in current_record:
            all_records.append(current_record)
    return all_records