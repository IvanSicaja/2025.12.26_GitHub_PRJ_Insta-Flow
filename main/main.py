import sys
import os
import shutil
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QFileDialog, QHBoxLayout, QVBoxLayout, QLineEdit,
    QMessageBox, QSpacerItem, QSizePolicy, QScrollArea
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSettings

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')
LOG_FILENAME = 'instaflow_log.txt'
MAX_LOG_ENTRIES = 10


class ImageSorterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('InstaFlow')
        self.setWindowIcon(QIcon(r'..\assets\media\icons\icon.ico'))
        self.resize(1500, 900)
        self.setMinimumSize(1400, 800)
        self.current_folder = None
        self.target_base_folder = None   # NEW: independent target base folder
        self.images = []
        self.current_index = 0
        self.copy_mode = True  # True = Copy, False = Move
        self.settings = QSettings('ImageSorterApp', 'Settings')
        self._build_ui()
        self.update_mode_button_style()

    def _build_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        root_layout = QHBoxLayout(main_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # LEFT PANEL - scrollable
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setStyleSheet('QScrollArea { background-color: #f8f8f8; border: none; }')

        left_content = QWidget()
        left_content.setFocusPolicy(Qt.ClickFocus)
        left_content.mousePressEvent = lambda e: self.centralWidget().setFocus()
        left_panel = QVBoxLayout(left_content)
        left_panel.setAlignment(Qt.AlignTop)
        left_panel.setSpacing(12)
        left_panel.setContentsMargins(15, 15, 15, 15)

        # 1. Select folder
        lbl1 = QLabel('1. Select the folder containing images to sort:')
        lbl1.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        lbl1.setWordWrap(True)
        left_panel.addWidget(lbl1)

        self.open_btn = QPushButton('Open Folder')
        self.open_btn.setFocusPolicy(Qt.NoFocus)
        self.open_btn.setMinimumHeight(36)
        self.open_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; 
                font-weight: bold; 
                padding: 6px; 
                border: 2px solid #aaa; 
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #f8f8f8; }
        """)
        self.open_btn.clicked.connect(self.open_folder)
        left_panel.addWidget(self.open_btn)

        # 2. Navigation instructions
        lbl_nav = QLabel('2. Navigate preview images with ← → arrow keys')
        lbl_nav.setStyleSheet('QLabel { color: #444; font-size: 10pt; margin-top: 12px; }')
        left_panel.addWidget(lbl_nav)

        # 3. Mode selection
        lbl_mode = QLabel('3. Choose operation mode:')
        lbl_mode.setStyleSheet('QLabel { color: #444; font-size: 10pt; margin-top: 16px; }')
        left_panel.addWidget(lbl_mode)

        mode_desc = QLabel('• COPY: images are duplicated to target folder\n'
                           '• MOVE: images are moved and removed from current folder')
        mode_desc.setStyleSheet('QLabel { color: #666; font-size: 9.5pt; margin-left: 8px; }')
        mode_desc.setWordWrap(True)
        left_panel.addWidget(mode_desc)

        self.mode_button = QPushButton('Mode: COPY')
        self.mode_button.setCheckable(True)
        self.mode_button.setFocusPolicy(Qt.NoFocus)
        self.mode_button.setMinimumHeight(44)
        self.mode_button.clicked.connect(self.toggle_mode)
        left_panel.addWidget(self.mode_button)

        # 4. Target folders configuration
        lbl_folders = QLabel('4. Configure target folders (press key 1–0 to sort):')
        lbl_folders.setStyleSheet('QLabel { font-weight: bold; color: #333; font-size: 10.5pt; margin-top: 20px; }')
        lbl_folders.setWordWrap(True)
        left_panel.addWidget(lbl_folders)

        # --- Target base folder: use-same-as-step-1 toggle + custom picker ---
        # Divider line
        divider = QLabel()
        divider.setFixedHeight(1)
        divider.setStyleSheet('background-color: #ddd; margin: 2px 0px;')
        left_panel.addWidget(divider)

        lbl_target_header = QLabel('Sort destination folder:')
        lbl_target_header.setStyleSheet('QLabel { color: #333; font-size: 10pt; font-weight: bold; margin-top: 4px; }')
        left_panel.addWidget(lbl_target_header)

        # Toggle button: "Use same folder as Step 1"
        self.use_source_btn = QPushButton('✔  Use same folder as Step 1 (source)')
        self.use_source_btn.setCheckable(True)
        self.use_source_btn.setChecked(True)   # default: use source
        self.use_source_btn.setFocusPolicy(Qt.NoFocus)
        self.use_source_btn.setMinimumHeight(38)
        self.use_source_btn.setStyleSheet("""
            QPushButton {
                background-color: #e6f4ea; color: #2d6a4f; font-weight: bold;
                border: 2px solid #95d5b2; border-radius: 8px; padding: 6px 10px;
                text-align: left;
            }
            QPushButton:!checked {
                background-color: #f0f0f0; color: #888;
                border: 2px solid #ccc;
            }
        """)
        self.use_source_btn.clicked.connect(self.on_use_source_toggled)
        left_panel.addWidget(self.use_source_btn)

        # Custom target folder row (shown when toggle is OFF)
        self.custom_target_widget = QWidget()
        custom_target_layout = QVBoxLayout(self.custom_target_widget)
        custom_target_layout.setContentsMargins(0, 4, 0, 0)
        custom_target_layout.setSpacing(4)

        lbl_custom = QLabel('Custom target folder:')
        lbl_custom.setStyleSheet('QLabel { color: #444; font-size: 9.5pt; }')
        custom_target_layout.addWidget(lbl_custom)

        target_row = QHBoxLayout()

        self.target_folder_display = QLineEdit()
        self.target_folder_display.setPlaceholderText('No folder selected — click 📁 to choose')
        self.target_folder_display.setReadOnly(True)
        self.target_folder_display.setStyleSheet("""
            QLineEdit { 
                padding: 5px; 
                border-radius: 6px; 
                border: 2px solid #aaa;
                background-color: #f0f0f0;
                color: #333;
                font-size: 9pt;
            }
        """)
        target_row.addWidget(self.target_folder_display)

        self.select_target_btn = QPushButton('📁')
        self.select_target_btn.setFocusPolicy(Qt.NoFocus)
        self.select_target_btn.setFixedWidth(36)
        self.select_target_btn.setMinimumHeight(32)
        self.select_target_btn.setToolTip('Select custom target base folder')
        self.select_target_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; 
                font-size: 14pt;
                border: 2px solid #aaa; 
                border-radius: 8px;
                padding: 2px;
            }
            QPushButton:hover { background-color: #f8f8f8; }
        """)
        self.select_target_btn.clicked.connect(self.select_target_folder)
        target_row.addWidget(self.select_target_btn)

        self.clear_target_btn = QPushButton('✕')
        self.clear_target_btn.setFocusPolicy(Qt.NoFocus)
        self.clear_target_btn.setFixedWidth(36)
        self.clear_target_btn.setMinimumHeight(32)
        self.clear_target_btn.setToolTip('Clear custom folder selection')
        self.clear_target_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; 
                font-size: 11pt;
                border: 2px solid #aaa; 
                border-radius: 8px;
                padding: 2px;
            }
            QPushButton:hover { background-color: #ffe0e0; }
        """)
        self.clear_target_btn.clicked.connect(self.clear_target_folder)
        target_row.addWidget(self.clear_target_btn)

        custom_target_layout.addLayout(target_row)

        self.target_status_label = QLabel('')
        self.target_status_label.setStyleSheet('QLabel { color: #c0392b; font-size: 9pt; font-style: italic; }')
        self.target_status_label.setWordWrap(True)
        custom_target_layout.addWidget(self.target_status_label)

        self.custom_target_widget.setVisible(False)   # hidden by default (source mode active)
        left_panel.addWidget(self.custom_target_widget)

        divider2 = QLabel()
        divider2.setFixedHeight(1)
        divider2.setStyleSheet('background-color: #ddd; margin: 4px 0px;')
        left_panel.addWidget(divider2)
        # --- END target folder block ---

        # Sub-header and load button (below target folder selection)
        sub_header = QLabel('Check ✎ to edit name · Only folders with names will be created')
        sub_header.setStyleSheet('QLabel { color: #555; font-size: 10pt; }')
        sub_header.setWordWrap(True)
        left_panel.addWidget(sub_header)

        self.load_folders_btn = QPushButton('Load Existing Subfolders (A-Z)')
        self.load_folders_btn.setFocusPolicy(Qt.NoFocus)
        self.load_folders_btn.setMinimumHeight(36)
        self.load_folders_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; 
                font-weight: bold; 
                padding: 6px; 
                border: 2px solid #aaa;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #f8f8f8; }
        """)
        self.load_folders_btn.clicked.connect(self.load_existing_subfolders)
        left_panel.addWidget(self.load_folders_btn)

        # 10 folder inputs
        self.folder_inputs = []
        self.folder_enabled = []
        default_names = ['Family Milestones', 'My Milestones', '', '', '', '', '', '', '', '']

        for i in range(10):
            row = QHBoxLayout()

            key_label = QLabel(str((i + 1) % 10))
            key_label.setFixedWidth(28)
            key_label.setAlignment(Qt.AlignCenter)
            key_label.setStyleSheet('QLabel { font-weight: bold; font-size: 11pt; }')
            row.addWidget(key_label)

            checkbox = QPushButton('✎')
            checkbox.setCheckable(True)
            checkbox.setFixedWidth(36)
            checkbox.setStyleSheet("""
                QPushButton { 
                    border-radius: 8px; 
                    border: 2px solid #aaa; 
                    padding: 4px;
                }
                QPushButton:checked { background-color: #e0e0e0; }
            """)
            checkbox.setToolTip('Enable editing of folder name')
            checkbox.setFocusPolicy(Qt.NoFocus)
            checkbox.clicked.connect(self.on_pencil_clicked)
            row.addWidget(checkbox)

            edit = QLineEdit(default_names[i])
            edit.setEnabled(False)
            edit.setStyleSheet('QLineEdit { padding: 6px; border-radius: 6px; }')
            edit.focusInEvent = lambda e: QLineEdit.focusInEvent(edit, e)
            row.addWidget(edit)

            checkbox.toggled.connect(edit.setEnabled)

            self.folder_inputs.append(edit)
            self.folder_enabled.append(checkbox)

            left_panel.addLayout(row)

        # Create Folders button
        self.create_folders_btn = QPushButton('Create Folders')
        self.create_folders_btn.setFocusPolicy(Qt.NoFocus)
        self.create_folders_btn.setMinimumHeight(40)
        self.create_folders_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; 
                font-weight: bold; 
                padding: 10px; 
                border: 2px solid #aaa;
                border-radius: 8px;
                margin-top: 10px;
            }
            QPushButton:hover { background-color: #f8f8f8; }
        """)
        self.create_folders_btn.clicked.connect(self.create_folders)
        left_panel.addWidget(self.create_folders_btn)

        left_panel.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        left_scroll.setWidget(left_content)
        left_scroll.setFixedWidth(340)
        root_layout.addWidget(left_scroll)

        # RIGHT PANEL (image previews)
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(20, 20, 20, 20)
        right_panel.setSpacing(10)

        self.main_image_label = QLabel()
        self.main_image_label.setAlignment(Qt.AlignCenter)
        self.main_image_label.setStyleSheet('background-color: #222; border: 2px solid #444;')
        right_panel.addWidget(self.main_image_label, stretch=8)

        self.secondary_layout = QHBoxLayout()
        self.secondary_layout.setSpacing(10)
        self.secondary_layout.addStretch(1)

        self.secondary_labels = []
        for _ in range(5):
            lbl = QLabel()
            lbl.setFixedSize(120, 120)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet('background-color: #444; border: 1px solid #555; border-radius: 6px;')
            self.secondary_labels.append(lbl)
            self.secondary_layout.addWidget(lbl)

        self.secondary_layout.addStretch(1)

        right_panel.addLayout(self.secondary_layout, stretch=2)

        right_container = QWidget()
        right_container.setLayout(right_panel)
        right_container.setFocusPolicy(Qt.StrongFocus)
        right_container.mousePressEvent = lambda e: right_container.setFocus()
        root_layout.addWidget(right_container, 1)

    # --- Target folder methods ---

    def on_use_source_toggled(self):
        using_source = self.use_source_btn.isChecked()
        if using_source:
            # Switched back to "use source" — hide custom widget, clear custom folder
            self.use_source_btn.setText('✔  Use same folder as Step 1 (source)')
            self.custom_target_widget.setVisible(False)
            self.target_base_folder = None
            self.settings.remove('last_target_folder')
        else:
            # Switched to custom — show the picker area and open browser immediately
            self.use_source_btn.setText('☐  Use same folder as Step 1 (source)')
            self.custom_target_widget.setVisible(True)
            # Auto-open folder browser
            self.select_target_folder()
            # If user cancelled the dialog, revert toggle back to "use source"
            if not self.target_base_folder:
                self.use_source_btn.setChecked(True)
                self.use_source_btn.setText('✔  Use same folder as Step 1 (source)')
                self.custom_target_widget.setVisible(False)
        self.centralWidget().setFocus()

    def select_target_folder(self):
        last_target = self.settings.value('last_target_folder', '')
        start_dir = last_target if last_target and os.path.isdir(last_target) else os.getcwd()

        folder = QFileDialog.getExistingDirectory(self, 'Select Target Base Folder', start_dir)
        if not folder:
            return

        self.target_base_folder = folder
        self.settings.setValue('last_target_folder', folder)

        self.target_folder_display.setText(folder)
        self.target_folder_display.setToolTip(folder)
        self.target_status_label.setText(f'✅ Target set: {os.path.basename(folder)}')
        self.target_status_label.setStyleSheet(
            'QLabel { color: #2d6a4f; font-size: 9pt; font-style: italic; }'
        )
        self.centralWidget().setFocus()

    def clear_target_folder(self):
        self.target_base_folder = None
        self.settings.remove('last_target_folder')
        self.target_folder_display.clear()
        self.target_folder_display.setToolTip('')
        self.target_status_label.setText('⚠ No folder selected — images will not be sorted until a folder is chosen.')
        self.target_status_label.setStyleSheet(
            'QLabel { color: #c0392b; font-size: 9pt; font-style: italic; }'
        )
        self.centralWidget().setFocus()

    def get_effective_target_folder(self):
        """Returns the target base folder, falling back to the source folder."""
        if self.target_base_folder and os.path.isdir(self.target_base_folder):
            return self.target_base_folder
        return self.current_folder

    def write_log_entry(self, target_base, subfolder_name, image_src_path, image_dst_path):
        """
        Write/update ONE activity log file in the root target base folder.
        Format per line: [YYYY-MM-DD HH:MM:SS] COPY/MOVE | subfolder_name | original_source_path
        Keeps a maximum of MAX_LOG_ENTRIES entries, newest first.
        """
        log_path = os.path.join(target_base, LOG_FILENAME)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        operation = 'COPY' if self.copy_mode else 'MOVE'
        new_entry = f'[{timestamp}] {operation} | {subfolder_name} | {image_src_path}'

        existing_entries = []
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            existing_entries.append(line)
            except Exception:
                existing_entries = []

        updated_entries = [new_entry] + existing_entries
        updated_entries = updated_entries[:MAX_LOG_ENTRIES]

        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(updated_entries) + '\n')
        except Exception as e:
            print(f'Warning: could not write log file: {e}')

    # --- END target folder methods ---

    def on_pencil_clicked(self):
        self.centralWidget().setFocus()

    def open_folder(self):
        last_folder = self.settings.value('last_folder', '')
        start_dir = last_folder if last_folder and os.path.isdir(last_folder) else os.getcwd()

        folder = QFileDialog.getExistingDirectory(self, 'Select Image Folder', start_dir)
        if not folder:
            return

        self.current_folder = folder
        self.settings.setValue('last_folder', folder)

        self.images = [
            f for f in sorted(os.listdir(folder))
            if f.lower().endswith(IMAGE_EXTENSIONS)
        ]
        if not self.images:
            QMessageBox.warning(self, 'No Images', 'Selected folder has no images.')
            return

        self.current_index = 0
        self.update_previews()
        self.centralWidget().setFocus()

    def load_existing_subfolders(self):
        if not self.current_folder:
            QMessageBox.information(self, 'No Folder', 'Please open a folder first.')
            return

        # Load from target base folder if set, otherwise from source folder
        scan_folder = self.get_effective_target_folder()
        if not scan_folder:
            QMessageBox.information(self, 'No Folder', 'Please open a folder first.')
            return

        try:
            items = os.listdir(scan_folder)
            subfolders = [item for item in items if os.path.isdir(os.path.join(scan_folder, item))]
            subfolders = sorted([f for f in subfolders if not f.startswith('.')], key=str.lower)

            for edit, cb in zip(self.folder_inputs, self.folder_enabled):
                edit.setText('')
                edit.setEnabled(False)
                cb.setChecked(False)

            for i, name in enumerate(subfolders[:10]):
                self.folder_inputs[i].setText(name)
                self.folder_inputs[i].setEnabled(True)
                self.folder_enabled[i].setChecked(True)

            QMessageBox.information(
                self, 'Subfolders Loaded',
                f'Loaded {min(len(subfolders), 10)} existing subfolder(s) alphabetically.\n'
                f'Total found: {len(subfolders)}'
            )
            self.centralWidget().setFocus()
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not load subfolders:\n{str(e)}')

    def create_folders(self):
        target_base = self.get_effective_target_folder()
        if not target_base:
            return

        created_count = 0
        already_exists_count = 0

        for edit in self.folder_inputs:
            name = edit.text().strip()
            if not name:
                continue
            path = os.path.join(target_base, name)
            if os.path.exists(path):
                already_exists_count += 1
            else:
                os.makedirs(path, exist_ok=True)
                created_count += 1

        if created_count > 0:
            msg = f'{created_count} folder(s) created.'
            if already_exists_count > 0:
                msg += f'\n{already_exists_count} already exist.'
            QMessageBox.information(self, 'Done', msg)
        elif already_exists_count > 0:
            QMessageBox.information(self, 'All Exist', 'All specified folders already exist.')
        else:
            QMessageBox.information(self, 'No Names', 'No folder names were entered.')

        self.centralWidget().setFocus()

    def toggle_mode(self):
        self.copy_mode = not self.copy_mode
        if self.copy_mode:
            self.mode_button.setText('Mode: COPY')
        else:
            self.mode_button.setText('Mode: MOVE')
        self.update_mode_button_style()
        self.centralWidget().setFocus()

    def update_mode_button_style(self):
        if self.copy_mode:
            self.mode_button.setStyleSheet("""
                QPushButton {
                    background-color: #e6f4ea; color: #2d6a4f; font-weight: bold;
                    border: 2px solid #95d5b2; border-radius: 8px; padding: 8px;
                }
            """)
        else:
            self.mode_button.setStyleSheet("""
                QPushButton {
                    background-color: #fff8e1; color: #e65100; font-weight: bold;
                    border: 2px solid #ffca28; border-radius: 8px; padding: 8px;
                }
            """)

    def update_previews(self):
        if not self.images:
            self.main_image_label.clear()
            for lbl in self.secondary_labels:
                lbl.clear()
            return

        img_path = os.path.join(self.current_folder, self.images[self.current_index])
        pix = QPixmap(img_path)
        self.main_image_label.setPixmap(pix.scaled(
            self.main_image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

        offsets = [-2, -1, 0, 1, 2]
        for lbl, off in zip(self.secondary_labels, offsets):
            idx = self.current_index + off
            if 0 <= idx < len(self.images):
                p = QPixmap(os.path.join(self.current_folder, self.images[idx]))
                lbl.setPixmap(p.scaled(110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                lbl.clear()

    def keyPressEvent(self, event):
        if isinstance(self.focusWidget(), QLineEdit) and event.key() in (Qt.Key_Left, Qt.Key_Right):
            self.focusWidget().event(event)
            return

        if not self.images:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key_Right:
            self.current_index = min(self.current_index + 1, len(self.images) - 1)
            self.update_previews()
            event.accept()
        elif key == Qt.Key_Left:
            self.current_index = max(self.current_index - 1, 0)
            self.update_previews()
            event.accept()
        elif Qt.Key_1 <= key <= Qt.Key_9:
            self.handle_sort(key - Qt.Key_1)
            event.accept()
        elif key == Qt.Key_0:
            self.handle_sort(9)
            event.accept()
        else:
            super().keyPressEvent(event)

    def handle_sort(self, folder_idx):
        if folder_idx >= len(self.folder_inputs):
            return

        src_path = os.path.join(self.current_folder, self.images[self.current_index])
        target_name = self.folder_inputs[folder_idx].text().strip()
        if not target_name:
            QMessageBox.warning(self, 'Empty Name', 'Folder name is empty. Set a name first.')
            return

        # Use target base folder (independent from source folder)
        target_base = self.get_effective_target_folder()
        target_folder = os.path.join(target_base, target_name)
        os.makedirs(target_folder, exist_ok=True)
        dst_path = os.path.join(target_folder, os.path.basename(src_path))

        if os.path.exists(dst_path):
            QMessageBox.warning(self, 'File Exists',
                f'"{os.path.basename(src_path)}" already exists in "{target_name}".\nSkipped.')
            return

        was_last_image = len(self.images) == 1

        try:
            if self.copy_mode:
                shutil.copy2(src_path, dst_path)
            else:
                shutil.move(src_path, dst_path)
                del self.images[self.current_index]
                if self.images:
                    self.current_index = min(self.current_index, len(self.images) - 1)
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))
            return

        # Write activity log entry into the root target base folder
        self.write_log_entry(target_base, target_name, src_path, dst_path)

        self.update_previews()

        if not self.copy_mode and was_last_image:
            QMessageBox.information(self, 'Done', 'No more images to preview.')

        self.centralWidget().setFocus()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageSorterApp()
    window.showMaximized()
    sys.exit(app.exec_())