import sys
import time
import fnmatch
import os
import password_manager as pm
import sevenzip_handler as szh
import history_manager as hm
import tempfile
import shutil
import re
from collections import OrderedDict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QSplitter, QFileDialog,
    QLabel, QLineEdit, QDialog, QMessageBox, QMenu, QToolBar,
    QPushButton, QTreeWidget, QTreeWidgetItem, QFileIconProvider
)
from PyQt6.QtCore import Qt, pyqtSignal, QFileInfo
from PyQt6.QtGui import QAction, QIcon, QColor

# =====================================================================
# --- Dialogs and Custom Widgets ---
# =====================================================================
class PasswordBookDialog(QDialog):
    password_selected=pyqtSignal(str);try_all_triggered=pyqtSignal()
    def __init__(self,db,p=None):super().__init__(p);self.password_db=db;self.setWindowTitle("密码本");self.setMinimumWidth(400);self.password_list_widget=QListWidget();self.new_password_input=QLineEdit();self.new_password_input.setPlaceholderText("在此输入新密码...");self.add_button=QPushButton("添加");self.remove_button=QPushButton("移除选中");self.use_button=QPushButton("使用选中密码");self.try_all_button=QPushButton("全部尝试");self.close_button=QPushButton("关闭");l=QVBoxLayout();t=QHBoxLayout();t.addWidget(self.new_password_input);t.addWidget(self.add_button);l.addLayout(t);l.addWidget(self.password_list_widget);l.addWidget(self.remove_button);b=QHBoxLayout();b.addWidget(self.use_button);b.addWidget(self.try_all_button);b.addStretch();b.addWidget(self.close_button);l.addLayout(b);self.setLayout(l);self.add_button.clicked.connect(self.add_password);self.remove_button.clicked.connect(self.remove_password);self.use_button.clicked.connect(self.use_password);self.try_all_button.clicked.connect(self.try_all);self.close_button.clicked.connect(self.accept);self.password_list_widget.itemDoubleClicked.connect(self.use_password);self.refresh_list()
    def refresh_list(self):self.password_list_widget.clear();self.password_list_widget.addItems(pm.get_password_book(self.password_db))
    def add_password(self):p=self.new_password_input.text();_=pm.add_password_to_book(self.password_db,p)and(self.new_password_input.clear(),self.refresh_list())
    def remove_password(self):i=self.password_list_widget.currentItem();_=i and pm.remove_password_from_book(self.password_db,i.text())and self.refresh_list()
    def use_password(self):i=self.password_list_widget.currentItem();_=i and(self.password_selected.emit(i.text()),self.accept())
    def try_all(self):self.try_all_triggered.emit();self.accept()

class HistoryDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.history_db = db
        self.setWindowTitle("打开历史")
        self.setMinimumSize(500, 400)

        self.archive_list = QListWidget()

        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.accept)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel("历史压缩包 (最近的在最上方)"))
        main_layout.addWidget(self.archive_list)
        main_layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignRight)

        self.populate_lists()

    def populate_lists(self):
        self.archive_list.clear()
        self.archive_list.addItems(reversed(self.history_db.get('archives', [])))

class ArchiveItemWidget(QWidget):
    def __init__(self, archive_path, list_item, main_window):
        super().__init__()
        self.archive_path = archive_path
        self.list_item = list_item
        self.main_window = main_window
        self.files_cache = []
        self.archive_hash = None

        self.path_label = QLabel(os.path.basename(archive_path))
        self.path_label.setToolTip(archive_path)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码...")
        self.password_input.setVisible(False)
        self.try_button = QPushButton("尝试")
        self.try_button.setVisible(False)
        self.book_button = QPushButton("密码本...")
        self.book_button.setVisible(False)
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.path_label)
        password_layout = QHBoxLayout()
        password_layout.addWidget(self.password_input, 2)
        password_layout.addWidget(self.try_button, 1)
        password_layout.addWidget(self.book_button, 1)
        layout.addLayout(password_layout)
        self.setLayout(layout)
        self.try_button.clicked.connect(self.on_try_password)
        self.book_button.clicked.connect(self.on_open_book)
    
    def on_try_password(self): self.main_window.check_password_for_item(self)
    def on_open_book(self): self.main_window.open_password_book_for_item(self)
    
    def update_background_color(self):
        if self.list_item in self.main_window.activated_items:
            palette = self.palette()
            palette.setColor(self.backgroundRole(), QColor(229, 243, 255))
            self.setAutoFillBackground(True)
            self.setPalette(palette)
        else:
            self.setAutoFillBackground(False)
            self.update()

    def set_color(self, color):
        palette = self.palette()
        palette.setColor(self.backgroundRole(), color)
        self.setAutoFillBackground(True)
        self.setPalette(palette)

    def set_state_encrypted(self):
        self.update_background_color()
        self.password_input.setVisible(True)
        self.try_button.setVisible(True)
        self.book_button.setVisible(True)
        self.list_item.setSizeHint(self.sizeHint())

    def set_state_normal(self, files_list):
        self.files_cache = files_list
        self.update_background_color()
        self.password_input.setVisible(False)
        self.try_button.setVisible(False)
        self.book_button.setVisible(False)
        self.list_item.setSizeHint(self.sizeHint())

    def set_state_password_error(self):
        self.files_cache = []
        self.update_background_color()
        self.password_input.setVisible(True)
        self.password_input.selectAll()
        self.try_button.setVisible(True)
        self.book_button.setVisible(True)
        self.list_item.setSizeHint(self.sizeHint())


class ArchiveListWidget(QListWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
    
    def contextMenuEvent(self, event):
        context_menu = QMenu(self)
        item = self.itemAt(event.pos())
        
        if item:
            remove_action = context_menu.addAction("从列表中移除")
            delete_action = context_menu.addAction("从磁盘删除文件")
            
            action = context_menu.exec(event.globalPos())
            if action == remove_action: self.main_window.remove_archive_item(item)
            elif action == delete_action: self.main_window.delete_archive_file(item)
        else:
            add_action = context_menu.addAction("添加压缩包...")
            clear_action = context_menu.addAction("清空列表")
            action = context_menu.exec(event.globalPos())
            if action == add_action: self.main_window.add_archives()
            elif action == clear_action: self.main_window.clear_archive_list()


class FileListWidget(QListWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
    def contextMenuEvent(self, event):
        self.main_window.show_file_context_menu(event, self)

class FileTreeWidget(QTreeWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setHeaderHidden(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
    def contextMenuEvent(self, event):
        self.main_window.show_file_context_menu(event, self)

# =====================================================================
# --- 主窗口 ---
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("批量解压缩工具")
        self.setGeometry(100, 100, 1200, 700)
        self.password_db = pm.load_database()
        self.history_db = hm.load_history()
        self.active_item_for_book = None
        self.activated_items = []
        self.icon_provider = QFileIconProvider()
        self.temp_dirs_to_clean = []
        self.recent_files_menu = None
        self.MAX_RECENT_FILES = 15
        
        self.setAcceptDrops(True)

        self.archive_list_widget = ArchiveListWidget(self)
        self.archive_list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        
        self.file_tree_widget = FileTreeWidget(self)
        self.file_list_widget = FileListWidget(self)
        self.file_list_widget.setVisible(False)
        
        self.status_label = QLabel("准备就绪")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("在此搜索文件... (输入内容后自动切换为列表视图)")

        self._create_menu_bar()
        self._create_filter_bar()
        self._update_recent_files_menu()

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("压缩包面板 (点击激活/取消)"))
        left_layout.addWidget(self.archive_list_widget)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("文件面板 (按压缩包分组，搜索时切换为列表)"))
        right_layout.addWidget(self.search_input)
        right_layout.addWidget(self.file_tree_widget)
        right_layout.addWidget(self.file_list_widget)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([450, 750])
        
        self.statusBar().addWidget(self.status_label)

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.addWidget(main_splitter)
        self.setCentralWidget(central_widget)

        self.archive_list_widget.itemClicked.connect(self.on_archive_item_clicked)
        self.search_input.textChanged.connect(self.update_aggregated_file_list_display)
        
        self.file_tree_widget.itemDoubleClicked.connect(self.on_file_item_double_clicked)
        self.file_list_widget.itemDoubleClicked.connect(self.on_file_item_double_clicked)

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&文件")
        add_action = QAction("&添加压缩包...", self)
        add_action.triggered.connect(lambda: self.add_archives())
        file_menu.addAction(add_action)

        self.recent_files_menu = file_menu.addMenu("打开最近")
        
        file_menu.addSeparator()
        exit_action = QAction("&退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        edit_menu = menu_bar.addMenu("&编辑")
        password_book_action = QAction("&密码本...", self)
        password_book_action.triggered.connect(self.open_password_book_globally)
        edit_menu.addAction(password_book_action)

        view_menu = menu_bar.addMenu("&查看")
        history_action = QAction("&查看打开历史...", self)
        history_action.triggered.connect(self.show_history_dialog)
        view_menu.addAction(history_action)

    def _update_recent_files_menu(self):
        self.recent_files_menu.clear()
        recent_files = self.history_db.get('archives', [])
        
        files_to_show = []
        for path in reversed(recent_files):
            if os.path.exists(path):
                files_to_show.append(path)
            if len(files_to_show) >= self.MAX_RECENT_FILES:
                break
        
        if not files_to_show:
            empty_action = QAction("(空)", self)
            empty_action.setEnabled(False)
            self.recent_files_menu.addAction(empty_action)
        else:
            for path in files_to_show:
                action = QAction(path, self)
                action.triggered.connect(lambda checked=False, p=path: self.add_archives([p]))
                self.recent_files_menu.addAction(action)

    def _create_filter_bar(self):
        filter_bar = QToolBar("分类筛选")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, filter_bar)
        filters = {"图片": "jpg jpeg png gif bmp tiff webp heic raw cr2 nef arw dng", "视频": "mp4 mkv avi mov wmv flv rmvb m4v ts webm", "音乐": "mp3 flac wav aac ogg wma m4a ape cue", "文档": "doc docx xls xlsx ppt pptx pdf txt rtf odt ods odp md csv", "压缩包": "zip rar 7z tar gz bz2 xz", "可执行": "exe msi bat sh com app dmg", "全部": ""}
        for name, extensions_str in filters.items():
            action = QAction(name, self)
            if extensions_str: action.triggered.connect(lambda checked=False, exts=extensions_str: self.apply_filter(exts))
            else: action.triggered.connect(self.clear_filter)
            filter_bar.addAction(action)

    def apply_filter(self, extensions_str):
        extensions = extensions_str.split()
        search_pattern = "|".join([f"*.{ext}" for ext in extensions])
        self.search_input.setText(search_pattern)

    def clear_filter(self): self.search_input.clear()
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        file_paths = [os.path.normpath(url.toLocalFile()) for url in urls]
        self.add_archives(file_paths)

    def remove_archive_item(self, list_item):
        if list_item in self.activated_items:
            self.activated_items.remove(list_item)
        row = self.archive_list_widget.row(list_item)
        self.archive_list_widget.takeItem(row)
        self.update_aggregated_file_list_display()

    def clear_archive_list(self):
        reply = QMessageBox.question(self, "确认操作", "您确定要清空左侧的压缩包列表吗？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.activated_items.clear()
            self.archive_list_widget.clear()
            self.update_aggregated_file_list_display()

    def delete_archive_file(self, list_item):
        widget = self.archive_list_widget.itemWidget(list_item)
        if not widget: return
        file_path = widget.archive_path
        reply = QMessageBox.question(self, "确认删除", f"您确定要将以下文件移动到回收站吗？\n\n{file_path}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from send2trash import send2trash
                send2trash(file_path)
                self.remove_archive_item(list_item)
                self.statusBar().showMessage(f"文件 {os.path.basename(file_path)} 已移至回收站。", 3000)
            except ImportError: QMessageBox.warning(self, "缺少组件", "请先安装 'send2trash' 库来实现安全的删除功能。\n\npip install send2trash")
            except Exception as e: QMessageBox.critical(self, "删除失败", f"无法删除文件：\n{e}")

    def add_nested_archive(self, list_item):
        data = list_item.data(Qt.ItemDataRole.UserRole) if isinstance(list_item, QListWidgetItem) else list_item.data(0, Qt.ItemDataRole.UserRole)
        nested_archive_path = data['path']
        source_widget = data['source_widget']
        temp_dir = tempfile.mkdtemp(prefix="batchunzip_")
        self.statusBar().showMessage(f"正在处理嵌套压缩包: {nested_archive_path}...", 2000)
        QApplication.processEvents()
        password = None
        if source_widget.archive_hash: password = pm.get_password_for_archive(self.password_db, source_widget.archive_hash)
        result = szh.extract_files(source_widget.archive_path, [{'path': nested_archive_path, 'strip': ''}], temp_dir, password)
        if result['success']:
            extracted_path = os.path.normpath(os.path.join(temp_dir, nested_archive_path))
            if os.path.exists(extracted_path):
                self.add_archives([extracted_path])
                self.statusBar().showMessage("嵌套压缩包添加成功！", 3000)
            else:
                QMessageBox.warning(self, "错误", f"无法在临时目录中找到解压后的文件：\n{extracted_path}")
                shutil.rmtree(temp_dir)
        else:
            QMessageBox.critical(self, "错误", f"解压嵌套压缩包失败：\n{result['error']}")
            shutil.rmtree(temp_dir)

    def on_archive_item_clicked(self, list_item):
        if list_item in self.activated_items:
            self.activated_items.remove(list_item)
        else:
            self.activated_items.append(list_item)
        
        for i in range(self.archive_list_widget.count()):
            item = self.archive_list_widget.item(i)
            widget = self.archive_list_widget.itemWidget(item)
            if widget:
                widget.update_background_color()
        
        self.update_aggregated_file_list_display()

    def update_aggregated_file_list_display(self):
        search_term = self.search_input.text()
        
        files_by_source = OrderedDict()
        for list_item in self.activated_items:
            item_widget = self.archive_list_widget.itemWidget(list_item)
            if item_widget and item_widget.files_cache:
                files_by_source[item_widget] = item_widget.files_cache

        if not search_term:
            self.file_list_widget.setVisible(False)
            self.file_tree_widget.setVisible(True)
            self.file_tree_widget.clear()

            for source_widget, files_list in files_by_source.items():
                archive_name = os.path.basename(source_widget.archive_path)
                root_item = QTreeWidgetItem(self.file_tree_widget, [archive_name])
                root_item.setIcon(0, self.icon_provider.icon(QFileInfo("dummy.zip")))
                root_item.setFlags(root_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                root_item.setExpanded(True)

                file_tree = OrderedDict()
                for file_details in files_list:
                    info = {'path': file_details.get('Path', '未知'), 'source_widget': source_widget, 'is_dir': 'D' in file_details.get('Attributes', '')}
                    parts = info['path'].replace('\\', os.sep).split(os.sep)
                    current_level = file_tree
                    for part in parts:
                        if part not in current_level:
                            current_level[part] = OrderedDict()
                        current_level = current_level[part]
                    current_level['__data__'] = info
                
                self._populate_tree(root_item, file_tree)
        else:
            self.file_tree_widget.setVisible(False)
            self.file_list_widget.setVisible(True)
            self.file_list_widget.clear()

            all_files_info = []
            for files in files_by_source.values():
                all_files_info.extend(files)

            patterns = [f"*{p.strip()}*" for p in search_term.split('|')]
            
            for file_details in all_files_info:
                if 'D' in file_details.get('Attributes', ''): continue

                file_path = file_details.get('Path', '未知')
                if not any(fnmatch.fnmatch(file_path.lower(), pattern.lower()) for pattern in patterns):
                    continue
                
                source_widget = None
                for sw, fl in files_by_source.items():
                    if file_details in fl:
                        source_widget = sw
                        break
                
                if source_widget:
                    source_name = os.path.basename(source_widget.archive_path)
                    display_text = f"{file_path}  (来源: {source_name})"
                    list_entry = QListWidgetItem(display_text)
                    list_entry.setIcon(self.icon_provider.icon(QFileInfo(file_path)))
                    list_entry.setData(Qt.ItemDataRole.UserRole, {'path': file_path, 'source_widget': source_widget})
                    self.file_list_widget.addItem(list_entry)

    def _populate_tree(self, parent_item, children_dict, current_path=""):
        sorted_children = sorted(children_dict.items(), key=lambda item: '__data__' not in item[1])
        for name, content in sorted_children:
            if name == '__data__': continue
            
            new_path = os.path.join(current_path, name)
            is_dir = '__data__' not in content or content['__data__']['is_dir']
            
            tree_item = QTreeWidgetItem(parent_item, [name])
            
            if is_dir:
                tree_item.setIcon(0, self.icon_provider.icon(QFileIconProvider.IconType.Folder))
            else:
                tree_item.setIcon(0, self.icon_provider.icon(QFileInfo(name)))

            if is_dir:
                tree_item.setData(0, Qt.ItemDataRole.UserRole, {'path': new_path, 'is_dir': True})
                self._populate_tree(tree_item, content, new_path)
            else:
                file_data = content['__data__']
                tree_item.setData(0, Qt.ItemDataRole.UserRole, {'path': file_data['path'], 'source_widget': file_data['source_widget'], 'is_dir': False})


    def show_file_context_menu(self, event, widget):
        context_menu = QMenu(self)
        selected_items = widget.selectedItems()
        if selected_items:
            context_menu.addAction("解压选中项到...").triggered.connect(self.extract_selected_files)
            context_menu.addAction("解压选中项并删除来源压缩包到...").triggered.connect(self.extract_and_delete_selected_files)
        if len(selected_items) == 1:
            context_menu.addSeparator()
            context_menu.addAction("作为压缩包添加到左侧面板").triggered.connect(lambda: self.add_nested_archive(selected_items[0]))
        if context_menu.actions():
            context_menu.exec(widget.viewport().mapToGlobal(event.pos()))

    def _collect_files_from_tree_item(self, item, all_files_data, strip_path):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            if not data.get('is_dir'):
                file_info = data.copy()
                file_info['strip'] = strip_path
                all_files_data.append(file_info)
            else:
                for i in range(item.childCount()):
                    self._collect_files_from_tree_item(item.child(i), all_files_data, strip_path)

    def _get_selected_file_data(self):
        if self.file_tree_widget.isVisible():
            selected_items = self.file_tree_widget.selectedItems()
        else:
            selected_items = self.file_list_widget.selectedItems()

        if not selected_items:
            QMessageBox.warning(self, "提示", "请在右侧文件面板中至少选择一个要解压的文件或文件夹。")
            return None, None

        all_files_data = []
        if self.file_tree_widget.isVisible():
            for item in selected_items:
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if not data: continue
                
                item_path = data['path']
                strip_path = os.path.dirname(item_path)
                
                self._collect_files_from_tree_item(item, all_files_data, strip_path)
        else: 
            for item in selected_items:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    file_info = data.copy()
                    file_info['strip'] = os.path.dirname(data['path'])
                    all_files_data.append(file_info)

        if not all_files_data:
            QMessageBox.warning(self, "提示", "选择的文件夹为空或未能收集到任何文件。")
            return None, None
        
        unique_files_info = {}
        for data in all_files_data:
            key = (data['source_widget'], data['path'])
            if key not in unique_files_info:
                unique_files_info[key] = data

        files_by_source = {}
        for (source_widget, path), data in unique_files_info.items():
            if source_widget not in files_by_source:
                files_by_source[source_widget] = []
            files_by_source[source_widget].append({'path': path, 'strip': data['strip']})

        return files_by_source, len(unique_files_info)


    def extract_selected_files(self):
        files_by_source, total_files = self._get_selected_file_data()
        if not files_by_source: return

        output_dir = QFileDialog.getExistingDirectory(self, "选择解压目标文件夹", "")
        if not output_dir: return

        self.statusBar().showMessage(f"准备解压 {total_files} 个文件...")
        QApplication.processEvents()
        has_error = False
        for source_widget, files_info in files_by_source.items():
            archive_path = source_widget.archive_path
            password = None
            if source_widget.archive_hash: password = pm.get_password_for_archive(self.password_db, source_widget.archive_hash)
            result = szh.extract_files(archive_path, files_info, output_dir, password)
            if not result['success']:
                QMessageBox.critical(self, "错误", f"从 {os.path.basename(archive_path)} 解压文件时发生错误:\n{result['error']}")
                has_error = True
                break
        
        if not has_error:
            self.statusBar().showMessage("解压成功！", 3000)
            QMessageBox.information(self, "成功", f"已成功解压 {total_files} 个文件到:\n{output_dir}")
        else:
            self.statusBar().showMessage("解压失败。")

    def extract_and_delete_selected_files(self):
        files_by_source, total_files = self._get_selected_file_data()
        if not files_by_source: return

        output_dir = QFileDialog.getExistingDirectory(self, "选择解压目标文件夹", "")
        if not output_dir: return

        self.statusBar().showMessage(f"准备解压 {total_files} 个文件...")
        QApplication.processEvents()
        
        overall_error = False
        successfully_extracted_sources = []

        for source_widget, files_info in files_by_source.items():
            archive_path = source_widget.archive_path
            password = None
            if source_widget.archive_hash: password = pm.get_password_for_archive(self.password_db, source_widget.archive_hash)
            result = szh.extract_files(archive_path, files_info, output_dir, password)
            if not result['success']:
                QMessageBox.critical(self, "解压错误", f"从 {os.path.basename(archive_path)} 解压文件时发生错误，该压缩包不会被删除:\n{result['error']}")
                overall_error = True
            else:
                successfully_extracted_sources.append(source_widget)

        if not successfully_extracted_sources:
            self.statusBar().showMessage("解压失败，未删除任何文件。")
            return

        sources_to_delete = set(successfully_extracted_sources)

        for source_widget in sources_to_delete:
            for i in range(self.archive_list_widget.count()):
                list_item = self.archive_list_widget.item(i)
                widget = self.archive_list_widget.itemWidget(list_item)
                if widget == source_widget:
                    try:
                        from send2trash import send2trash
                        send2trash(widget.archive_path)
                        self.remove_archive_item(list_item)
                        self.statusBar().showMessage(f"文件 {os.path.basename(widget.archive_path)} 已移至回收站。", 4000)
                    except ImportError:
                        QMessageBox.warning(self, "缺少组件", "请先安装 'send2trash' 库来实现安全的删除功能。\n\npip install send2trash")
                        overall_error = True
                    except Exception as e:
                        QMessageBox.critical(self, "删除失败", f"无法删除文件 '{widget.archive_path}':\n{e}")
                        overall_error = True
                    break 
        
        if not overall_error:
            self.statusBar().showMessage("操作成功！", 3000)
            QMessageBox.information(self, "成功", f"已成功解压 {total_files} 个文件到:\n{output_dir}\n\n相关的来源压缩包已移至回收站。")
        else:
            self.statusBar().showMessage("操作已完成，但中间出现错误。")
            
    def add_archives(self, file_paths=None):
        if not file_paths:
            supported_formats = "压缩包 (*.zip *.rar *.7z);;所有文件 (*.*)"
            paths, _ = QFileDialog.getOpenFileNames(self, "选择压缩包文件", "", supported_formats)
            if not paths: return
            file_paths = [os.path.normpath(p) for p in paths]
        
        if file_paths:
            primary_archives = self._identify_primary_archives(file_paths)
            archives_added = False
            for path in primary_archives:
                if hm.add_archive_to_history(self.history_db, path):
                    archives_added = True
                self.add_archive_item(path)
            
            if archives_added:
                self._update_recent_files_menu()

    def _identify_primary_archives(self, file_paths):
        archive_sets = {}
        part_rar_pattern = re.compile(r"^(.*)\.part\d+\.rar$", re.IGNORECASE)
        numbered_ext_pattern = re.compile(r"^(.*)\.(\d{3})$", re.IGNORECASE)
        zip_ext_pattern = re.compile(r"^(.*)\.z\d{2}$", re.IGNORECASE)

        unprocessed_paths = list(file_paths)
        processed_bases = set()
        
        for path in file_paths:
            base_name, part_num, is_multipart = None, -1, False

            match = part_rar_pattern.match(path)
            if match:
                base_name = match.group(1) + ".rar"
                part_num_str = re.search(r"\.part(\d+)\.rar$", path, re.IGNORECASE).group(1)
                part_num = int(part_num_str)
                is_multipart = True
            
            if not is_multipart:
                match = numbered_ext_pattern.match(path)
                if match:
                    base_name = match.group(1)
                    part_num = int(match.group(2))
                    is_multipart = True

            if not is_multipart:
                match = zip_ext_pattern.match(path)
                if match:
                    base_name = match.group(1) + ".zip"
                    part_num_str = re.search(r"\.z(\d{2})$", path, re.IGNORECASE).group(1)
                    part_num = int(part_num_str)
                    is_multipart = True

            if is_multipart:
                if base_name not in archive_sets:
                    archive_sets[base_name] = (part_num, path)
                elif part_num < archive_sets[base_name][0]:
                    archive_sets[base_name] = (part_num, path)
                
                if path in unprocessed_paths:
                    unprocessed_paths.remove(path)
                processed_bases.add(base_name)

        primary_files = [item[1] for item in archive_sets.values()]
        
        for path in unprocessed_paths:
            if path not in processed_bases:
                primary_files.append(path)

        return list(OrderedDict.fromkeys(primary_files))

    def add_archive_item(self, path):
        for i in range(self.archive_list_widget.count()):
            item = self.archive_list_widget.item(i)
            widget = self.archive_list_widget.itemWidget(item)
            if widget and widget.archive_path == path:
                return
        
        list_item = QListWidgetItem()
        item_widget = ArchiveItemWidget(path, list_item, self)
        list_item.setSizeHint(item_widget.sizeHint())
        self.archive_list_widget.addItem(list_item)
        self.archive_list_widget.setItemWidget(list_item, item_widget)
        
        result = szh.list_archive_contents(path)
        
        password_needed = False
        if result['error'] == '密码错误或需要密码':
            password_needed = True
        elif result['success']:
            is_content_encrypted = any('Encrypted' in f and f['Encrypted'] == '+' for f in result['files'])
            if is_content_encrypted:
                password_needed = True
                item_widget.files_cache = result['files']
                self.update_aggregated_file_list_display()
            else:
                item_widget.set_state_normal(result['files'])
                if not self.activated_items:
                    self.on_archive_item_clicked(list_item)
                else:
                    self.update_aggregated_file_list_display()

        if password_needed:
            basename = os.path.basename(path)
            
            pwd = pm.get_password_for_archive_by_name(self.password_db, basename)
            if pwd and self.check_password_for_item(item_widget, password=pwd):
                return

            item_widget.archive_hash = pm.calculate_file_hash(path)
            if item_widget.archive_hash:
                pwd = pm.get_password_for_archive(self.password_db, item_widget.archive_hash)
                if pwd and self.check_password_for_item(item_widget, password=pwd):
                    return
            
            item_widget.set_state_encrypted()

        elif not result['success']:
            row = self.archive_list_widget.row(list_item)
            self.archive_list_widget.takeItem(row)
            self.statusBar().showMessage(f"'{os.path.basename(path)}' 不是一个有效的或支持的压缩包。", 4000)
            print(f"处理文件时发生错误 {path}: {result['error']}")

    def check_password_for_item(self, item_widget, password=None):
        pwd_to_try = password if password is not None else item_widget.password_input.text()
        if not pwd_to_try: return False
        
        list_result = szh.list_archive_contents(item_widget.archive_path, password=pwd_to_try)
        
        if not list_result['success']:
            if item_widget.files_cache:
                item_widget.files_cache = []
                self.update_aggregated_file_list_display()
            item_widget.set_state_password_error()
            return False

        files = list_result['files']
        is_content_encrypted = any('Encrypted' in f and f['Encrypted'] == '+' for f in files)

        if is_content_encrypted:
            test_result = szh.test_archive_password(item_widget.archive_path, pwd_to_try)
            if not test_result['success']:
                if item_widget.files_cache:
                    item_widget.files_cache = []
                    self.update_aggregated_file_list_display()
                item_widget.set_state_password_error()
                self.statusBar().showMessage("密码错误！", 3000)
                return False
        
        item_widget.set_state_normal(files)
        
        if not item_widget.archive_hash:
            item_widget.archive_hash = pm.calculate_file_hash(item_widget.archive_path)
        if item_widget.archive_hash:
            pm.save_password_for_archive(self.password_db, item_widget.archive_hash, pwd_to_try)
        
        pm.save_password_for_archive_by_name(self.password_db, os.path.basename(item_widget.archive_path), pwd_to_try)
        pm.add_password_to_book(self.password_db, pwd_to_try)

        self.update_aggregated_file_list_display()
        return True


    def open_password_book_for_item(self, item_widget):
        self.active_item_for_book = item_widget
        dialog = PasswordBookDialog(self.password_db, self)
        dialog.password_selected.connect(self.on_password_from_book_selected)
        dialog.try_all_triggered.connect(self.on_try_all_from_book)
        dialog.exec()

    def open_password_book_globally(self):
        self.active_item_for_book = None
        dialog = PasswordBookDialog(self.password_db, self)
        dialog.exec()

    def on_password_from_book_selected(self, password):
        if self.active_item_for_book:
            self.active_item_for_book.password_input.setText(password)
            self.check_password_for_item(self.active_item_for_book)

    def on_try_all_from_book(self):
        if not self.active_item_for_book: return
        
        passwords = pm.get_password_book(self.password_db)
        if not passwords:
            QMessageBox.information(self, "提示", "您的密码本是空的！")
            return
            
        item_widget = self.active_item_for_book
        original_text = os.path.basename(item_widget.archive_path)
        
        for i, password in enumerate(passwords):
            item_widget.path_label.setText(f"尝试中 ({i+1}/{len(passwords)}): {password}")
            QApplication.processEvents()
            if self.check_password_for_item(item_widget, password=password):
                item_widget.path_label.setText(original_text)
                QMessageBox.information(self, "成功", f"密码 '{password}' 正确！")
                return
            time.sleep(0.05)

        item_widget.path_label.setText(original_text)
        QMessageBox.warning(self, "失败", "密码本中的所有密码都尝试失败。")

    def on_file_item_double_clicked(self, item):
        if isinstance(item, QTreeWidgetItem):
            data = item.data(0, Qt.ItemDataRole.UserRole)
        else: # QListWidgetItem
            data = item.data(Qt.ItemDataRole.UserRole)

        if not data or data.get('is_dir', False):
            return

        file_path_in_archive = data['path']
        source_widget = data['source_widget']

        temp_dir = tempfile.mkdtemp(prefix="batchunzip_open_")
        self.temp_dirs_to_clean.append(temp_dir)

        self.statusBar().showMessage(f"正在解压 '{os.path.basename(file_path_in_archive)}' 到临时位置...", 3000)
        QApplication.processEvents()

        password = None
        if source_widget.archive_hash:
            password = pm.get_password_for_archive(self.password_db, source_widget.archive_hash)

        result = szh.extract_files(
            source_widget.archive_path,
            [{'path': file_path_in_archive, 'strip': ''}],
            temp_dir,
            password
        )

        if result['success']:
            extracted_file_path = os.path.join(temp_dir, file_path_in_archive)
            if os.path.exists(extracted_file_path):
                try:
                    os.startfile(extracted_file_path)
                    self.statusBar().showMessage(f"已调用默认程序打开 '{os.path.basename(extracted_file_path)}'", 3000)
                except AttributeError:
                    import subprocess
                    if sys.platform == "win32":
                        os.startfile(extracted_file_path)
                    elif sys.platform == "darwin":
                        subprocess.call(["open", extracted_file_path])
                    else:
                        subprocess.call(["xdg-open", extracted_file_path])
                except Exception as e:
                    QMessageBox.critical(self, "打开失败", f"无法用默认程序打开文件：\n{e}")
            else:
                QMessageBox.warning(self, "错误", "文件解压成功，但在临时目录中找不到。")
        else:
            QMessageBox.critical(self, "解压失败", f"无法解压文件以打开：\n{result['error']}")

    def show_history_dialog(self):
        dialog = HistoryDialog(self.history_db, self)
        dialog.exec()

    def closeEvent(self, event):
        for temp_dir in self.temp_dirs_to_clean:
            shutil.rmtree(temp_dir, ignore_errors=True)
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())