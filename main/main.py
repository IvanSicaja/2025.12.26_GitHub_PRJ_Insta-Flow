import sys
import os
import shutil
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QFileDialog, QHBoxLayout, QVBoxLayout, QLineEdit,
    QSlider, QMessageBox
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')


class ImageSorterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Image Sorting Preview App')
        self.resize(1200, 800)

        self.current_folder = None
        self.images = []
        self.current_index = 0
        self.copy_mode = True  # True = Copy, False = Move

        self._build_ui()

    def _build_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        root_layout = QHBoxLayout(main_widget)

        # LEFT PANEL (controls)
        left_panel = QVBoxLayout()
        left_panel.setAlignment(Qt.AlignTop)

        self.open_btn = QPushButton('Open Folder')
        self.open_btn.setFocusPolicy(Qt.NoFocus)
        self.open_btn.clicked.connect(self.open_folder)
        left_panel.addWidget(self.open_btn)

        # Mode toggle (Move / Copy)
        self.mode_button = QPushButton('Mode: COPY')
        self.mode_button.setCheckable(True)
        self.mode_button.setFocusPolicy(Qt.NoFocus)
        self.mode_button.clicked.connect(self.toggle_mode)
        left_panel.addWidget(self.mode_button)

        info_label = QLabel('Press number key to send image to folder')
        info_label.setWordWrap(True)
        left_panel.addWidget(info_label)

        # Folder name inputs with enable checkbox
        self.folder_inputs = []
        self.folder_enabled = []
        for i in range(3):
            row = QHBoxLayout()

            key_label = QLabel(str(i + 1))
            key_label.setFixedWidth(20)
            row.addWidget(key_label)

            checkbox = QPushButton('✎')
            checkbox.setCheckable(True)
            checkbox.setFixedWidth(30)
            checkbox.setToolTip('Enable custom name')
            checkbox.setFocusPolicy(Qt.NoFocus)
            row.addWidget(checkbox)

            edit = QLineEdit(f'folder {i + 1}')
            edit.setEnabled(False)
            row.addWidget(edit)

            checkbox.toggled.connect(edit.setEnabled)

            self.folder_inputs.append(edit)
            self.folder_enabled.append(checkbox)
            left_panel.addLayout(row)

        self.create_folders_btn = QPushButton('Create Folders')
        self.create_folders_btn.setFocusPolicy(Qt.NoFocus)
        self.create_folders_btn.clicked.connect(self.create_folders)
        left_panel.addWidget(self.create_folders_btn)

        left_container = QWidget()
        left_container.setLayout(left_panel)
        left_container.setFixedWidth(160)
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
            lbl.setStyleSheet('background-color: #444;')
            self.secondary_labels.append(lbl)
            self.secondary_layout.addWidget(lbl)

        right_panel.addLayout(self.secondary_layout, 2)

        right_container = QWidget()
        right_container.setLayout(right_panel)
        root_layout.addWidget(right_container, 1)

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Image Folder')
        if not folder:
            return

        self.current_folder = folder
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

        for edit in self.folder_inputs:
            path = os.path.join(self.current_folder, edit.text())
            os.makedirs(path, exist_ok=True)

        QMessageBox.information(self, 'Folders Created', 'Target folders are ready.')

    def toggle_mode(self):
        self.copy_mode = not self.copy_mode
        if self.copy_mode:
            self.mode_button.setText('Mode: COPY')
        else:
            self.mode_button.setText('Mode: MOVE')

    def update_previews(self):
        if not self.images:
            return

        # Main image
        img_path = os.path.join(self.current_folder, self.images[self.current_index])
        pix = QPixmap(img_path)
        self.main_image_label.setPixmap(pix.scaled(
            self.main_image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

        # Secondary images
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
            return

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

        if Qt.Key_1 <= key <= Qt.Key_3:
            folder_idx = key - Qt.Key_1
            self.handle_sort(folder_idx)
            event.accept()

    def handle_sort(self, folder_idx):
        if folder_idx >= len(self.folder_inputs):
            return

        src_path = os.path.join(self.current_folder, self.images[self.current_index])
        target_folder = os.path.join(self.current_folder, self.folder_inputs[folder_idx].text())
        os.makedirs(target_folder, exist_ok=True)

        dst_path = os.path.join(target_folder, os.path.basename(src_path))

        try:
            if self.copy_mode:
                shutil.copy2(src_path, dst_path)
            else:
                shutil.move(src_path, dst_path)
                del self.images[self.current_index]
                self.current_index = min(self.current_index, len(self.images) - 1)
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))
            return

        self.update_previews()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageSorterApp()
    window.show()
    sys.exit(app.exec_())
