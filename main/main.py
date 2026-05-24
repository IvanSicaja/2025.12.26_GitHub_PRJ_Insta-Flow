import sys
import os
import shutil
import threading
from collections import OrderedDict
from datetime import datetime

# Third-party — install with: pip install PyQt6 rawpy numpy
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QFileDialog, QHBoxLayout, QVBoxLayout, QGridLayout, QLineEdit,
    QMessageBox, QSpacerItem, QSizePolicy, QScrollArea, QCheckBox
)
from PyQt6.QtGui import QPixmap, QIcon, QImage
from PyQt6.QtCore import Qt, QSettings, QTimer
import rawpy          # pip install rawpy
import numpy as np    # pip install numpy

# Extensions that require rawpy to decode (Qt cannot render these natively)
RAW_EXTENSIONS = {
    '.arw', '.cr2', '.cr3', '.nef', '.nrw', '.orf', '.rw2',
    '.pef', '.srw', '.dng', '.raf', '.raw', '.3fr', '.iiq',
    '.erf', '.mrw', '.x3f',
}

IMAGE_EXTENSIONS = (
    # JPEG
    '.jpg', '.jpeg', '.jpe', '.jfif',
    # PNG
    '.png',
    # BMP / DIB
    '.bmp', '.dib',
    # GIF
    '.gif',
    # TIFF
    '.tif', '.tiff',
    # WebP
    '.webp',
    # HEIF / HEIC  (iOS / modern cameras)
    '.heif', '.heic',
    # RAW formats
    '.raw', '.arw',   # Sony
    '.cr2', '.cr3',   # Canon
    '.nef', '.nrw',   # Nikon
    '.orf',           # Olympus
    '.rw2',           # Panasonic
    '.pef',           # Pentax
    '.srw',           # Samsung
    '.dng',           # Adobe DNG (universal RAW)
    '.raf',           # Fujifilm
    '.3fr',           # Hasselblad
    '.iiq',           # Phase One
    '.erf',           # Epson
    '.mrw',           # Konica-Minolta
    '.x3f',           # Sigma
    # Other common formats
    '.ico',
    '.tga',
    '.psd',           # Photoshop (flattened)
    '.xcf',           # GIMP
    '.ppm', '.pgm', '.pbm', '.pnm',   # Netpbm
    '.svg',           # vector (Qt can render these)
    '.svgz',
)
LOG_FILENAME = 'instaflow_log.txt'
MAX_LOG_ENTRIES = 10
CACHE_SIZE = 20        # max pixmaps kept in memory
PRELOAD_AHEAD  = 6    # how many images to preload ahead of current index
PRELOAD_BEHIND = 3    # how many images to keep behind current index


def _suppress_fd2():
    """Context manager that redirects file-descriptor 2 (C-level stderr) to /dev/null."""
    import contextlib, os as _os

    @contextlib.contextmanager
    def _cm():
        devnull = _os.open(_os.devnull, _os.O_WRONLY)
        old_fd = _os.dup(2)
        _os.dup2(devnull, 2)
        _os.close(devnull)
        try:
            yield
        finally:
            _os.dup2(old_fd, 2)
            _os.close(old_fd)

    return _cm()


def load_pixmap(path: str) -> QPixmap:
    """
    Load any image file as a QPixmap.
    RAW formats decoded with rawpy; everything else via QPixmap directly.
    """
    ext = os.path.splitext(path)[1].lower()

    if ext in RAW_EXTENSIONS:
        try:
            with _suppress_fd2():
                with rawpy.imread(path) as raw:
                    rgb = raw.postprocess(
                        use_camera_wb=True,
                        half_size=True,
                        no_auto_bright=False,
                        output_bps=8,
                    )
            h, w, ch = rgb.shape
            buf = bytes(rgb)
            bpl = ch * w
            qimg = QImage(buf, w, h, bpl, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qimg.copy())
            if pix.isNull():
                print(f'[InstaFlow] Warning: could not render {os.path.basename(path)}')
            return pix
        except Exception as e:
            print(f'[InstaFlow] Error loading {os.path.basename(path)}: {type(e).__name__}: {e}')
            return QPixmap()
    else:
        pix = QPixmap(path)
        if not pix.isNull():
            return pix
        return QPixmap()


class PixmapCache:
    """
    Background thread that preloads full-size QPixmaps for images around
    the current index.  All public methods are thread-safe.
    """

    def __init__(self):
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start_preload(self, folder: str, images: list[str], center_idx: int):
        """Stop any running preload and start a new one centred on center_idx."""
        self._stop_event.set()                    # signal old thread to stop
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)        # wait briefly

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker,
            args=(folder, images, center_idx),
            daemon=True,
        )
        self._thread.start()

    def _worker(self, folder: str, images: list[str], center_idx: int):
        """Load pixmaps in order of proximity to center_idx."""
        total = len(images)
        # Build priority order: current, then alternating ahead/behind
        order = [center_idx]
        for delta in range(1, max(PRELOAD_AHEAD, PRELOAD_BEHIND) + 1):
            if delta <= PRELOAD_AHEAD and center_idx + delta < total:
                order.append(center_idx + delta)
            if delta <= PRELOAD_BEHIND and center_idx - delta >= 0:
                order.append(center_idx - delta)

        for idx in order:
            if self._stop_event.is_set():
                return
            path = os.path.join(folder, images[idx])
            with self._lock:
                if path in self._cache:
                    self._cache.move_to_end(path)
                    continue
            # Load outside the lock so other threads aren't blocked
            pix = load_pixmap(path)
            if pix.isNull():
                continue
            with self._lock:
                self._cache[path] = pix
                self._cache.move_to_end(path)
                while len(self._cache) > CACHE_SIZE:
                    self._cache.popitem(last=False)

    def get(self, path: str) -> QPixmap | None:
        """Return cached pixmap or None if not yet loaded."""
        with self._lock:
            if path in self._cache:
                self._cache.move_to_end(path)
                return self._cache[path]
        return None

    def clear(self):
        """Discard all cached pixmaps and stop the worker."""
        self._stop_event.set()
        with self._lock:
            self._cache.clear()



class ImageSorterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('InstaFlow')
        self.setWindowIcon(QIcon(r'..\assets\media\icons\icon.ico'))
        self.resize(1500, 900)
        self.setMinimumSize(1400, 800)
        self.current_folder = None
        self.target_base_folder = None
        self.images = []
        self.current_index = 0
        self.copy_mode = True
        self.folder_keys = []
        self._pix_cache = PixmapCache()   # background preloader
        self._loaded_subfolder_names: set[str] = set()  # names as of last "Load Existing Subfolders"
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
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setStyleSheet('QScrollArea { background-color: #f8f8f8; border: none; }')

        left_content = QWidget()
        left_content.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        left_content.mousePressEvent = lambda e: self.centralWidget().setFocus()
        left_panel = QVBoxLayout(left_content)
        left_panel.setAlignment(Qt.AlignmentFlag.AlignTop)
        left_panel.setSpacing(5)
        left_panel.setContentsMargins(12, 12, 12, 12)

        # 1. Select folder
        lbl1 = QLabel('1. Select the folder containing images to sort:')
        lbl1.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        lbl1.setWordWrap(True)
        left_panel.addWidget(lbl1)

        self.open_btn = QPushButton('Open Folder')
        self.open_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        lbl_nav = QLabel('2. Navigate preview images with \u2190 \u2192 arrow keys')
        lbl_nav.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        left_panel.addWidget(lbl_nav)

        # 3. Mode selection
        lbl_mode = QLabel('3. Choose operation mode:')
        lbl_mode.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        left_panel.addWidget(lbl_mode)

        # FIX 1+2: indented to align with "Choose operation mode:" text start; bullet points
        mode_desc = QLabel(
            '\u2022  COPY:  duplicates image to target folder\n'
            '\u2022  MOVE: removes image from source folder'
        )
        mode_desc.setStyleSheet('QLabel { color: #666; font-size: 9pt; margin-left: 20px; }')
        mode_desc.setWordWrap(False)
        left_panel.addWidget(mode_desc)

        self.mode_button = QPushButton('Mode: COPY')
        self.mode_button.setCheckable(True)
        self.mode_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mode_button.setFixedHeight(32)
        self.mode_button.clicked.connect(self.toggle_mode)
        left_panel.addWidget(self.mode_button)

        # 4. Setup sorting destination folders
        lbl_folders = QLabel('4. Setup sorting target folders (folders where images\n    will be copied or moved)')
        lbl_folders.setStyleSheet('QLabel { color: #444; font-size: 10pt; }')
        lbl_folders.setWordWrap(False)
        left_panel.addWidget(lbl_folders)

        # FIX 1+2: indented + bullet point
        lbl_key_instr = QLabel(
            '\u2022  Press keyboard keys (e.g.: 1,2,3\u20269, or custom\n'
            '    configured letters e.g.: q,w,e\u2026m) to instantly\n'
            '    sort the previewed image into the corresponding\n'
            '    subfolder.'
        )
        lbl_key_instr.setStyleSheet('QLabel { color: #666; font-size: 9pt; margin-left: 20px; }')
        lbl_key_instr.setWordWrap(False)
        left_panel.addWidget(lbl_key_instr)

        # FIX 1: "Sorting destination:" indented to align with step 4 header text
        lbl_target_header = QLabel('Sorting destination:')
        lbl_target_header.setStyleSheet('QLabel { color: #444; font-size: 10pt; margin-left: 20px; }')
        left_panel.addWidget(lbl_target_header)

        # FIX 1+2: indented + bullet points
        lbl_checkbox_on = QLabel('\u2022  Checked \u2014 target folder is the same as Step 1.')
        lbl_checkbox_on.setStyleSheet('QLabel { color: #666; font-size: 9pt; margin-left: 26px; }')
        left_panel.addWidget(lbl_checkbox_on)

        lbl_checkbox_off = QLabel('\u2022  Unchecked \u2014 choose any custom target folder.')
        lbl_checkbox_off.setStyleSheet('QLabel { color: #666; font-size: 9pt; margin-left: 26px; }')
        left_panel.addWidget(lbl_checkbox_off)

        # Checkbox row — sits directly below its explanations
        self.use_source_checkbox = QCheckBox('Use same folder as Step 1 for target folder')
        self.use_source_checkbox.setChecked(True)
        self.use_source_checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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

        # Path row: text field + "…" browse button — sits directly below checkbox
        target_row = QHBoxLayout()

        self.target_folder_display = QLineEdit()
        self.target_folder_display.setPlaceholderText('No folder selected yet (open a folder in Step 1 or type a path)')
        self.target_folder_display.setReadOnly(True)
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

        self.select_target_btn = QPushButton('\u2026')
        self.select_target_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.select_target_btn.setFixedWidth(32)
        self.select_target_btn.setMinimumHeight(32)
        self.select_target_btn.setToolTip('Browse for target folder')
        self.select_target_btn.setEnabled(False)
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

        # Icon legend with bordered icon boxes for perfect alignment
        ICON_BOX = (
            'QLabel { color: #555; font-size: 9pt; border: 1px solid #bbb; '
            'border-radius: 3px; background: #f8f8f8; padding: 1px; }'
        )
        LEGEND_TEXT = 'QLabel { color: #555; font-size: 9pt; }'

        legend_widget = QWidget()
        legend_layout = QVBoxLayout(legend_widget)
        legend_layout.setContentsMargins(6, 2, 0, 2)
        legend_layout.setSpacing(2)

        for icon, desc in [('\u2328', 'Press below to edit shortcut key'),
                           ('\u270e', 'Press below to edit subfolder name')]:
            leg_row = QHBoxLayout()
            leg_row.setSpacing(6)
            leg_icon = QLabel(icon)
            leg_icon.setFixedSize(20, 20)
            leg_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            leg_icon.setStyleSheet(ICON_BOX)
            leg_text = QLabel(desc)
            leg_text.setStyleSheet(LEGEND_TEXT)
            leg_row.addWidget(leg_icon)
            leg_row.addWidget(leg_text)
            leg_row.addStretch()
            legend_layout.addLayout(leg_row)

        left_panel.addWidget(legend_widget)

        # FIX 2: bullet points on button instruction lines; exact button label names
        lbl_load_desc = QLabel(
            '\u2022  Press "Load Existing Subfolders (A-Z)" to import\n'
            '    subfolder names from the target folder.\n'
            '\u2022  Press "Create Folders" to create folders you typed.'
        )
        lbl_load_desc.setStyleSheet('QLabel { color: #666; font-size: 9pt; margin-left: 6px; }')
        lbl_load_desc.setWordWrap(False)
        left_panel.addWidget(lbl_load_desc)

        self.load_folders_btn = QPushButton('Load Existing Subfolders (A-Z)')
        self.load_folders_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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

        # Column headers above the key-folder rows
        col_header = QWidget()
        col_header_layout = QHBoxLayout(col_header)
        col_header_layout.setContentsMargins(0, 2, 0, 0)
        col_header_layout.setSpacing(3)

        lbl_col_key = QLabel('Key')
        lbl_col_key.setFixedWidth(28)
        lbl_col_key.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_col_key.setStyleSheet('color: #888; font-size: 8pt; font-weight: bold;')
        col_header_layout.addWidget(lbl_col_key)

        col_header_layout.addSpacing(55)

        lbl_col_folder = QLabel('Subfolder name')
        lbl_col_folder.setStyleSheet('color: #888; font-size: 8pt; font-weight: bold;')
        col_header_layout.addWidget(lbl_col_folder, 1)

        left_panel.addWidget(col_header)

        # Folder key-pair rows (dynamic)
        self.folder_inputs = []
        self.folder_enabled = []
        self.folder_keys = []
        self.folder_del_btns = []
        self.folder_save_btns = []      # ✔ save buttons (one per row, hidden by default)
        self.folder_cancel_btns = []    # ✕ cancel buttons (one per row, hidden by default)
        self.folder_saved_names = []    # last committed folder name per row
        self.folder_saved_keys = []     # last committed key per row
        self.folder_rows_widgets = []

        self.folder_rows_container = QWidget()
        self.folder_rows_layout = QVBoxLayout(self.folder_rows_container)
        self.folder_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.folder_rows_layout.setSpacing(4)
        left_panel.addWidget(self.folder_rows_container)

        default_names = ['', '', '', '', '', '', '']
        for i in range(7):
            self._add_folder_row(default_names[i])

        self.add_row_btn = QPushButton('\uff0b  Add another key\u2013folder pair')
        self.add_row_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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

        self.create_folders_btn = QPushButton('Create Folders')
        self.create_folders_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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

        left_panel.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        left_scroll.setWidget(left_content)
        left_scroll.setFixedWidth(360)
        root_layout.addWidget(left_scroll)

        # RIGHT PANEL
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(20, 10, 20, 10)
        right_panel.setSpacing(6)

        source_bar = QWidget()
        source_bar.setStyleSheet('background-color: #2b2b2b; border-radius: 0px;')
        source_bar.setFixedHeight(28)
        source_bar_layout = QHBoxLayout(source_bar)
        source_bar_layout.setContentsMargins(10, 0, 10, 0)
        source_bar_layout.setSpacing(6)

        source_bar_icon = QLabel('\U0001f4c2')
        source_bar_icon.setStyleSheet('color: #aaa; font-size: 10pt; background: transparent;')
        source_bar_layout.addWidget(source_bar_icon)

        source_bar_prefix = QLabel('Source:')
        source_bar_prefix.setStyleSheet('color: #888; font-size: 9pt; font-weight: bold; background: transparent;')
        source_bar_layout.addWidget(source_bar_prefix)

        self.source_folder_bar_label = QLabel('No folder selected \u2014 use Step 1 to open a folder')
        self.source_folder_bar_label.setStyleSheet('color: #ccc; font-size: 9pt; background: transparent;')
        self.source_folder_bar_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        source_bar_layout.addWidget(self.source_folder_bar_label, 1)

        right_panel.addWidget(source_bar)

        # Main image wrapped in a container so we can overlay an op-notification in the top-right
        img_container = QWidget()
        img_container.setStyleSheet('background: transparent;')
        img_container_layout = QGridLayout(img_container)
        img_container_layout.setContentsMargins(0, 0, 0, 0)
        img_container_layout.setSpacing(0)

        self.main_image_label = QLabel()
        self.main_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_image_label.setStyleSheet('background-color: #222; border: 2px solid #444;')
        img_container_layout.addWidget(self.main_image_label, 0, 0)  # fills entire cell

        # Overlay label — top-right corner, shown briefly after each sort operation
        self.op_overlay_label = QLabel('')
        self.op_overlay_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.op_overlay_label.setStyleSheet('background: transparent; color: transparent; padding: 0px;')
        self.op_overlay_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        img_container_layout.addWidget(self.op_overlay_label, 0, 0,
                                        alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        # Delete button — bottom-right corner of the preview image
        self.delete_btn = QPushButton('🗑  Delete  [D]')
        self.delete_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.delete_btn.setFixedHeight(30)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 40, 40, 210);
                color: #ff6b6b;
                font-size: 9pt;
                font-weight: bold;
                border: 1px solid #ff6b6b;
                border-radius: 5px;
                padding: 2px 10px;
            }
            QPushButton:hover {
                background-color: rgba(180, 40, 40, 230);
                color: white;
                border-color: white;
            }
        """)
        self.delete_btn.clicked.connect(self.delete_current_image)
        img_container_layout.addWidget(self.delete_btn, 0, 0,
                                        alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        right_panel.addWidget(img_container, stretch=8)

        self.secondary_layout = QHBoxLayout()
        self.secondary_layout.setSpacing(10)
        self.secondary_layout.addStretch(1)

        self.secondary_labels = []
        for _ in range(5):
            lbl = QLabel()
            lbl.setFixedSize(120, 120)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet('background-color: #444; border: 1px solid #555; border-radius: 6px;')
            self.secondary_labels.append(lbl)
            self.secondary_layout.addWidget(lbl)

        self.secondary_layout.addStretch(1)
        right_panel.addLayout(self.secondary_layout, stretch=2)

        # Two-line info bar at the bottom
        BAR_STYLE = 'background-color: {bg}; border-radius: 0px;'
        TEXT_CSS   = 'color: #ccc; font-size: 9pt; background: transparent;'
        PREFIX_W   = 105  # wide enough for "Last operation:" at 9pt

        # Bar 1: currently displayed image name
        cur_bar = QWidget()
        cur_bar.setStyleSheet(BAR_STYLE.format(bg='#1e1e1e'))
        cur_bar.setFixedHeight(26)
        cur_bar_layout = QHBoxLayout(cur_bar)
        cur_bar_layout.setContentsMargins(10, 0, 10, 0)
        cur_bar_layout.setSpacing(0)

        cur_bar_prefix = QLabel('Preview:')
        cur_bar_prefix.setFixedWidth(PREFIX_W)
        cur_bar_prefix.setStyleSheet('color: #666; font-size: 9pt; background: transparent;')
        cur_bar_prefix.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        cur_bar_layout.addWidget(cur_bar_prefix)

        self.current_image_name_label = QLabel('\u2014')
        self.current_image_name_label.setStyleSheet(TEXT_CSS)
        self.current_image_name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        cur_bar_layout.addWidget(self.current_image_name_label, 1)

        right_panel.addWidget(cur_bar)

        # Bar 2: last operation result
        status_bar = QWidget()
        status_bar.setStyleSheet(BAR_STYLE.format(bg='#2b2b2b'))
        status_bar.setFixedHeight(26)
        status_bar_layout = QHBoxLayout(status_bar)
        status_bar_layout.setContentsMargins(10, 0, 10, 0)
        status_bar_layout.setSpacing(0)

        op_prefix = QLabel('Last operation:')
        op_prefix.setFixedWidth(PREFIX_W)
        op_prefix.setStyleSheet('color: #666; font-size: 9pt; background: transparent;')
        op_prefix.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        status_bar_layout.addWidget(op_prefix)

        # filename → folder (stretches to fill)
        self.operation_status_label = QLabel('Ready \u2014 press a key (1\u20130, Q, W\u2026) to sort the current image')
        self.operation_status_label.setStyleSheet(TEXT_CSS)
        self.operation_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        status_bar_layout.addWidget(self.operation_status_label, 1)

        # FIX 4: op badge right-aligned, fixed width; animated via _animate_badge()
        self.operation_badge_label = QLabel('')
        self.operation_badge_label.setFixedWidth(62)
        self.operation_badge_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.operation_badge_label.setStyleSheet(
            'font-size: 9pt; font-weight: bold; background: transparent; color: transparent;'
        )
        status_bar_layout.addWidget(self.operation_badge_label)

        right_panel.addWidget(status_bar)

        right_container = QWidget()
        right_container.setLayout(right_panel)
        right_container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        right_container.mousePressEvent = lambda e: right_container.setFocus()
        root_layout.addWidget(right_container, 1)

    # --- Target folder methods ---

    def on_use_source_toggled(self, state):
        checked = (state == Qt.CheckState.Checked)
        if checked:
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
            if self.current_folder:
                self.target_folder_display.setText(self.current_folder)
            else:
                self.target_folder_display.clear()
        else:
            self.target_folder_display.setReadOnly(False)
            self.target_folder_display.setStyleSheet("""
                QLineEdit {
                    padding: 5px; border-radius: 6px;
                    border: 2px solid #aaa; background-color: #fff;
                    color: #222; font-size: 9pt;
                }
            """)
            self.select_target_btn.setEnabled(True)
            self.target_folder_display.setPlaceholderText('Type a path or click \u2026 to browse')
        self.centralWidget().setFocus()

    def on_target_path_edited(self, text):
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
        if self.target_base_folder and os.path.isdir(self.target_base_folder):
            return self.target_base_folder
        return self.current_folder

    def write_log_entry(self, target_base, subfolder_name, image_src_path, image_dst_path):
        log_path = os.path.join(target_base, LOG_FILENAME)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        operation = 'COPY' if self.copy_mode else 'MOVE'
        dst_folder_path = os.path.join(target_base, subfolder_name)
        new_entry = f'[{timestamp}]  {operation}  {image_src_path}  \u2192  {dst_folder_path}'

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

    def write_delete_log_entry(self, deleted_path: str):
        """Log a DELETE operation to the target base folder's log file."""
        target_base = self.get_effective_target_folder()
        if not target_base:
            return
        log_path = os.path.join(target_base, LOG_FILENAME)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_entry = f'[{timestamp}]  DELETE  {deleted_path}'

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

    def delete_current_image(self):
        """Permanently delete the currently previewed image after confirmation."""
        if not self.images:
            return

        filename = self.images[self.current_index]
        src_path = os.path.join(self.current_folder, filename)

        reply = QMessageBox.question(
            self,
            'Delete Image',
            f'Permanently delete this file?\n\n{filename}\n\nThis cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            os.remove(src_path)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Could not delete file:\n{e}')
            return

        # Remove from image list and advance
        del self.images[self.current_index]
        if self.images:
            self.current_index = min(self.current_index, len(self.images) - 1)

        # Log the deletion
        self.write_delete_log_entry(src_path)

        # Update status bar
        self.operation_status_label.setText(f'{filename}  [DELETED]')
        self.operation_status_label.setStyleSheet('color: #ff6b6b; font-size: 9pt; background: transparent;')
        self.operation_badge_label.setText('')

        self.update_previews()
        if self.images:
            self._pix_cache.start_preload(self.current_folder, self.images, self.current_index)
        else:
            self.operation_status_label.setText('No more images in the source folder.')

        self.centralWidget().setFocus()

    # --- Dynamic folder-row helpers ---

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

        ICON_BTN = """
            QPushButton {{
                border-radius: 5px; border: 2px solid #aaa;
                background: white; padding: 2px; font-size: 9pt; color: #444;
                width: {w}px; height: 28px;
            }}
            QPushButton:checked {{ background-color: #e8e8e8; border-color: #888; }}
            QPushButton:hover   {{ background-color: #f0f0f0; }}
        """

        # ── Key field + ⌨ button ──────────────────────────────────────────
        key_edit = QLineEdit(default_key)
        key_edit.setFixedWidth(28)
        key_edit.setFixedHeight(30)
        key_edit.setEnabled(False)
        key_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        key_edit.setMaxLength(2)
        key_edit.setStyleSheet("""
            QLineEdit {
                font-weight: bold; font-size: 10pt; color: #333;
                border: 2px solid transparent; border-radius: 5px;
                background: transparent; padding: 0px;
            }
            QLineEdit:enabled {
                background: white; border: 2px solid #f0a500; color: #c0700a;
            }
        """)
        row.addWidget(key_edit)

        key_btn = QPushButton('\u2328')
        key_btn.setCheckable(True)
        key_btn.setFixedWidth(26)
        key_btn.setFixedHeight(28)
        key_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        key_btn.setToolTip('Edit the shortcut key for this folder')
        key_btn.setStyleSheet(ICON_BTN.format(w=26) +
            'QPushButton:checked { background-color: #fff3cd; border-color: #f0a500; color: #c0700a; }')
        row.addWidget(key_btn)

        # ── Folder name field + ✎ button ─────────────────────────────────
        pencil_btn = QPushButton('\u270e')
        pencil_btn.setCheckable(True)
        pencil_btn.setFixedWidth(26)
        pencil_btn.setFixedHeight(28)
        pencil_btn.setStyleSheet(ICON_BTN.format(w=26) +
            'QPushButton:checked { background-color: #dbeafe; border-color: #3b82f6; color: #1d4ed8; }')
        pencil_btn.setToolTip('Enable editing of folder name')
        pencil_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(pencil_btn)

        edit = QLineEdit(default_name)
        edit.setEnabled(False)
        edit.setFixedHeight(28)
        edit.setStyleSheet(
            'QLineEdit { padding: 4px; border-radius: 5px; font-size: 9pt; border: 2px solid #ccc; }'
            'QLineEdit:enabled { border: 2px solid #3b82f6; background: #f0f7ff; }'
        )
        row.addWidget(edit)

        # ── Save ✔ and Cancel ✕ buttons (hidden until editing starts) ─────
        COMMIT_BTN = """
            QPushButton {{
                border-radius: 5px; border: 2px solid {border};
                background: {bg}; padding: 2px; font-size: 10pt;
                font-weight: bold; color: {fg}; width: 24px; height: 28px;
            }}
            QPushButton:hover {{ background: {hbg}; }}
        """
        save_btn = QPushButton('\u2714')   # ✔
        save_btn.setFixedWidth(24)
        save_btn.setFixedHeight(28)
        save_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        save_btn.setToolTip('Save changes')
        save_btn.setStyleSheet(COMMIT_BTN.format(
            border='#27ae60', bg='#eafaf1', fg='#27ae60', hbg='#d5f5e3'))
        save_btn.setVisible(False)
        row.addWidget(save_btn)

        cancel_btn = QPushButton('\u2716')   # ✖
        cancel_btn.setFixedWidth(24)
        cancel_btn.setFixedHeight(28)
        cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel_btn.setToolTip('Cancel — restore previous name/key')
        cancel_btn.setStyleSheet(COMMIT_BTN.format(
            border='#e74c3c', bg='#fdf2f2', fg='#e74c3c', hbg='#fadbd8'))
        cancel_btn.setVisible(False)
        row.addWidget(cancel_btn)

        # ── Reorder / delete buttons ──────────────────────────────────────
        up_btn = QPushButton('\u25b2')
        up_btn.setFixedWidth(20)
        up_btn.setFixedHeight(28)
        up_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        up_btn.setToolTip('Move up')
        up_btn.setStyleSheet(ICON_BTN.format(w=20))
        up_btn.clicked.connect(lambda _, w=row_widget: self._move_row_up(w))
        row.addWidget(up_btn)

        dn_btn = QPushButton('\u25bc')
        dn_btn.setFixedWidth(20)
        dn_btn.setFixedHeight(28)
        dn_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        dn_btn.setToolTip('Move down')
        dn_btn.setStyleSheet(ICON_BTN.format(w=20))
        dn_btn.clicked.connect(lambda _, w=row_widget: self._move_row_dn(w))
        row.addWidget(dn_btn)

        del_btn = QPushButton('\xd7')
        del_btn.setFixedWidth(22)
        del_btn.setFixedHeight(28)
        del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        del_btn.setToolTip('Remove this key\u2013folder pair')
        del_btn.setStyleSheet(ICON_BTN.format(w=22) +
            'QPushButton:hover { background-color: #ffe0e0; border-color: #e88; color: #c00; }')
        del_btn.clicked.connect(lambda _, w=row_widget: self._delete_row(w))
        row.addWidget(del_btn)

        # ── Wire up editing logic ─────────────────────────────────────────
        # We need refs to all four widgets inside the lambdas
        def _on_key_toggled(checked,
                            _key_edit=key_edit, _key_btn=key_btn,
                            _pencil_btn=pencil_btn,
                            _save=save_btn, _cancel=cancel_btn):
            _key_edit.setEnabled(checked)
            # Show/hide save+cancel; track editing state across both toggles
            editing = checked or _pencil_btn.isChecked()
            _save.setVisible(editing)
            _cancel.setVisible(editing)
            if not checked:
                self.centralWidget().setFocus()

        def _on_pencil_toggled(checked,
                               _edit=edit, _pencil_btn=pencil_btn,
                               _key_btn=key_btn,
                               _save=save_btn, _cancel=cancel_btn):
            _edit.setEnabled(checked)
            editing = checked or _key_btn.isChecked()
            _save.setVisible(editing)
            _cancel.setVisible(editing)
            if not checked:
                self.centralWidget().setFocus()

        def _on_save(checked=False,
                     _edit=edit, _key_edit=key_edit,
                     _pencil_btn=pencil_btn, _key_btn=key_btn,
                     _save=save_btn, _cancel=cancel_btn,
                     _row_idx=[idx]):
            """Commit both fields, update saved values, exit editing mode."""
            i = self.folder_rows_widgets.index(row_widget)
            self.folder_saved_names[i] = _edit.text()
            self.folder_saved_keys[i]  = _key_edit.text()
            # Deactivate both toggle buttons (suppressing signals to avoid recursion)
            _pencil_btn.blockSignals(True); _pencil_btn.setChecked(False); _pencil_btn.blockSignals(False)
            _key_btn.blockSignals(True);    _key_btn.setChecked(False);    _key_btn.blockSignals(False)
            _edit.setEnabled(False)
            _key_edit.setEnabled(False)
            _save.setVisible(False)
            _cancel.setVisible(False)
            self._update_create_folders_highlight()
            self.centralWidget().setFocus()

        def _on_cancel(checked=False,
                       _edit=edit, _key_edit=key_edit,
                       _pencil_btn=pencil_btn, _key_btn=key_btn,
                       _save=save_btn, _cancel=cancel_btn):
            """Restore previous saved values and exit editing mode."""
            i = self.folder_rows_widgets.index(row_widget)
            _edit.setText(self.folder_saved_names[i])
            _key_edit.setText(self.folder_saved_keys[i])
            _pencil_btn.blockSignals(True); _pencil_btn.setChecked(False); _pencil_btn.blockSignals(False)
            _key_btn.blockSignals(True);    _key_btn.setChecked(False);    _key_btn.blockSignals(False)
            _edit.setEnabled(False)
            _key_edit.setEnabled(False)
            _save.setVisible(False)
            _cancel.setVisible(False)
            self.centralWidget().setFocus()

        key_btn.toggled.connect(_on_key_toggled)
        pencil_btn.toggled.connect(_on_pencil_toggled)
        save_btn.clicked.connect(_on_save)
        cancel_btn.clicked.connect(_on_cancel)

        # ── Register in tracking lists ────────────────────────────────────
        self.folder_inputs.append(edit)
        self.folder_enabled.append(pencil_btn)
        self.folder_keys.append(key_edit)
        self.folder_del_btns.append(del_btn)
        self.folder_save_btns.append(save_btn)
        self.folder_cancel_btns.append(cancel_btn)
        self.folder_saved_names.append(default_name)
        self.folder_saved_keys.append(default_key)
        self.folder_rows_widgets.append(row_widget)
        self.folder_rows_layout.addWidget(row_widget)

    def _get_effective_key(self, index):
        if index < len(self.folder_keys):
            val = self.folder_keys[index].text().strip()
            if val:
                return val.lower()
        return self._get_key_label_for(index)

    def _refresh_key_labels(self):
        for i, row_widget in enumerate(self.folder_rows_widgets):
            key_edit_widget = row_widget.layout().itemAt(0).widget()
            if isinstance(key_edit_widget, QLineEdit):
                key_btn_widget = row_widget.layout().itemAt(1).widget()
                if isinstance(key_btn_widget, QPushButton) and not key_btn_widget.isChecked():
                    old_default = self._get_key_label_for(i)
                    current_val = key_edit_widget.text().strip()
                    if current_val in self.KEY_SEQUENCE:
                        key_edit_widget.setText(old_default)

    def _delete_row(self, row_widget):
        if len(self.folder_rows_widgets) <= 1:
            return
        idx = self.folder_rows_widgets.index(row_widget)
        self.folder_rows_layout.removeWidget(row_widget)
        row_widget.setParent(None)
        self.folder_rows_widgets.pop(idx)
        self.folder_inputs.pop(idx)
        self.folder_enabled.pop(idx)
        self.folder_keys.pop(idx)
        self.folder_del_btns.pop(idx)
        self.folder_save_btns.pop(idx)
        self.folder_cancel_btns.pop(idx)
        self.folder_saved_names.pop(idx)
        self.folder_saved_keys.pop(idx)
        self._refresh_key_labels()
        self.centralWidget().setFocus()

    def _swap_rows(self, i, j):
        for lst in (self.folder_rows_widgets, self.folder_inputs,
                    self.folder_enabled, self.folder_keys, self.folder_del_btns,
                    self.folder_save_btns, self.folder_cancel_btns,
                    self.folder_saved_names, self.folder_saved_keys):
            lst[i], lst[j] = lst[j], lst[i]
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

    def _update_create_folders_highlight(self):
        """
        Highlight 'Create Folders' with an orange border when any saved folder
        name differs from what was loaded by 'Load Existing Subfolders'.
        Resets to normal when all names match the loaded set (or no names loaded).
        """
        if not self._loaded_subfolder_names:
            # Nothing was loaded — no highlight needed
            self.create_folders_btn.setStyleSheet("""
                QPushButton {
                    background-color: white; font-weight: bold; padding: 4px;
                    border: 2px solid #aaa; border-radius: 6px;
                }
                QPushButton:hover { background-color: #f8f8f8; }
            """)
            return

        current_names = {n for n in self.folder_saved_names if n.strip()}
        has_new = bool(current_names - self._loaded_subfolder_names)

        if has_new:
            self.create_folders_btn.setStyleSheet("""
                QPushButton {
                    background-color: #fff8ee; font-weight: bold; padding: 4px;
                    border: 2px solid #f0a500; border-radius: 6px; color: #b36800;
                }
                QPushButton:hover { background-color: #fff0d0; }
            """)
        else:
            self.create_folders_btn.setStyleSheet("""
                QPushButton {
                    background-color: white; font-weight: bold; padding: 4px;
                    border: 2px solid #aaa; border-radius: 6px;
                }
                QPushButton:hover { background-color: #f8f8f8; }
            """)

    def open_folder(self):
        last_folder = self.settings.value('last_folder', '')
        start_dir = last_folder if last_folder and os.path.isdir(last_folder) else os.getcwd()

        folder = QFileDialog.getExistingDirectory(self, 'Select Image Folder', start_dir)
        if not folder:
            return

        self.current_folder = folder
        self.settings.setValue('last_folder', folder)
        self.source_folder_bar_label.setText(folder)

        # Collect all images recursively from all subfolders, sorted by full path.
        # self.images stores relative paths (e.g. "subfolder/img.arw") so the
        # full path is always: os.path.join(self.current_folder, relative_path)
        all_images = []
        for dirpath, _dirnames, filenames in os.walk(folder):
            for fname in filenames:
                if fname.lower().endswith(IMAGE_EXTENSIONS):
                    rel = os.path.relpath(os.path.join(dirpath, fname), folder)
                    all_images.append(rel)
        self.images = sorted(all_images, key=str.lower)
        if not self.images:
            QMessageBox.warning(self, 'No Images', 'Selected folder has no images.')
            return

        self.current_index = 0
        self._pix_cache.clear()
        self._pix_cache.start_preload(folder, self.images, 0)
        self.update_previews()
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

            for w in list(self.folder_rows_widgets):
                self.folder_rows_layout.removeWidget(w)
                w.setParent(None)
            self.folder_rows_widgets.clear()
            self.folder_inputs.clear()
            self.folder_enabled.clear()
            self.folder_keys.clear()
            self.folder_del_btns.clear()
            self.folder_save_btns.clear()
            self.folder_cancel_btns.clear()
            self.folder_saved_names.clear()
            self.folder_saved_keys.clear()

            count = max(len(subfolders), 1)
            for i in range(count):
                name = subfolders[i] if i < len(subfolders) else ''
                self._add_folder_row(name)
                # FIX 3: do NOT auto-enable pencil/edit — just populate names, leave locked

            self._refresh_key_labels()
            # Record what was loaded so we can detect new names later
            self._loaded_subfolder_names = set(subfolders)
            self._update_create_folders_highlight()
            QMessageBox.information(
                self, 'Subfolders Loaded',
                f'Loaded {len(subfolders)} subfolder(s) \u2014 {count} key\u2013folder pair(s) created.'
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
            self.current_image_name_label.setText('\u2014')
            return

        current_name = self.images[self.current_index]
        # Show the full relative path so subfolder origin is always visible
        self.current_image_name_label.setText(current_name)

        img_path = os.path.join(self.current_folder, current_name)
        # Try cache first; fall back to direct load (blocks briefly only on cache miss)
        pix = self._pix_cache.get(img_path)
        if pix is None:
            pix = load_pixmap(img_path)
        self.main_image_label.setPixmap(pix.scaled(
            self.main_image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))

        offsets = [-2, -1, 0, 1, 2]
        for lbl, off in zip(self.secondary_labels, offsets):
            idx = self.current_index + off
            if 0 <= idx < len(self.images):
                thumb_path = os.path.join(self.current_folder, self.images[idx])
                p = self._pix_cache.get(thumb_path)
                if p is None:
                    p = load_pixmap(thumb_path)
                lbl.setPixmap(p.scaled(110, 110, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                lbl.clear()

    def keyPressEvent(self, event):
        if isinstance(self.focusWidget(), QLineEdit) and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.focusWidget().event(event)
            return

        if not self.images:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key.Key_Right:
            self.current_index = min(self.current_index + 1, len(self.images) - 1)
            self.update_previews()
            self._pix_cache.start_preload(self.current_folder, self.images, self.current_index)
            event.accept()
            return
        elif key == Qt.Key.Key_Left:
            self.current_index = max(self.current_index - 1, 0)
            self.update_previews()
            self._pix_cache.start_preload(self.current_folder, self.images, self.current_index)
            event.accept()
            return

        if isinstance(self.focusWidget(), QLineEdit):
            super().keyPressEvent(event)
            return

        # D = delete current image
        if key == Qt.Key.Key_D.value:
            self.delete_current_image()
            event.accept()
            return

        key_char = None
        if Qt.Key.Key_1.value <= key <= Qt.Key.Key_9.value:
            key_char = str(key - Qt.Key.Key_0.value)
        elif key == Qt.Key.Key_0.value:
            key_char = '0'
        elif Qt.Key.Key_A.value <= key <= Qt.Key.Key_Z.value:
            key_char = chr(key).lower()

        if key_char is not None:
            for idx in range(len(self.folder_inputs)):
                if self._get_effective_key(idx) == key_char:
                    self.handle_sort(idx)
                    event.accept()
                    return

        super().keyPressEvent(event)

    def _animate_badge(self, op_word, op_color):
        """Brief bright→dim flash on the right-side badge in the status bar."""
        BRIGHT = f'font-size: 9pt; font-weight: bold; background: transparent; color: {op_color};'
        DIM    = 'font-size: 9pt; font-weight: bold; background: transparent; color: #666;'

        self.operation_badge_label.setText(op_word)
        self.operation_badge_label.setStyleSheet(BRIGHT)

        t1 = QTimer(self)
        t1.setSingleShot(True)
        t1.timeout.connect(lambda: self.operation_badge_label.setStyleSheet(DIM))
        t1.start(180)

        t2 = QTimer(self)
        t2.setSingleShot(True)
        t2.timeout.connect(lambda: self.operation_badge_label.setStyleSheet(BRIGHT))
        t2.start(360)

        t3 = QTimer(self)
        t3.setSingleShot(True)
        t3.timeout.connect(lambda: self.operation_badge_label.setStyleSheet(DIM))
        t3.start(560)

    def _animate_overlay(self, op_word, op_color):
        """
        Show a large icon+text badge in the top-right corner of the preview image.
        COPIED → green  📋  COPIED
        MOVED  → orange ✂   MOVED
        Animates: appear bright → fade to transparent over ~900 ms, then clears completely.
        """
        icon = '\U0001f4cb' if op_word == 'COPIED' else '\u2702'  # 📋 or ✂
        label_text = f'{icon}  {op_word}'

        SHOW = (
            f'font-size: 15pt; font-weight: bold; background: transparent;'
            f' color: {op_color}; padding: 8px 12px; border-radius: 8px;'
        )
        HALF = (
            f'font-size: 15pt; font-weight: bold; background: transparent;'
            f' color: rgba(180,180,180,160); padding: 8px 12px; border-radius: 8px;'
        )
        GONE = 'background: transparent; color: transparent; padding: 0px;'

        self.op_overlay_label.setText(label_text)
        self.op_overlay_label.setStyleSheet(SHOW)

        t1 = QTimer(self)
        t1.setSingleShot(True)
        t1.timeout.connect(lambda: self.op_overlay_label.setStyleSheet(HALF))
        t1.start(400)

        t2 = QTimer(self)
        t2.setSingleShot(True)
        def _clear():
            self.op_overlay_label.setStyleSheet(GONE)
            self.op_overlay_label.setText('')   # remove text so no space is reserved
        t2.timeout.connect(_clear)
        t2.start(900)

    def handle_sort(self, folder_idx):
        if folder_idx >= len(self.folder_inputs):
            return

        src_path = os.path.join(self.current_folder, self.images[self.current_index])
        target_name = self.folder_inputs[folder_idx].text().strip()
        if not target_name:
            QMessageBox.warning(self, 'Empty Name', 'Folder name is empty. Set a name first.')
            return

        target_base = self.get_effective_target_folder()
        target_folder = os.path.join(target_base, target_name)

        # If the folder doesn't exist yet, ask the user instead of creating silently
        if not os.path.isdir(target_folder):
            reply = QMessageBox.question(
                self,
                'Folder Does Not Exist',
                f'The folder "{target_name}" does not exist yet in:\n{target_base}\n\n'
                f'Create it now and continue?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                os.makedirs(target_folder, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Could not create folder:\n{e}')
                return
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

        self.write_log_entry(target_base, target_name, src_path, dst_path)

        op = 'MOVED' if not self.copy_mode else 'COPIED'
        op_color = '#e67e22' if not self.copy_mode else '#27ae60'
        filename = os.path.basename(src_path)
        # rel_path includes any subfolder, e.g. "2024/January/DSC001.ARW"
        rel_path = self.images[self.current_index]

        # filename + arrow + folder + op word in the main label; badge + overlay flash
        self.operation_status_label.setText(f'{rel_path}  \u2192  {target_name}  [{op}]')
        self.operation_status_label.setStyleSheet('color: #ccc; font-size: 9pt; background: transparent;')
        self.operation_status_label.setTextFormat(Qt.TextFormat.PlainText)

        self._animate_badge(op, op_color)    # flash badge on the right of status bar
        self._animate_overlay(op, op_color)  # large icon+text in top-right of preview

        self.update_previews()
        if self.images:
            self._pix_cache.start_preload(self.current_folder, self.images, self.current_index)

        if not self.copy_mode and was_last_image:
            self.operation_status_label.setText('No more images to sort in the source folder.')
            self.operation_badge_label.setText('')

        self.centralWidget().setFocus()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageSorterApp()
    window.showMaximized()
    sys.exit(app.exec())