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
        self.copy_mode = True  # True = Copy, False = Move
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
        left_panel.setSpacing(12)  # Reduced spacing for better fit

        # 1. Select folder
        lbl1 = QLabel('1. Select the folder containing images to sort:')
        lbl1.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        lbl1.setWordWrap(True)
        left_panel.addWidget(lbl1)

        self.open_btn = QPushButton('Open Folder')
        self.open_btn.setFocusPolicy(Qt.NoFocus)
        self.open_btn.setMinimumHeight(36)
        self.open_btn.setStyleSheet('QPushButton { background-color: white; font-weight: bold; padding: 6px; }')
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
        lbl_folders.setStyleSheet('QLabel { font-weight: bold; color: #333; font-size: 11pt; margin-top: 20px; }')
        left_panel.addWidget(lbl_folders)

        sub_header = QLabel('Check ✎ to edit name · Only folders with names will be created')
        sub_header.setStyleSheet('QLabel { color: #555; font-size: 10pt; }')
        sub_header.setWordWrap(True)
        left_panel.addWidget(sub_header)

        # Load existing subfolders button - white background, no rounding
        self.load_folders_btn = QPushButton('Load Existing Subfolders (A-Z)')
        self.load_folders_btn.setFocusPolicy(Qt.NoFocus)
        self.load_folders_btn.setMinimumHeight(36)
        self.load_folders_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; 
                font-weight: bold; 
                padding: 6px; 
                border: 1px solid #ccc;
            }
            QPushButton:hover { background-color: #f5f5f5; }
        """)
        self.load_folders_btn.clicked.connect(self.load_existing_subfolders)
        left_panel.addWidget(self.load_folders_btn)

        # 10 folder inputs
        self.folder_inputs = []
        self.folder_enabled = []
        default_names = ['family', 'me', '', '', '', '', '', '', '', '']

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
                    border-radius: 6px; 
                    border: 1px solid #aaa; 
                    padding: 4px;
                }
                QPushButton:checked { background-color: #e0e0e0; }
            """)
            checkbox.setToolTip('Enable editing of folder name')
            checkbox.setFocusPolicy(Qt.NoFocus)
            row.addWidget(checkbox)

            edit = QLineEdit(default_names[i])
            edit.setEnabled(False)
            edit.setStyleSheet('QLineEdit { padding: 6px; }')
            row.addWidget(edit)

            checkbox.toggled.connect(edit.setEnabled)

            self.folder_inputs.append(edit)
            self.folder_enabled.append(checkbox)

            left_panel.addLayout(row)

        # Create Folders button - white, no rounding, at bottom
        self.create_folders_btn = QPushButton('Create Folders')
        self.create_folders_btn.setFocusPolicy(Qt.NoFocus)
        self.create_folders_btn.setMinimumHeight(40)
        self.create_folders_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; 
                font-weight: bold; 
                padding: 10px; 
                border: 1px solid #ccc;
                margin-top: 10px;
            }
            QPushButton:hover { background-color: #f5f5f5; }
        """)
        self.create_folders_btn.clicked.connect(self.create_folders)
        left_panel.addWidget(self.create_folders_btn)

        left_panel.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        left_container = QWidget()
        left_container.setLayout(left_panel)
        left_container.setFixedWidth(340)
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

    def load_existing_subfolders(self):
        if not self.current_folder:
            QMessageBox.information(self, 'No Folder', 'Please open a folder first.')
            return

        try:
            items = os.listdir(self.current_folder)
            subfolders = [item for item in items if os.path.isdir(os.path.join(self.current_folder, item))]
            subfolders = sorted([f for f in subfolders if not f.startswith('.')], key=str.lower)

            # Clear all inputs
            for edit, cb in zip(self.folder_inputs, self.folder_enabled):
                edit.setText('')
                edit.setEnabled(False)
                cb.setChecked(False)

            # Fill up to 10
            for i, name in enumerate(subfolders[:10]):
                self.folder_inputs[i].setText(name)
                self.folder_inputs[i].setEnabled(True)
                self.folder_enabled[i].setChecked(True)

            QMessageBox.information(
                self, 'Subfolders Loaded',
                f'Loaded {min(len(subfolders), 10)} existing subfolder(s) alphabetically.\n'
                f'Total found: {len(subfolders)}'
            )
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not load subfolders:\n{str(e)}')

    def create_folders(self):
        if not self.current_folder:
            return

        created_count = 0
        already_exists_count = 0

        for edit in self.folder_inputs:
            name = edit.text().strip()
            if not name:
                continue
            path = os.path.join(self.current_folder, name)
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

    def toggle_mode(self):
        self.copy_mode = not self.copy_mode
        if self.copy_mode:
            self.mode_button.setText('Mode: COPY')
        else:
            self.mode_button.setText('Mode: MOVE')
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
            return
        elif key == Qt.Key_Left:
            self.current_index = max(self.current_index - 1, 0)
            self.update_previews()
            event.accept()
            return

        if Qt.Key_1 <= key <= Qt.Key_9:
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