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
        self.resize(1500, 900)
        self.current_folder = None
        self.images = []
        self.current_index = 0
        self.copy_mode = True
        self.settings = QSettings('ImageSorterApp', 'Settings')
        self._build_ui()
        self.update_mode_button_style()

    def _build_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        root_layout = QHBoxLayout(main_widget)

        # LEFT PANEL
        left_panel = QVBoxLayout()
        left_panel.setAlignment(Qt.AlignTop)
        left_panel.setSpacing(16)

        # 1. Select folder
        lbl1 = QLabel('1. Select the folder containing images to sort:')
        lbl1.setStyleSheet('QLabel { color: #444; font-size: 11pt; }')
        lbl1.setWordWrap(True)
        left_panel.addWidget(lbl1)

        self.open_btn = QPushButton('Open Folder')
        self.open_btn.setFocusPolicy(Qt.NoFocus)
        self.open_btn.setMinimumHeight(40)
        self.open_btn.setStyleSheet("""
            QPushButton { border: 2px solid #aaa; border-radius: 8px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #f0f0f0; }
        """)
        self.open_btn.clicked.connect(self.open_folder)
        left_panel.addWidget(self.open_btn)

        # 2. Navigation info
        lbl2 = QLabel('2. Navigate preview images:')
        lbl2.setStyleSheet('QLabel { color: #444; font-size: 11pt; margin-top: 20px; }')
        left_panel.addWidget(lbl2)

        nav_info = QLabel('Use ← → arrow keys to move between images\nPress 1–0 to sort current image')
        nav_info.setWordWrap(True)
        nav_info.setStyleSheet('QLabel { color: #666; font-size: 12pt; }')
        left_panel.addWidget(nav_info)

        # 3. Operation mode
        lbl3 = QLabel('3. Choose operation mode:')
        lbl3.setStyleSheet('QLabel { color: #444; font-size: 11pt; margin-top: 20px; }')
        left_panel.addWidget(lbl3)

        mode_desc = QLabel('• COPY: images are duplicated to target folder\n'
                           '• MOVE: images are moved (deleted from current folder)')
        mode_desc.setWordWrap(True)
        mode_desc.setStyleSheet('QLabel { color: #555; font-size: 11pt; }')
        left_panel.addWidget(mode_desc)

        self.mode_button = QPushButton('Mode: COPY')
        self.mode_button.setCheckable(True)
        self.mode_button.setFocusPolicy(Qt.NoFocus)
        self.mode_button.setMinimumHeight(48)
        self.mode_button.clicked.connect(self.toggle_mode)
        left_panel.addWidget(self.mode_button)

        # 4. Target folders configuration
        lbl4 = QLabel('4. Configure target folders (press key to sort to folder):')
        lbl4.setStyleSheet('QLabel { font-weight: bold; color: #333; font-size: 12pt; margin-top: 25px; }')
        left_panel.addWidget(lbl4)

        sub_header = QLabel('Check Edit icon to rename · Only folders with names will be created')
        sub_header.setWordWrap(True)
        sub_header.setStyleSheet('QLabel { color: #555; font-size: 11pt; }')
        left_panel.addWidget(sub_header)

        # Load existing subfolders button
        self.load_folders_btn = QPushButton('Load Existing Subfolders')
        self.load_folders_btn.setFocusPolicy(Qt.NoFocus)
        self.load_folders_btn.setMinimumHeight(36)
        self.load_folders_btn.setStyleSheet("""
            QPushButton { border: 1px solid #999; border-radius: 6px; padding: 6px; background-color: #e8f5e9; }
            QPushButton:hover { background-color: #c8e6c9; }
        """)
        self.load_folders_btn.clicked.connect(self.load_existing_subfolders)
        left_panel.addWidget(self.load_folders_btn)

        # 10 folder inputs
        self.folder_inputs = []
        self.folder_enabled = []
        default_names = ['family', 'me', '', '', '', '', '', '', '', '']

        for i in range(10):
            row = QHBoxLayout()

            key_lbl = QLabel(str((i + 1) % 10))
            key_lbl.setFixedWidth(30)
            key_lbl.setAlignment(Qt.AlignCenter)
            key_lbl.setStyleSheet('QLabel { font-weight: bold; font-size: 12pt; }')
            row.addWidget(key_lbl)

            edit_btn = QPushButton('Edit')
            edit_btn.setCheckable(True)
            edit_btn.setFixedWidth(40)
            edit_btn.setToolTip('Enable editing of folder name')
            edit_btn.setFocusPolicy(Qt.NoFocus)
            row.addWidget(edit_btn)

            edit = QLineEdit(default_names[i])
            edit.setEnabled(False)
            edit.setMinimumWidth(180)
            row.addWidget(edit)

            edit_btn.toggled.connect(edit.setEnabled)

            self.folder_inputs.append(edit)
            self.folder_enabled.append(edit_btn)

            left_panel.addLayout(row)

        # Create Folders button at the very bottom
        self.create_folders_btn = QPushButton('Create Folders')
        self.create_folders_btn.setFocusPolicy(Qt.NoFocus)
        self.create_folders_btn.setMinimumHeight(44)
        self.create_folders_btn.setStyleSheet("""
            QPushButton {
                border: 2px solid #43a047;
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
                background-color: #e8f5e9;
                color: #2e7d32;
            }
            QPushButton:hover { background-color: #c8e6c9; }
        """)
        self.create_folders_btn.clicked.connect(self.create_folders)
        left_panel.addWidget(self.create_folders_btn)

        left_panel.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        left_container = QWidget()
        left_container.setLayout(left_panel)
        left_container.setFixedWidth(340)
        left_container.setStyleSheet('QWidget { background-color: #f8f8f8; }')
        root_layout.addWidget(left_container)

        # RIGHT PANEL (previews)
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

    def load_existing_subfolders(self):
        if not self.current_folder:
            QMessageBox.information(self, 'No Folder', 'Please open a folder first.')
            return

        subfolders = []
        try:
            for entry in os.listdir(self.current_folder):
                full_path = os.path.join(self.current_folder, entry)
                if os.path.isdir(full_path) and not entry.startswith('.'):
                    subfolders.append(entry)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not read subfolders:\n{e}')
            return

        if not subfolders:
            QMessageBox.information(self, 'No Subfolders', 'No subfolders found in the selected folder.')
            return

        # Sort alphabetically and fill available slots
        subfolders.sort(key=str.lower)
        for i, name in enumerate(subfolders[:10]):
            self.folder_inputs[i].setText(name)
            self.folder_enabled[i].setChecked(True)  # Enable editing automatically

        QMessageBox.information(
            self, 'Subfolders Loaded',
            f'Found and loaded {len(subfolders[:10])} existing subfolder(s) alphabetically.'
        )

    def create_folders(self):
        if not self.current_folder:
            return

        created = 0
        exists = 0

        for edit in self.folder_inputs:
            name = edit.text().strip()
            if not name:
                continue
            path = os.path.join(self.current_folder, name)
            if os.path.exists(path):
                exists += 1
            else:
                os.makedirs(path, exist_ok=True)
                created += 1

        if created > 0:
            msg = f'{created} folder(s) created.'
            if exists > 0:
                msg += f'\n{exists} already existed.'
            QMessageBox.information(self, 'Done', msg)
        elif exists > 0:
            QMessageBox.information(self, 'Already Exist', 'All specified folders already exist.')
        else:
            QMessageBox.information(self, 'No Names', 'No folder names provided.')

    def toggle_mode(self):
        self.copy_mode = not self.copy_mode
        self.mode_button.setText('Mode: COPY' if self.copy_mode else 'Mode: MOVE')
        self.update_mode_button_style()

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

    def handle_sort(self, folder_idx):
        if folder_idx >= len(self.folder_inputs):
            return

        src_path = os.path.join(self.current_folder, self.images[self.current_index])
        target_name = self.folder_inputs[folder_idx].text().strip()
        if not target_name:
            QMessageBox.warning(self, 'Empty Name', 'Folder name is empty. Set a name first.')
            return

        target_folder = os.path.join(self.current_folder, target_name)
        os.makedirs(target_folder, exist_ok=True)
        dst_path = os.path.join(target_folder, os.path.basename(src_path))

        if os.path.exists(dst_path):
            QMessageBox.warning(self, 'File Exists',
                f'"{os.path.basename(src_path)}" already exists in "{target_name}".\nSkipped.')
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