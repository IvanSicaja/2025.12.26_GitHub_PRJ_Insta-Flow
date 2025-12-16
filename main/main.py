import sys
import os
import shutil
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QFileDialog, QHBoxLayout, QVBoxLayout, QLineEdit,
    QMessageBox, QSpacerItem, QSizePolicy
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QSettings

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')

class ImageSorterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Image Sorting Preview App')
        self.resize(1500, 900)  # Slightly larger window for better visibility
        self.current_folder = None
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

        # LEFT PANEL - wider and with clear section instructions
        left_panel = QVBoxLayout()
        left_panel.setAlignment(Qt.AlignTop)
        left_panel.setSpacing(16)

        # Instruction above Open Folder
        open_instruction = QLabel('1. Select the folder containing images to sort:')
        open_instruction.setStyleSheet('QLabel { color: #444; font-size: 11pt; margin-top: 10px; }')
        open_instruction.setWordWrap(True)
        left_panel.addWidget(open_instruction)

        self.open_btn = QPushButton('Open Folder')
        self.open_btn.setFocusPolicy(Qt.NoFocus)
        self.open_btn.setMinimumHeight(40)
        self.open_btn.setStyleSheet("""
            QPushButton {
                border: 2px solid #aaa;
                border-radius: 8px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
        """)
        self.open_btn.clicked.connect(self.open_folder)
        left_panel.addWidget(self.open_btn)

        # Instruction above Mode button
        mode_instruction = QLabel('2. Choose operation mode:')
        mode_instruction.setStyleSheet('QLabel { color: #444; font-size: 11pt; margin-top: 20px; }')
        left_panel.addWidget(mode_instruction)

        self.mode_button = QPushButton('Mode: COPY')
        self.mode_button.setCheckable(True)
        self.mode_button.setFocusPolicy(Qt.NoFocus)
        self.mode_button.setMinimumHeight(48)
        self.mode_button.clicked.connect(self.toggle_mode)
        left_panel.addWidget(self.mode_button)

        # Create Folders button with rounded style
        self.create_folders_btn = QPushButton('Create Folders')
        self.create_folders_btn.setFocusPolicy(Qt.NoFocus)
        self.create_folders_btn.setMinimumHeight(40)
        self.create_folders_btn.setStyleSheet("""
            QPushButton {
                border: 2px solid #aaa;
                border-radius: 8px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
        """)
        self.create_folders_btn.clicked.connect(self.create_folders)
        left_panel.addWidget(self.create_folders_btn)

        # General navigation info
        info_label = QLabel('Navigate with ← → arrows\nSort current image with keys 1–0')
        info_label.setWordWrap(True)
        info_label.setStyleSheet('QLabel { color: #666; font-size: 12pt; margin-top: 20px; }')
        left_panel.addWidget(info_label)

        # Folder configuration section
        header_label = QLabel('3. Configure target folders (press key to sort to folder):')
        header_label.setStyleSheet('QLabel { font-weight: bold; color: #333; font-size: 12pt; margin-top: 20px; }')
        left_panel.addWidget(header_label)

        sub_header = QLabel('Check ✎ to edit folder name · Only folders with names will be created')
        sub_header.setWordWrap(True)
        sub_header.setStyleSheet('QLabel { color: #555; font-size: 11pt; }')
        left_panel.addWidget(sub_header)

        # 10 folder inputs
        self.folder_inputs = []
        self.folder_enabled = []
        default_names = ['family', 'me', '', '', '', '', '', '', '', '']

        for i in range(10):
            row = QHBoxLayout()

            key_label = QLabel(str((i + 1) % 10))  # 1–9, 0 for 10th
            key_label.setFixedWidth(30)
            key_label.setAlignment(Qt.AlignCenter)
            key_label.setStyleSheet('QLabel { font-weight: bold; font-size: 12pt; }')
            row.addWidget(key_label)

            checkbox = QPushButton('✎')
            checkbox.setCheckable(True)
            checkbox.setFixedWidth(40)
            checkbox.setToolTip('Enable editing of folder name')
            checkbox.setFocusPolicy(Qt.NoFocus)
            row.addWidget(checkbox)

            edit = QLineEdit(default_names[i])
            edit.setEnabled(False)
            edit.setMinimumWidth(180)
            row.addWidget(edit)

            checkbox.toggled.connect(edit.setEnabled)

            self.folder_inputs.append(edit)
            self.folder_enabled.append(checkbox)

            left_panel.addLayout(row)

        left_panel.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        left_container = QWidget()
        left_container.setLayout(left_panel)
        left_container.setFixedWidth(320)  # Much wider for full text visibility
        left_container.setStyleSheet('QWidget { background-color: #f8f8f8; }')
        root_layout.addWidget(left_container)

        # RIGHT PANEL (image previews)
        right_panel = QVBoxLayout()

        self.main_image_label = QLabel()
        self.main_image_label.setAlignment(Qt.AlignCenter)
        self.main_image_label.setStyleSheet('background-color: #222;')
        right_panel.addWidget(self.main_image_label, 8)

        self.secondary_layout = QHBoxLayout()
        self.secondary_labels = []
        for _ in range(5):
            lbl = QLabel()
            lbl.setFixedSize(120, 120)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet('background-color: #444; border: 1px solid #555;')
            self.secondary_labels.append(lbl)
            self.secondary_layout.addWidget(lbl)

        right_panel.addLayout(self.secondary_layout, 2)

        right_container = QWidget()
        right_container.setLayout(right_panel)
        root_layout.addWidget(right_container, 1)

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

    def create_folders(self):
        if not self.current_folder:
            return

        created_count = 0
        already_exists_count = 0
        empty_count = 0

        for edit in self.folder_inputs:
            name = edit.text().strip()
            if not name:
                empty_count += 1
                continue

            path = os.path.join(self.current_folder, name)
            if os.path.exists(path):
                already_exists_count += 1
            else:
                os.makedirs(path, exist_ok=True)
                created_count += 1

        if created_count > 0:
            msg = f'{created_count} folder(s) created successfully.'
            if already_exists_count > 0:
                msg += f'\n{already_exists_count} folder(s) already exist and were skipped.'
            QMessageBox.information(self, 'Folders Created', msg)
        elif already_exists_count > 0:
            QMessageBox.information(self, 'Folders Exist', 'All specified folders already exist.')
        else:
            QMessageBox.information(self, 'No Folders', 'No folder names were provided.')

    def toggle_mode(self):
        self.copy_mode = not self.copy_mode
        if self.copy_mode:
            self.mode_button.setText('Mode: COPY')
        else:
            self.mode_button.setText('Mode: MOVE')  # Removed ⚠️ icon
        self.update_mode_button_style()

    def update_mode_button_style(self):
        if self.copy_mode:
            # Calm, safe green (kept as-is – you said it's great)
            self.mode_button.setStyleSheet("""
                QPushButton {
                    background-color: #e6f4ea;
                    color: #2d6a4f;
                    font-weight: bold;
                    border: 2px solid #95d5b2;
                    border-radius: 8px;
                    padding: 8px;
                }
            """)
        else:
            # Yellow/orange caution tone for MOVE – visible but comfortable
            self.mode_button.setStyleSheet("""
                QPushButton {
                    background-color: #fff8e1;
                    color: #e65100;
                    font-weight: bold;
                    border: 2px solid #ffca28;
                    border-radius: 8px;
                    padding: 8px;
                }
            """)

    def update_previews(self):
        if not self.images:
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
        if not self.images:
            return super().keyPressEvent(event)

        key = event.key()
        if key == Qt.Key_Right:
            self.current_index = min(self.current_index + 1, len(self.images) - 1)
            self.update_previews()
            event.accept()
            return
        elif key == Qt.Key_Left:
            self.current_index = max(self.current_index - 1, 0)
            self.update_previews()
            event.accept()
            return

        if Qt.Key_1 <= key <= Qt.Key_9:
            folder_idx = key - Qt.Key_1
            self.handle_sort(folder_idx)
            event.accept()
        elif key == Qt.Key_0:
            self.handle_sort(9)
            event.accept()

    def handle_sort(self, folder_idx):
        if folder_idx >= len(self.folder_inputs):
            return

        src_path = os.path.join(self.current_folder, self.images[self.current_index])
        target_folder_name = self.folder_inputs[folder_idx].text().strip()
        if not target_folder_name:
            QMessageBox.warning(self, 'Invalid Folder', 'Folder name is empty. Set a name first.')
            return

        target_folder = os.path.join(self.current_folder, target_folder_name)
        os.makedirs(target_folder, exist_ok=True)

        dst_path = os.path.join(target_folder, os.path.basename(src_path))

        if os.path.exists(dst_path):
            QMessageBox.warning(
                self, 'File Exists',
                f'An image named "{os.path.basename(src_path)}" already exists in "{target_folder_name}".\nOperation skipped.'
            )
            return

        try:
            if self.copy_mode:
                shutil.copy2(src_path, dst_path)
            else:
                shutil.move(src_path, dst_path)
                del self.images[self.current_index]
                self.current_index = min(self.current_index, len(self.images) - 1 if self.images else 0)
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))
            return

        self.update_previews()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageSorterApp()
    window.show()
    sys.exit(app.exec_())