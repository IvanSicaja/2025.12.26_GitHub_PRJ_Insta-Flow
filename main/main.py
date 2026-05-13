import sys
import os
import shutil
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QFileDialog, QHBoxLayout, QVBoxLayout, QLineEdit,
    QMessageBox, QSpacerItem, QSizePolicy, QScrollArea, QCheckBox
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
        self.folder_keys = []  # parallel to folder_inputs: custom key strings per row
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
        left_panel.setSpacing(5)
        left_panel.setContentsMargins(12, 12, 12, 12)

        # 1. Select folder
        lbl1 = QLabel('1. Select the folder containing images to sort:')
        lbl1.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        lbl1.setWordWrap(True)
        left_panel.addWidget(lbl1)

        self.open_btn = QPushButton('Open Folder')
        self.open_btn.setFocusPolicy(Qt.NoFocus)
        self.open_btn.setFixedHeight(32)
        self.open_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; font-weight: bold; padding: 4px;
                border: 2px solid #aaa; border-radius: 6px;
            }
            QPushButton:hover { background-color: #f8f8f8; }
        """)
        self.open_btn.clicked.connect(self.open_folder)
        left_panel.addWidget(self.open_btn)

        # 2. Navigation instructions
        lbl_nav = QLabel('2. Navigate preview images with ← → arrow keys')
        lbl_nav.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        left_panel.addWidget(lbl_nav)

        # 3. Mode selection
        lbl_mode = QLabel('3. Choose operation mode:')
        lbl_mode.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        left_panel.addWidget(lbl_mode)

        mode_desc = QLabel('COPY: duplicates image to target folder\nMOVE: removes image from source folder')
        mode_desc.setStyleSheet('QLabel { color: #666; font-size: 9pt; margin-left: 6px; }')
        mode_desc.setWordWrap(False)
        left_panel.addWidget(mode_desc)

        self.mode_button = QPushButton('Mode: COPY')
        self.mode_button.setCheckable(True)
        self.mode_button.setFocusPolicy(Qt.NoFocus)
        self.mode_button.setFixedHeight(32)
        self.mode_button.clicked.connect(self.toggle_mode)
        left_panel.addWidget(self.mode_button)

        # 4. Target folders configuration
        lbl_folders = QLabel('4. Configure target folders (press key 1–0 to sort):')
        lbl_folders.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        lbl_folders.setWordWrap(True)
        left_panel.addWidget(lbl_folders)

        # --- Sort destination folder ---
        lbl_target_header = QLabel('Sort destination folder:')
        lbl_target_header.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        left_panel.addWidget(lbl_target_header)

        lbl_target_desc = QLabel('Use source folder (Step 1) or pick a different target.')
        lbl_target_desc.setStyleSheet('QLabel { color: #666; font-size: 9pt; margin-left: 6px; }')
        lbl_target_desc.setWordWrap(True)
        left_panel.addWidget(lbl_target_desc)

        # Checkbox row
        self.use_source_checkbox = QCheckBox('Use same folder as Step 1 (source folder)')
        self.use_source_checkbox.setChecked(True)
        self.use_source_checkbox.setFocusPolicy(Qt.NoFocus)
        self.use_source_checkbox.setStyleSheet("""
            QCheckBox {
                color: #111;
                font-weight: bold;
                font-size: 9.5pt;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        self.use_source_checkbox.stateChanged.connect(self.on_use_source_toggled)
        left_panel.addWidget(self.use_source_checkbox)

        # Path row: text field + "..." browse button (always visible)
        target_row = QHBoxLayout()

        self.target_folder_display = QLineEdit()
        self.target_folder_display.setPlaceholderText('No folder selected yet (open a folder in Step 1 or type a path)')
        self.target_folder_display.setReadOnly(True)   # starts locked (checkbox is checked)
        self.target_folder_display.setStyleSheet("""
            QLineEdit { 
                padding: 5px; 
                border-radius: 6px; 
                border: 2px solid #ccc;
                background-color: #efefef;
                color: #555;
                font-size: 9pt;
            }
        """)
        self.target_folder_display.textEdited.connect(self.on_target_path_edited)
        target_row.addWidget(self.target_folder_display)

        self.select_target_btn = QPushButton('…')
        self.select_target_btn.setFocusPolicy(Qt.NoFocus)
        self.select_target_btn.setFixedWidth(32)
        self.select_target_btn.setMinimumHeight(32)
        self.select_target_btn.setToolTip('Browse for target folder')
        self.select_target_btn.setEnabled(False)   # disabled while checkbox is checked
        self.select_target_btn.setStyleSheet("""
            QPushButton { 
                background-color: white;
                font-weight: bold;
                font-size: 11pt;
                border: 2px solid #aaa; 
                border-radius: 8px;
                padding: 2px;
            }
            QPushButton:hover:enabled { background-color: #f0f0f0; }
            QPushButton:disabled { background-color: #e8e8e8; color: #bbb; border-color: #ccc; }
        """)
        self.select_target_btn.clicked.connect(self.select_target_folder)
        target_row.addWidget(self.select_target_btn)

        left_panel.addLayout(target_row)
        # --- END destination folder block ---

        # Sub-header and load button
        sub_header = QLabel('⌨  Edit shortcut key\n✎  Edit folder name')
        sub_header.setStyleSheet('QLabel { color: #555; font-size: 9pt; margin-left: 6px; }')
        sub_header.setWordWrap(False)
        left_panel.addWidget(sub_header)

        self.load_folders_btn = QPushButton('Load Existing Subfolders (A-Z)')
        self.load_folders_btn.setFocusPolicy(Qt.NoFocus)
        self.load_folders_btn.setFixedHeight(32)
        self.load_folders_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; font-weight: bold; padding: 4px;
                border: 2px solid #aaa; border-radius: 6px;
            }
            QPushButton:hover { background-color: #f8f8f8; }
        """)
        self.load_folders_btn.clicked.connect(self.load_existing_subfolders)
        left_panel.addWidget(self.load_folders_btn)

        # Folder key-pair rows (dynamic)
        self.folder_inputs = []
        self.folder_enabled = []
        self.folder_keys = []
        self.folder_del_btns = []
        self.folder_rows_widgets = []  # list of QWidget (each full row)

        # Container widget whose layout holds the rows
        self.folder_rows_container = QWidget()
        self.folder_rows_layout = QVBoxLayout(self.folder_rows_container)
        self.folder_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.folder_rows_layout.setSpacing(4)
        left_panel.addWidget(self.folder_rows_container)

        default_names = ['Family Milestones', 'My Milestones', '', '', '', '', '']
        for i in range(7):
            self._add_folder_row(default_names[i])

        # "+" button to add more rows
        self.add_row_btn = QPushButton('＋  Add another key–folder pair')
        self.add_row_btn.setFocusPolicy(Qt.NoFocus)
        self.add_row_btn.setFixedHeight(30)
        self.add_row_btn.setStyleSheet("""
            QPushButton {
                background-color: white; font-size: 9.5pt;
                border: 2px dashed #aaa; border-radius: 6px;
                padding: 2px; color: #555;
            }
            QPushButton:hover { background-color: #f0f0f0; border-color: #888; }
        """)
        self.add_row_btn.clicked.connect(self._on_add_row)
        left_panel.addWidget(self.add_row_btn)

        # Create Folders button
        self.create_folders_btn = QPushButton('Create Folders')
        self.create_folders_btn.setFocusPolicy(Qt.NoFocus)
        self.create_folders_btn.setFixedHeight(32)
        self.create_folders_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; font-weight: bold; padding: 4px;
                border: 2px solid #aaa; border-radius: 6px;
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
        right_panel.setContentsMargins(20, 10, 20, 10)
        right_panel.setSpacing(6)

        # Source folder info bar (top of preview area)
        source_bar = QWidget()
        source_bar.setStyleSheet('background-color: #2b2b2b; border-radius: 0px;')
        source_bar.setFixedHeight(28)
        source_bar_layout = QHBoxLayout(source_bar)
        source_bar_layout.setContentsMargins(10, 0, 10, 0)
        source_bar_layout.setSpacing(6)

        source_bar_icon = QLabel('📂')
        source_bar_icon.setStyleSheet('color: #aaa; font-size: 10pt; background: transparent;')
        source_bar_layout.addWidget(source_bar_icon)

        source_bar_prefix = QLabel('Source:')
        source_bar_prefix.setStyleSheet('color: #888; font-size: 9pt; font-weight: bold; background: transparent;')
        source_bar_layout.addWidget(source_bar_prefix)

        self.source_folder_bar_label = QLabel('No folder selected — use Step 1 to open a folder')
        self.source_folder_bar_label.setStyleSheet('color: #ccc; font-size: 9pt; background: transparent;')
        self.source_folder_bar_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        source_bar_layout.addWidget(self.source_folder_bar_label, 1)

        right_panel.addWidget(source_bar)

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

        # Two-line info bar at the bottom (current image name + last operation)
        BAR_STYLE = 'background-color: {bg}; border-radius: 0px;'
        TEXT_CSS  = 'color: #ccc; font-size: 9pt; background: transparent;'

        # --- Bar 1: currently displayed image name ---
        cur_bar = QWidget()
        cur_bar.setStyleSheet(BAR_STYLE.format(bg='#1e1e1e'))
        cur_bar.setFixedHeight(26)
        cur_bar_layout = QHBoxLayout(cur_bar)
        cur_bar_layout.setContentsMargins(10, 0, 10, 0)
        cur_bar_layout.setSpacing(0)

        PREFIX_W = 58   # fixed width for both prefix labels — ensures filename columns align

        cur_bar_prefix = QLabel('Preview:')
        cur_bar_prefix.setFixedWidth(PREFIX_W)
        cur_bar_prefix.setStyleSheet('color: #666; font-size: 9pt; background: transparent;')
        cur_bar_prefix.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        cur_bar_layout.addWidget(cur_bar_prefix)

        self.current_image_name_label = QLabel('—')
        self.current_image_name_label.setStyleSheet(TEXT_CSS)
        self.current_image_name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        cur_bar_layout.addWidget(self.current_image_name_label, 1)

        right_panel.addWidget(cur_bar)

        # --- Bar 2: last operation result ---
        status_bar = QWidget()
        status_bar.setStyleSheet(BAR_STYLE.format(bg='#2b2b2b'))
        status_bar.setFixedHeight(26)
        status_bar_layout = QHBoxLayout(status_bar)
        status_bar_layout.setContentsMargins(10, 0, 10, 0)
        status_bar_layout.setSpacing(0)

        # Prefix label — same fixed width as bar above so filenames align perfectly
        op_prefix = QLabel('Last op:')
        op_prefix.setFixedWidth(PREFIX_W)
        op_prefix.setStyleSheet('color: #666; font-size: 9pt; background: transparent;')
        op_prefix.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        status_bar_layout.addWidget(op_prefix)

        # Filename + arrow + folder (left-aligned, stretches)
        self.operation_status_label = QLabel('Ready — press a number key (1–0) to sort the current image')
        self.operation_status_label.setStyleSheet(TEXT_CSS)
        self.operation_status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        status_bar_layout.addWidget(self.operation_status_label, 1)

        # Operation badge (right-aligned, fixed)
        self.operation_badge_label = QLabel('')
        self.operation_badge_label.setFixedWidth(54)
        self.operation_badge_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.operation_badge_label.setStyleSheet('font-size: 9pt; font-weight: bold; background: transparent; color: transparent;')
        status_bar_layout.addWidget(self.operation_badge_label)

        right_panel.addWidget(status_bar)

        right_container = QWidget()
        right_container.setLayout(right_panel)
        right_container.setFocusPolicy(Qt.StrongFocus)
        right_container.mousePressEvent = lambda e: right_container.setFocus()
        root_layout.addWidget(right_container, 1)

    # --- Target folder methods ---

    def on_use_source_toggled(self, state):
        """Called when the 'Use same folder as Step 1' checkbox changes."""
        checked = (state == Qt.Checked)
        if checked:
            # Lock to source folder
            self.target_base_folder = None
            self.settings.remove('last_target_folder')
            self.target_folder_display.setReadOnly(True)
            self.target_folder_display.setStyleSheet("""
                QLineEdit { 
                    padding: 5px; border-radius: 6px;
                    border: 2px solid #ccc; background-color: #efefef;
                    color: #555; font-size: 9pt;
                }
            """)
            self.select_target_btn.setEnabled(False)
            # Show the current source folder path (if one is open)
            if self.current_folder:
                self.target_folder_display.setText(self.current_folder)
            else:
                self.target_folder_display.clear()
        else:
            # Unlock for custom input
            self.target_folder_display.setReadOnly(False)
            self.target_folder_display.setStyleSheet("""
                QLineEdit { 
                    padding: 5px; border-radius: 6px;
                    border: 2px solid #aaa; background-color: #fff;
                    color: #222; font-size: 9pt;
                }
            """)
            self.select_target_btn.setEnabled(True)
            self.target_folder_display.setPlaceholderText('Type a path or click … to browse')
        self.centralWidget().setFocus()

    def on_target_path_edited(self, text):
        """Called when the user manually types a path into the target folder field."""
        path = text.strip()
        if os.path.isdir(path):
            self.target_base_folder = path
            self.settings.setValue('last_target_folder', path)
        else:
            self.target_base_folder = None

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
        self.centralWidget().setFocus()

    def clear_target_folder(self):
        self.target_base_folder = None
        self.settings.remove('last_target_folder')
        self.target_folder_display.clear()
        self.target_folder_display.setToolTip('')
        self.centralWidget().setFocus()

    def get_effective_target_folder(self):
        """Returns the custom target folder if set, otherwise falls back to the source folder."""
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
        dst_folder_path = os.path.join(target_base, subfolder_name)
        new_entry = f'[{timestamp}]  {operation}  {image_src_path}  →  {dst_folder_path}'

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

    # --- Dynamic folder-row helpers ---

    # Key sequence: 1-9, 0, then keyboard rows Q→P, A→L, Y→M (physical left-to-right)
    KEY_SEQUENCE = (
        [str(i) for i in range(1, 10)] + ['0'] +
        list('qwertzuiop') +
        list('asdfghjkl') +
        list('yxcvbnm')
    )

    def _get_key_label_for(self, index):
        if index < len(self.KEY_SEQUENCE):
            return self.KEY_SEQUENCE[index]
        return '?'

    def _add_folder_row(self, default_name=''):
        idx = len(self.folder_inputs)
        default_key = self._get_key_label_for(idx)

        row_widget = QWidget()
        row_widget.setFixedHeight(36)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)

        # --- Key display/edit area ---
        # Shows the assigned key; clicking ⌨ makes it editable
        key_edit = QLineEdit(default_key)
        key_edit.setFixedWidth(28)
        key_edit.setFixedHeight(30)
        key_edit.setEnabled(False)
        key_edit.setAlignment(Qt.AlignCenter)
        key_edit.setMaxLength(2)
        key_edit.setStyleSheet("""
            QLineEdit {
                font-weight: bold; font-size: 10pt; color: #333;
                border: 2px solid transparent; border-radius: 5px;
                background: transparent; padding: 0px;
            }
            QLineEdit:enabled {
                background: white; border: 2px solid #f0a500;
                color: #c0700a;
            }
        """)
        row.addWidget(key_edit)

        # Shared style for all small icon buttons in a row
        ICON_BTN = """
            QPushButton {{
                border-radius: 5px; border: 2px solid #aaa;
                background: white; padding: 2px; font-size: 9pt; color: #444;
                width: {w}px; height: 28px;
            }}
            QPushButton:checked {{ background-color: #e8e8e8; border-color: #888; }}
            QPushButton:hover   {{ background-color: #f0f0f0; }}
        """

        # ⌨ button — unlock key editing
        key_btn = QPushButton('⌨')
        key_btn.setCheckable(True)
        key_btn.setFixedWidth(26)
        key_btn.setFixedHeight(28)
        key_btn.setFocusPolicy(Qt.NoFocus)
        key_btn.setToolTip('Edit the shortcut key for this folder')
        key_btn.setStyleSheet(ICON_BTN.format(w=26) +
            "QPushButton:checked { background-color: #fff3cd; border-color: #f0a500; color: #c0700a; }")
        key_btn.toggled.connect(key_edit.setEnabled)
        key_btn.toggled.connect(lambda checked: self.on_pencil_clicked() if not checked else None)
        row.addWidget(key_btn)

        # ✎ button — unlock folder name editing
        pencil_btn = QPushButton('✎')
        pencil_btn.setCheckable(True)
        pencil_btn.setFixedWidth(26)
        pencil_btn.setFixedHeight(28)
        pencil_btn.setStyleSheet(ICON_BTN.format(w=26))
        pencil_btn.setToolTip('Enable editing of folder name')
        pencil_btn.setFocusPolicy(Qt.NoFocus)
        pencil_btn.clicked.connect(self.on_pencil_clicked)
        row.addWidget(pencil_btn)

        # Folder name edit
        edit = QLineEdit(default_name)
        edit.setEnabled(False)
        edit.setFixedHeight(28)
        edit.setStyleSheet('QLineEdit { padding: 4px; border-radius: 5px; font-size: 9pt; }')
        row.addWidget(edit)

        pencil_btn.toggled.connect(edit.setEnabled)

        # ▲ up button
        up_btn = QPushButton('▲')
        up_btn.setFixedWidth(20)
        up_btn.setFixedHeight(28)
        up_btn.setFocusPolicy(Qt.NoFocus)
        up_btn.setToolTip('Move up')
        up_btn.setStyleSheet(ICON_BTN.format(w=20))
        up_btn.clicked.connect(lambda _, w=row_widget: self._move_row_up(w))
        row.addWidget(up_btn)

        # ▼ down button
        dn_btn = QPushButton('▼')
        dn_btn.setFixedWidth(20)
        dn_btn.setFixedHeight(28)
        dn_btn.setFocusPolicy(Qt.NoFocus)
        dn_btn.setToolTip('Move down')
        dn_btn.setStyleSheet(ICON_BTN.format(w=20))
        dn_btn.clicked.connect(lambda _, w=row_widget: self._move_row_dn(w))
        row.addWidget(dn_btn)

        # × delete button
        del_btn = QPushButton('×')
        del_btn.setFixedWidth(22)
        del_btn.setFixedHeight(28)
        del_btn.setFocusPolicy(Qt.NoFocus)
        del_btn.setToolTip('Remove this key–folder pair')
        del_btn.setStyleSheet(ICON_BTN.format(w=22) +
            "QPushButton:hover { background-color: #ffe0e0; border-color: #e88; color: #c00; }")
        del_btn.clicked.connect(lambda _, w=row_widget: self._delete_row(w))
        row.addWidget(del_btn)

        self.folder_inputs.append(edit)
        self.folder_enabled.append(pencil_btn)
        self.folder_keys.append(key_edit)
        self.folder_del_btns.append(del_btn)
        self.folder_rows_widgets.append(row_widget)
        self.folder_rows_layout.addWidget(row_widget)

    def _get_effective_key(self, index):
        """Return the active key string for a row (custom if set, else default)."""
        if index < len(self.folder_keys):
            val = self.folder_keys[index].text().strip()
            if val:
                return val.lower()
        return self._get_key_label_for(index)

    def _refresh_key_labels(self):
        """After reorder, update default key labels only for rows that haven't been customised."""
        for i, row_widget in enumerate(self.folder_rows_widgets):
            key_edit_widget = row_widget.layout().itemAt(0).widget()
            if isinstance(key_edit_widget, QLineEdit):
                # Only reset if not currently being edited (key_btn not checked)
                key_btn_widget = row_widget.layout().itemAt(1).widget()
                if isinstance(key_btn_widget, QPushButton) and not key_btn_widget.isChecked():
                    # Only overwrite if it still holds the old default value
                    old_default = self._get_key_label_for(i)
                    # Check if the value matches any default in KEY_SEQUENCE (i.e. hasn't been customised)
                    current_val = key_edit_widget.text().strip()
                    if current_val in self.KEY_SEQUENCE:
                        key_edit_widget.setText(old_default)

    def _delete_row(self, row_widget):
        if len(self.folder_rows_widgets) <= 1:
            return  # always keep at least one row
        idx = self.folder_rows_widgets.index(row_widget)
        self.folder_rows_layout.removeWidget(row_widget)
        row_widget.setParent(None)
        self.folder_rows_widgets.pop(idx)
        self.folder_inputs.pop(idx)
        self.folder_enabled.pop(idx)
        self.folder_keys.pop(idx)
        self.folder_del_btns.pop(idx)
        self._refresh_key_labels()
        self.centralWidget().setFocus()

    def _swap_rows(self, i, j):
        for lst in (self.folder_rows_widgets, self.folder_inputs,
                    self.folder_enabled, self.folder_keys, self.folder_del_btns):
            lst[i], lst[j] = lst[j], lst[i]
        for w in self.folder_rows_widgets:
            self.folder_rows_layout.removeWidget(w)
        for w in self.folder_rows_widgets:
            self.folder_rows_layout.addWidget(w)
        self._refresh_key_labels()
        self.centralWidget().setFocus()

    def _move_row_up(self, row_widget):
        idx = self.folder_rows_widgets.index(row_widget)
        if idx > 0:
            self._swap_rows(idx, idx - 1)

    def _move_row_dn(self, row_widget):
        idx = self.folder_rows_widgets.index(row_widget)
        if idx < len(self.folder_rows_widgets) - 1:
            self._swap_rows(idx, idx + 1)

    def _on_add_row(self):
        self._add_folder_row('')
        self._refresh_key_labels()
        self.centralWidget().setFocus()

    # --- END dynamic folder-row helpers ---

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
        # Update source folder info bar
        self.source_folder_bar_label.setText(folder)

        self.images = [
            f for f in sorted(os.listdir(folder))
            if f.lower().endswith(IMAGE_EXTENSIONS)
        ]
        if not self.images:
            QMessageBox.warning(self, 'No Images', 'Selected folder has no images.')
            return

        self.current_index = 0
        self.update_previews()
        # If "use source" checkbox is checked, keep the display in sync
        if self.use_source_checkbox.isChecked():
            self.target_folder_display.setText(folder)
        self.centralWidget().setFocus()

    def load_existing_subfolders(self):
        if not self.current_folder:
            QMessageBox.information(self, 'No Folder', 'Please open a folder first.')
            return

        scan_folder = self.get_effective_target_folder()
        if not scan_folder:
            QMessageBox.information(self, 'No Folder', 'Please open a folder first.')
            return

        try:
            items = os.listdir(scan_folder)
            subfolders = sorted(
                [f for f in items if os.path.isdir(os.path.join(scan_folder, f)) and not f.startswith('.')],
                key=str.lower
            )

            # Remove all existing rows
            for w in list(self.folder_rows_widgets):
                self.folder_rows_layout.removeWidget(w)
                w.setParent(None)
            self.folder_rows_widgets.clear()
            self.folder_inputs.clear()
            self.folder_enabled.clear()
            self.folder_keys.clear()
            self.folder_del_btns.clear()

            # Add exactly as many rows as subfolders found (minimum 1)
            count = max(len(subfolders), 1)
            for i in range(count):
                name = subfolders[i] if i < len(subfolders) else ''
                self._add_folder_row(name)
                if i < len(subfolders):
                    # Enable the edit field and pencil for pre-filled rows
                    self.folder_inputs[i].setEnabled(True)
                    self.folder_enabled[i].setChecked(True)

            self._refresh_key_labels()
            QMessageBox.information(
                self, 'Subfolders Loaded',
                f'Loaded {len(subfolders)} subfolder(s) — {count} key–folder pair(s) created.'
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
            self.current_image_name_label.setText('—')
            return

        current_name = self.images[self.current_index]
        self.current_image_name_label.setText(current_name)

        img_path = os.path.join(self.current_folder, current_name)
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
            return
        elif key == Qt.Key_Left:
            self.current_index = max(self.current_index - 1, 0)
            self.update_previews()
            event.accept()
            return

        # Don't trigger sort keys when a QLineEdit has focus
        if isinstance(self.focusWidget(), QLineEdit):
            super().keyPressEvent(event)
            return

        # Build pressed key string (single char, lowercase)
        key_char = None
        if Qt.Key_1 <= key <= Qt.Key_9:
            key_char = str(key - Qt.Key_0)
        elif key == Qt.Key_0:
            key_char = '0'
        elif Qt.Key_A <= key <= Qt.Key_Z:
            key_char = chr(key).lower()

        if key_char is not None:
            # Check each row for a matching effective key
            for idx in range(len(self.folder_inputs)):
                if self._get_effective_key(idx) == key_char:
                    self.handle_sort(idx)
                    event.accept()
                    return

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

        # Show operation result in the status bar (no popup)
        op = 'MOVED' if not self.copy_mode else 'COPIED'
        op_color = '#e67e22' if not self.copy_mode else '#27ae60'
        filename = os.path.basename(src_path)
        self.operation_status_label.setText(f'{filename}  →  {target_name}')
        self.operation_status_label.setStyleSheet('color: #ccc; font-size: 9pt; background: transparent;')
        self.operation_status_label.setTextFormat(Qt.PlainText)
        self.operation_badge_label.setText(op)
        self.operation_badge_label.setStyleSheet(
            f'font-size: 9pt; font-weight: bold; background: transparent; color: {op_color};'
        )

        self.update_previews()

        if not self.copy_mode and was_last_image:
            self.operation_status_label.setText('No more images to sort in the source folder.')
            self.operation_badge_label.setText('')

        self.centralWidget().setFocus()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageSorterApp()
    window.showMaximized()
    sys.exit(app.exec_())