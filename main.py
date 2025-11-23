# main.py
import sys, os, csv, datetime, traceback, shutil
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QPixmap, QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QListWidget, QListWidgetItem, QLineEdit, QScrollArea, QFileDialog,
    QMessageBox, QSplitter, QComboBox, QInputDialog, QMenu, QDialog,
    QGraphicsDropShadowEffect
)

# --- Rutas base ---
def resolve_app_dirs():
    """Return (app_dir, resource_dir) for script/frozen modes."""
    if getattr(sys, "frozen", False):
        app_root = Path(sys.executable).parent
        resource_root = Path(getattr(sys, "_MEIPASS", app_root))
    else:
        app_root = Path(__file__).parent
        resource_root = app_root
    return app_root, resource_root


APP_DIR, RESOURCE_DIR = resolve_app_dirs()
DATA_DIR   = APP_DIR / "data"
ASSETS_DIR = APP_DIR / "assets"
PRODS_CSV  = DATA_DIR / "productos.csv"
LOG_FILE   = APP_DIR / "logs.txt"
BACKUP_DIR = DATA_DIR / "historial" / "backups"
SUMMARY_DIR = DATA_DIR / "historial" / "resumenes"
PRINTER_NAME = os.environ.get("POS_PRINTER")
CUT_COMMAND = b"\x1d\x56\x00"  # ESC/POS: full cut after imprimir

# --- Paleta base (visual) ---
ACCENT = "#22c8b8"
ACCENT_DARK = "#16a796"
BG = "#121416"
PANEL = "#1b1d21"
CARD_BG = "#25282d"
CARD_HOVER = "#2d3238"


def sanitize_pdf_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def write_text_pdf(path: Path, lines, title="Ticket Camelia"):
    lines = [line.encode("ascii", "ignore").decode("ascii") for line in lines]
    chunks = [lines[i:i + 40] for i in range(0, len(lines), 40)] or [[""]]
    objects = []

    def add_object(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    def set_object(idx: int, data: bytes):
        objects[idx - 1] = data

    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    content_ids = []
    for chunk in chunks:
        content_lines = ["BT", "/F1 11 Tf", "13 TL", "40 780 Td"]
        for idx, line in enumerate(chunk):
            content_lines.append(f"({sanitize_pdf_text(line)}) Tj")
            if idx != len(chunk) - 1:
                content_lines.append("T*")
        content_lines.append("ET")
        content_str = "\n".join(content_lines).encode("ascii")
        stream = f"<< /Length {len(content_str)} >>\nstream\n".encode("ascii") + content_str + b"\nendstream"
        content_ids.append(add_object(stream))

    pages_obj_id = len(objects) + 1
    objects.append(None)
    page_ids = []
    for content_id in content_ids:
        page_dict = (
            f"<< /Type /Page /Parent {pages_obj_id} 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        ).encode("ascii")
        page_ids.append(add_object(page_dict))
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_dict = f"<< /Type /Pages /Kids [ {kids} ] /Count {len(page_ids)} >>".encode("ascii")
    set_object(pages_obj_id, pages_dict)
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_obj_id} 0 R /Lang (es) /ViewerPreferences << /DisplayDocTitle true >> >>".encode("ascii"))

    with path.open("wb") as f:
        f.write(b"%PDF-1.4\n")
        offsets = [0]
        for idx, data in enumerate(objects, start=1):
            offsets.append(f.tell())
            f.write(f"{idx} 0 obj\n".encode("ascii"))
            f.write(data)
            f.write(b"\nendobj\n")
        xref_pos = f.tell()
        total = len(objects) + 1
        f.write(f"xref\n0 {total}\n".encode("ascii"))
        f.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            f.write(f"{offset:010d} 00000 n \n".encode("ascii"))
        metadata = f"trailer\n<< /Size {total} /Root {catalog_id} 0 R /Info << /Title ({sanitize_pdf_text(title)}) >> >>\nstartxref\n{xref_pos}\n%%EOF".encode("ascii")
        f.write(metadata)


def ensure_log_file():
    """Crea logs.txt vacío si aún no existe (para que el staff lo ubique)."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not LOG_FILE.exists():
            with open(LOG_FILE, "w", encoding="utf-8") as log:
                log.write("=== Cafeteria POS logs ===\n")
    except Exception:
        pass


def _write_log(prefix: str, message: str, exc: Exception | None = None):
    try:
        ensure_log_file()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"[{timestamp}] {prefix} {message}\n")
            if exc:
                log.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            log.write("\n")
    except Exception:
        # No hacemos nada si fallan los logs para no romper el flujo principal.
        pass


def log_error(message: str, exc: Exception | None = None):
    """Persiste errores en logs.txt."""
    _write_log("ERROR", message, exc)


def log_event(message: str):
    """Log simple para auditoria de sesiones/acciones."""
    _write_log("INFO ", message)

# --- Utilidades de datos ---
def ensure_runtime_payload():
    """In modo frozen copiamos assets/data junto al exe si faltan."""
    if RESOURCE_DIR == APP_DIR:
        return
    for folder in ("assets", "data"):
        src = RESOURCE_DIR / folder
        dest = APP_DIR / folder
        if src.exists() and not dest.exists():
            shutil.copytree(src, dest)


def ensure_dirs():
    ensure_runtime_payload()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    hist_dir = DATA_DIR / "historial"
    hist_dir.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

def bootstrap_products_csv():
    """Crea un productos.csv de ejemplo si no existe."""
    if not PRODS_CSV.exists():
        rows = [
            ["item_id","item_desc","categoria","precio","activo","imagen"],
            ["no_hay_datos","No hay datos","Miscelaneo","999.99","0", str(ASSETS_DIR / "not_found.png")],
        ]
        with open(PRODS_CSV, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)

def load_products():
    """Lee productos.csv -> (lista de dicts válidos, lista de mensajes de error)."""
    prods = []
    errors = []
    with open(PRODS_CSV, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):
            if row.get("activo", "1") == "1":
                desc = row.get("item_desc", "").strip()
                if not desc:
                    errors.append(f"Linea {idx}: item_desc vacío (ID {row.get('item_id','?')}).")
                    continue
                try:
                    row["precio"] = float(row["precio"])
                except Exception:
                    errors.append(f"Linea {idx}: precio inválido ({row.get('precio')}) en {desc}.")
                    continue
                if row["precio"] <= 0:
                    errors.append(f"Linea {idx}: precio debe ser > 0 en {desc}.")
                    continue
                prods.append(row)
    return prods, errors


def install_exception_logger():
    """Registra un excepthook global para dejar trazas en logs.txt."""
    ensure_log_file()
    def _hook(exc_type, exc, tb):
        log_error("Excepcion no controlada", exc)
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = _hook

def current_sales_path():
    """Devuelve ruta del CSV mensual y se asegura de que exista con encabezado."""
    now = datetime.datetime.now()
    fn = f"ventas_{now:%Y-%m}.csv"
    p = DATA_DIR / "historial" / fn
    if not p.exists():
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("fecha_hora,ticket_id,item_id,item_desc,categoria,cantidad,precio_unit,subtotal,medio_pago,cajero,nota\n")
    return p

def sales_path_for_date(target_date: datetime.date) -> Path:
    return DATA_DIR / "historial" / f"ventas_{target_date:%Y-%m}.csv"

def last_ticket_id_from_csv(csv_path: Path) -> int:
    """Lee el último ticket_id del CSV (si existe) y retorna el siguiente."""
    if not csv_path.exists():
        return 1
    last = 0
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split(",")
                if len(parts) > 1 and parts[0] != "fecha_hora":
                    try:
                        last = max(last, int(parts[1]))
                    except:
                        pass
    except:
        return 1
    return last + 1

# --- Widgets ---
class ProductCard(QPushButton):
    def __init__(self, prod: dict, on_add):
        super().__init__()
        self.prod = prod
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(180, 200)
        self.setStyleSheet("""
            QPushButton {
                text-align: left; padding: 10px; border-radius: 12px;
                background: %s; color: #e8eaef; border: 1px solid #2f343b;
            }
            QPushButton:hover { background: %s; border-color: %s; }
        """ % (CARD_BG, CARD_HOVER, ACCENT))
        v = QVBoxLayout(self)
        img_path = prod.get("imagen", "")
        if img_path and Path(img_path).exists():
            pix = QPixmap(str(img_path)).scaled(160, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl = QLabel(); lbl.setPixmap(pix); lbl.setAlignment(Qt.AlignCenter)
            v.addWidget(lbl, alignment=Qt.AlignCenter)
        name = QLabel(prod["item_desc"])
        name.setStyleSheet("font-weight:600; color:#f3f4f6;")
        price = QLabel(f"${prod['precio']:,.2f}")
        price.setStyleSheet("color:#cdd3dd;")
        v.addWidget(name); v.addWidget(price)
        self.clicked.connect(lambda: on_add(prod, 1, False))

        # Sombra suave para separar cada card del fondo.
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(Qt.black)
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

# --- App principal ---
class POS(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cafetería POS")
        self.setWindowIcon(QIcon())
        ensure_dirs()
        bootstrap_products_csv()

        self.prods, self.prods_errors = load_products()
        self.ticket = []  # lista de {"prod":dict, "cant":int}
        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet(
            f"padding:8px; border-radius:10px; background:{PANEL}; color:#d5dbe6; border:1px solid #22262c;"
        )
        self.sales_path = None
        self.current_period = None
        self.current_day = datetime.date.today()
        self.last_backup_signature = None
        self.shortcuts = []
        self.settings = QSettings("CameliaPOS", "CafeteriaPOS")
        self.kiosk_enabled = self.settings.value("kiosk_enabled", False, type=bool)
        self.ticket_discount = 0.0
        self.refresh_sales_target(force=True)
        self.generate_daily_summary(self.current_day - datetime.timedelta(days=1), mode="auto")
        log_event("Sesion POS iniciada.")

        # ----- Buscador (definido ANTES de senales) -----
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar producto...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filters)
        self.search.setStyleSheet(
            "QLineEdit {"
            " background:#0f1114; color:#e6e9ef; border:1px solid #252a31;"
            " border-radius:10px; padding:10px 12px;"
            "}"
            f"QLineEdit:focus {{ border:1px solid {ACCENT}; }}"
        )

        # ----- Sidebar de categorías -----
        self.categories = ["Todas"] + sorted({p["categoria"] for p in self.prods})
        self.cat_list = QListWidget()
        for c in self.categories:
            QListWidgetItem(c, self.cat_list)
        self.cat_list.setFixedWidth(200)
        self.cat_list.setSelectionMode(QListWidget.SingleSelection)
        self.cat_list.setStyleSheet(
            "QListWidget { background:%s; color:#e4e7ee; border:0; padding:6px; }"
            "QListWidget::item { padding:10px; margin:4px; border-radius:12px; }"
            "QListWidget::item:selected { background:%s; color:#0c1115; font-weight:600; }"
            "QListWidget::item:hover { background:#2c3138; }"
            % (PANEL, ACCENT)
        )

        # ----- Grilla de productos (scroll) -----
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)

        grid_wrap = QWidget(); grid_wrap.setLayout(self.grid)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(grid_wrap)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG}; border:0; }}")

        # ----- Ticket / derecha -----
        self.ticket_list = QListWidget()
        self.ticket_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ticket_list.customContextMenuRequested.connect(self.show_ticket_menu)
        self.ticket_list.itemDoubleClicked.connect(
            lambda item: self.edit_ticket_row(self.ticket_list.row(item))
        )
        self.ticket_base_style = (
            "QListWidget {"
            f" background:{PANEL};"
            " color:#f1f2f5;"
            f" border:1px solid {ACCENT};"
            " border-radius:12px;"
            " padding:10px;"
            "}"
            "QListWidget::item { padding:6px 2px; }"
        )
        self.ticket_list.setStyleSheet(self.ticket_base_style)

        self.mpago = QComboBox()
        self.mpago.addItems(["Efectivo", "Tarjeta", "QR", "Debito"])

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Codigo rapido (ID o ID*3) y Enter")
        self.code_input.setClearButtonEnabled(True)
        self.code_input.returnPressed.connect(self.handle_code_entry)
        self.code_input.setStyleSheet(
            "QLineEdit { background:#0f1114; color:#e6e9ef; border:1px solid #252a31; border-radius:10px; padding:8px; }"
            f"QLineEdit:focus {{ border:1px solid {ACCENT}; }}"
        )

        self.total_lbl = QLabel("Total: $0.00")
        self.total_lbl.setAlignment(Qt.AlignRight)
        self.total_lbl.setStyleSheet("color:#f3f4f6; padding:10px; font-size:16px; font-weight:700;")

        btn_cobrar = QPushButton("Cobrar"); btn_cobrar.clicked.connect(self.checkout)
        btn_export = QPushButton("Exportar a Excel"); btn_export.clicked.connect(self.export_excel)
        btn_resumen = QPushButton("Resumen diario"); btn_resumen.clicked.connect(self.manual_daily_summary)
        btn_info = QPushButton("Info / Ayuda"); btn_info.clicked.connect(self.show_help_info)
        btn_clear = QPushButton("Limpiar ticket"); btn_clear.clicked.connect(self.clear_ticket)
        btn_bonus = QPushButton("Bonificaciones"); btn_bonus.clicked.connect(self.manage_discounts)
        btn_kiosk = QPushButton("Modo kiosco"); btn_kiosk.setCheckable(True)
        btn_kiosk.setChecked(self.kiosk_enabled)
        btn_kiosk.toggled.connect(self.set_kiosk_state)
        self.btn_kiosk = btn_kiosk
        self.btn_bonus = btn_bonus
        for b in (btn_cobrar, btn_export, btn_resumen, btn_info, btn_clear, btn_bonus, btn_kiosk):
            b.setMinimumHeight(40)
            b.setStyleSheet(
                "QPushButton { background:%s; color:#0c1115; border:1px solid %s; border-radius:10px; padding:10px; font-weight:600; }"
                "QPushButton:hover { background:%s; }"
                "QPushButton:pressed { background:%s; }"
            % (ACCENT, ACCENT_DARK, ACCENT_DARK, "#118274")
            )
        btn_cobrar.setStyleSheet(
            "QPushButton { background:%s; color:#0b0f13; border:1px solid %s; border-radius:12px; padding:12px; font-weight:700; }"
            "QPushButton:hover { background:%s; }"
            "QPushButton:pressed { background:%s; }"
        % ("#ffd166", "#f4b400", "#ffbe44", "#d89a00")
        )

        # ----- Layouts -----
        left_panel = QVBoxLayout(); left_panel.addWidget(self.cat_list)
        left_widget = QWidget(); left_widget.setLayout(left_panel)

        center_panel = QVBoxLayout(); center_panel.addWidget(self.search); center_panel.addWidget(scroll)
        center_widget = QWidget(); center_widget.setLayout(center_panel)

        right = QVBoxLayout()
        right.addWidget(QLabel("Ticket actual"))
        right.addWidget(self.ticket_list, 1)
        right.addWidget(self.total_lbl)
        right.addWidget(QLabel("Codigo rapido / lector"))
        right.addWidget(self.code_input)
        right.addWidget(self.status_lbl)
        self.tips_box = QLabel(
            "Tips rapidos:\n"
            "- Ctrl+Enter: Cobrar\n"
            "- Ctrl+L: Ir a Codigo rapido\n"
            "- F2: Modo kiosco; Esc para salir"
        )
        self.tips_box.setWordWrap(True)
        self.tips_box.setStyleSheet(
            f"padding:8px 10px; border-radius:10px; background:{PANEL};"
            f" border:1px dashed {ACCENT}; color:#dfe4ec; font-size:11px;"
        )
        right.addWidget(self.tips_box)
        right.addWidget(QLabel("Medio de pago"))
        right.addWidget(self.mpago)
        right.addWidget(btn_resumen)
        right.addWidget(btn_kiosk)
        right.addWidget(btn_bonus)
        right.addWidget(btn_clear)
        right.addWidget(btn_info)
        right.addWidget(btn_export)
        right.addWidget(btn_cobrar)
        right_widget = QWidget(); right_widget.setLayout(right)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(center_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        root = QHBoxLayout(self)
        root.addWidget(splitter)

        self.setStyleSheet(f"QWidget {{ background:{BG}; color:#e0e5ec; }}")

        # Conectar señales después de crear todo
        self.cat_list.currentTextChanged.connect(self.apply_filters)
        self.cat_list.setCurrentRow(0)
        self.render_products(self.prods)
        self.refresh_ticket()
        self.ensure_daily_backup()
        if self.prods_errors:
            self.show_validation_errors(self.prods_errors)
        self.setup_shortcuts()
        if self.kiosk_enabled:
            self.apply_kiosk_mode()

    # ---- Render y filtros ----
    def apply_filters(self):
        cat = self.cat_list.currentItem().text() if self.cat_list.currentItem() else "Todas"
        text = self.search.text().strip().lower() if hasattr(self, "search") else ""

        items = self.prods
        if cat != "Todas":
            items = [p for p in items if p["categoria"] == cat]
        if text:
            items = [p for p in items if text in p["item_desc"].lower() or text in p["categoria"].lower()]
        self.render_products(items)

    def render_products(self, items):
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w: w.setParent(None)
        cols = 3
        for idx, p in enumerate(items):
            r, c = divmod(idx, cols)
            self.grid.addWidget(ProductCard(p, self.add_item), r, c)

    def setup_shortcuts(self):
        mappings = [
            ("Ctrl+Enter", self.checkout),
            ("Ctrl+Return", self.checkout),
            ("Ctrl+E", self.export_excel),
            ("Ctrl+R", self.manual_daily_summary),
            ("Ctrl+L", self.focus_code_input),
            ("F1", self.show_help_info),
            ("F2", self.toggle_kiosk),
            ("Esc", self.exit_kiosk_if_needed),
        ]
        for seq, handler in mappings:
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(handler)
            self.shortcuts.append(sc)

    def show_help_info(self):
        lines = [
            "Atajos disponibles:",
            "- Ctrl+Enter / Ctrl+Return: Cobrar",
            "- Ctrl+E: Exportar a Excel",
            "- Ctrl+R: Resumen diario",
            "- Ctrl+L: Enfocar el campo Codigo rapido",
            "- F1: Ver atajos y ayuda general",
            "- F2: Alternar modo kiosco",
            "- Esc: Salir de kiosco o cancelar pantalla completa",
            "",
            "Tips rapidos:",
            "- Usa el campo 'Codigo rapido' para cargar productos por ID o ID*3 y presiona Enter.",
            "- Activa el modo kiosco para trabajar en pantalla completa durante la atencion.",
        ]
        QMessageBox.information(self, "Atajos y ayuda", "\n".join(lines))

    def closeEvent(self, event):
        log_event("Sesion POS finalizada.")
        super().closeEvent(event)

    def focus_code_input(self):
        self.code_input.setFocus()
        self.code_input.selectAll()

    def handle_code_entry(self):
        raw = self.code_input.text().strip()
        if not raw:
            return
        self.code_input.clear()
        qty = 1
        code = raw
        for sep in ("*", "x", "X"):
            if sep in raw:
                left, right = raw.split(sep, 1)
                code = left.strip()
                try:
                    qty = max(1, int(right.strip()))
                except Exception:
                    qty = 1
                break
        prod = next((p for p in self.prods if p["item_id"].lower() == code.lower()), None)
        if not prod:
            self.set_status(f"Codigo {code} no encontrado.", "warning")
            return
        self.add_item(prod, qty, keep_status=True)
        self.set_status(f"{qty} x {prod['item_desc']} agregado por codigo.", "success")

    def toggle_kiosk(self):
        self.set_kiosk_state(not self.kiosk_enabled)

    def set_kiosk_state(self, state: bool):
        self.kiosk_enabled = bool(state)
        self.btn_kiosk.setChecked(self.kiosk_enabled)
        self.settings.setValue("kiosk_enabled", self.kiosk_enabled)
        self.apply_kiosk_mode()

    def exit_kiosk_if_needed(self):
        if self.kiosk_enabled:
            self.set_kiosk_state(False)

    def apply_kiosk_mode(self):
        if self.kiosk_enabled:
            self.showFullScreen()
            self.setCursor(Qt.ArrowCursor)
            self.set_status("Modo kiosco activo (F2 para salir).", "info")
        else:
            self.showNormal()
            self.setCursor(Qt.ArrowCursor)
            self.set_status("Modo kiosco desactivado.", "info")

    # ---- Ticket ----
    def add_item(self, prod, cant, keep_status=False):
        for it in self.ticket:
            if it["prod"]["item_id"] == prod["item_id"]:
                it["cant"] += cant
                self.refresh_ticket(keep_status=keep_status)
                self.flash_ticket()
                return
        self.ticket.append({"prod": prod, "cant": cant, "discount": 0.0})
        self.refresh_ticket(keep_status=keep_status)
        self.flash_ticket()

    def ticket_entries(self):
        entries = []
        subtotal = 0.0
        for it in self.ticket:
            discount = max(0.0, float(it.get("discount", 0.0)))
            prod = it["prod"]
            base_price = float(prod["precio"])
            net_unit = base_price * (1 - discount / 100)
            line_total = net_unit * it["cant"]
            subtotal += line_total
            entries.append(
                {
                    "prod": prod,
                    "cant": it["cant"],
                    "discount": discount,
                    "unit_price": net_unit,
                    "line_total": line_total,
                }
            )
        global_discount = subtotal * (self.ticket_discount / 100)
        total = subtotal - global_discount
        return entries, subtotal, global_discount, total

    def refresh_ticket(self, keep_status=False):
        self.ticket_list.clear()
        entries, subtotal, global_disc, total = self.ticket_entries()
        for entry in entries:
            prod = entry["prod"]
            label = f"{entry['cant']} x {prod['item_desc']}"
            if entry["discount"]:
                label += f" (-{entry['discount']:.2f}%)"
            label += f"  ->  ${entry['line_total']:,.2f}"
            self.ticket_list.addItem(label)
        if self.ticket_discount and subtotal:
            self.ticket_list.addItem(
                f"Descuento ticket {self.ticket_discount:.2f}%  ->  -${global_disc:,.2f}"
            )
        self.total_lbl.setText(f"Total: ${total:,.2f}")
        if not keep_status:
            self.update_ticket_status(total)

    def update_ticket_status(self, total):
        if not self.ticket:
            self.set_status("Ticket vacio. Agrega productos para cobrar.", "info")
            return
        items = sum(it["cant"] for it in self.ticket)
        self.set_status(f"Ticket con {items} items. Total ${total:,.2f}", "info")

    def flash_ticket(self):
        highlight = (
            "QListWidget {"
            f" background:{PANEL};"
            " color:#f1f2f5;"
            " border:1px solid #ffd166;"
            " border-radius:12px; padding:10px; }"
            "QListWidget::item { padding:6px 2px; }"
        )
        self.ticket_list.setStyleSheet(highlight)
        QTimer.singleShot(200, lambda: self.ticket_list.setStyleSheet(self.ticket_base_style))

    def show_ticket_menu(self, pos):
        item = self.ticket_list.itemAt(pos)
        if not item:
            return
        row = self.ticket_list.row(item)
        menu = QMenu(self)
        edit_action = menu.addAction("Editar cantidad")
        discount_action = menu.addAction("Bonificar item")
        delete_action = menu.addAction("Quitar item")
        chosen = menu.exec(self.ticket_list.viewport().mapToGlobal(pos))
        if chosen == edit_action:
            self.edit_ticket_row(row)
        elif chosen == discount_action:
            self.prompt_item_discount(row=row)
        elif chosen == delete_action:
            self.delete_ticket_row(row)

    def edit_ticket_row(self, row):
        if row < 0 or row >= len(self.ticket):
            return
        entry = self.ticket[row]
        prod = entry["prod"]
        current = entry["cant"]
        qty, ok = QInputDialog.getInt(
            self,
            "Editar cantidad",
            f"Cantidad para {prod['item_desc']}",
            value=current,
            minValue=1,
            maxValue=999,
        )
        if ok and qty != current:
            entry["cant"] = qty
            self.refresh_ticket()
            self.set_status(f"Cantidad actualizada: {prod['item_desc']} x {qty}.", "success")

    def delete_ticket_row(self, row):
        if row < 0 or row >= len(self.ticket):
            return
        prod = self.ticket[row]["prod"]
        del self.ticket[row]
        self.refresh_ticket()
        self.set_status(f"{prod['item_desc']} eliminado del ticket.", "info")

    def clear_ticket(self):
        if not self.ticket:
            self.set_status("El ticket ya esta vacio.", "info")
            return
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Limpiar ticket")
        confirm.setIcon(QMessageBox.Question)
        confirm.setText("Esto quitara todos los productos del ticket actual. Continuar?")
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setDefaultButton(QMessageBox.No)
        confirm.button(QMessageBox.Yes).setText("Sí")
        confirm.button(QMessageBox.No).setText("No")
        if confirm.exec() == QMessageBox.Yes:
            self.ticket.clear()
            self.ticket_discount = 0.0
            self.refresh_ticket()
            self.set_status("Ticket limpiado. Puedes comenzar de nuevo.", "info")

    def manage_discounts(self):
        if not self.ticket:
            QMessageBox.information(self, "Bonificaciones", "Agrega productos al ticket antes de aplicar descuentos.")
            return
        menu = QMenu(self)
        act_global = menu.addAction("Descuento general (%)")
        act_item = menu.addAction("Descuento por item (%)")
        act_clear = menu.addAction("Quitar todos los descuentos")
        pos = self.btn_bonus.mapToGlobal(self.btn_bonus.rect().bottomLeft())
        chosen = menu.exec(pos)
        if chosen == act_global:
            self.prompt_global_discount()
        elif chosen == act_item:
            self.prompt_item_discount()
        elif chosen == act_clear:
            self.reset_discounts()

    def prompt_global_discount(self):
        pct, ok = self.prompt_percentage(
            title="Descuento general",
            label="Porcentaje a aplicar sobre el total:",
            initial=self.ticket_discount,
        )
        if ok:
            self.ticket_discount = pct
            self.refresh_ticket()
            if pct:
                self.set_status(f"Descuento general aplicado: {pct:.2f}%.", "success")
            else:
                self.set_status("Descuento general eliminado.", "info")

    def prompt_item_discount(self, row=None):
        if not self.ticket:
            return
        if row is None:
            options = [f"{idx+1}. {it['prod']['item_desc']} (x{it['cant']})" for idx, it in enumerate(self.ticket)]
            choice, ok = QInputDialog.getItem(
                self,
                "Descuento por item",
                "Elegir producto:",
                options,
                0,
                False,
            )
            if not ok:
                return
            row = options.index(choice)
        if row < 0 or row >= len(self.ticket):
            return
        current = float(self.ticket[row].get("discount", 0.0))
        pct, ok = self.prompt_percentage(
            title="Descuento por item",
            label="Porcentaje a aplicar (0 para quitar):",
            initial=current,
        )
        if ok:
            self.ticket[row]["discount"] = pct
            self.refresh_ticket()
            if pct:
                self.set_status(f"Descuento {pct:.2f}% aplicado a {self.ticket[row]['prod']['item_desc']}.", "success")
            else:
                self.set_status("Descuento del item eliminado.", "info")

    def reset_discounts(self):
        changed = bool(self.ticket_discount or any(it.get("discount") for it in self.ticket))
        self.ticket_discount = 0.0
        for it in self.ticket:
            it["discount"] = 0.0
        self.refresh_ticket()
        if changed:
            self.set_status("Todos los descuentos fueron quitados.", "info")

    def prompt_percentage(self, title, label, initial, min_value=0.0, max_value=100.0):
        dialog = QInputDialog(self)
        dialog.setWindowTitle(title)
        dialog.setLabelText(label)
        dialog.setInputMode(QInputDialog.DoubleInput)
        dialog.setDoubleDecimals(2)
        dialog.setDoubleRange(min_value, max_value)
        dialog.setDoubleValue(float(initial))
        dialog.setOkButtonText("Aceptar")
        dialog.setCancelButtonText("Cancelar")
        accepted = dialog.exec() == QDialog.Accepted
        return dialog.doubleValue(), accepted

    def set_status(self, message, level="info"):
        colors = {
            "info": "#9fc5ff",
            "success": "#7feaae",
            "warning": "#ffd479",
            "error": "#ff8b8b",
        }
        color = colors.get(level, colors["info"])
        self.status_lbl.setText(message)
        self.status_lbl.setStyleSheet(
            f"padding:8px; border-radius:10px; background:{PANEL}; border:1px solid #22262c; "
            f"color:{color}; font-weight:600;"
        )

    def show_validation_errors(self, errors):
        preview = "\n".join(errors[:5])
        if len(errors) > 5:
            preview += f"\n... ({len(errors) - 5} filas mas)"
        log_error("Productos invalidos detectados al cargar CSV:\n" + preview)
        QMessageBox.warning(
            self,
            "Productos invalidos",
            "Se omitieron productos por datos incompletos:\n\n" + preview
        )
        self.set_status("Productos invalidos fueron omitidos del menu.", "warning")

    def ticket_total(self):
        *_, total = self.ticket_entries()
        return total

    def refresh_sales_target(self, force=False):
        period = datetime.datetime.now().strftime("%Y-%m")
        if force or self.sales_path is None or period != self.current_period:
            self.sales_path = current_sales_path()
            self.current_period = period
            self.ticket_id = last_ticket_id_from_csv(self.sales_path)
            if not force:
                self.set_status(
                    f"Nuevo periodo detectado ({period}). Ticket #{self.ticket_id:06d}",
                    "info",
                )
        self.check_day_rollover()

    def ensure_daily_backup(self, notify=True):
        if not self.sales_path or not self.sales_path.exists():
            return
        today = datetime.date.today().strftime("%Y-%m-%d")
        stats = self.sales_path.stat()
        signature = f"{self.sales_path.name}-{today}-{stats.st_mtime_ns}"
        if self.last_backup_signature == signature:
            return
        backup_file = BACKUP_DIR / f"{self.sales_path.stem}_{today}.csv"
        existed = backup_file.exists()
        try:
            shutil.copy2(self.sales_path, backup_file)
            self.last_backup_signature = signature
            if notify:
                action = "actualizado" if existed else "creado"
                self.set_status(f"Backup diario {action} ({backup_file.name}).", "info")
        except Exception as exc:
            log_error("Error creando backup diario.", exc)
            self.set_status("No se pudo crear el backup diario.", "warning")

    def check_day_rollover(self):
        today = datetime.date.today()
        if self.current_day is None:
            self.current_day = today
            return
        if today != self.current_day:
            previous = self.current_day
            self.current_day = today
            ok, detail = self.generate_daily_summary(previous, mode="auto")
            if ok:
                self.set_status(f"Resumen automatico de {previous} generado.", "success")
            else:
                self.set_status(f"Resumen automatico pendiente: {detail}", "warning")

    def manual_daily_summary(self):
        ok, detail = self.generate_daily_summary(datetime.date.today(), mode="manual")
        if ok:
            QMessageBox.information(self, "Resumen diario", f"Generado en:\n{detail}")
            self.set_status(f"Resumen manual creado ({Path(detail).name}).", "success")
        else:
            QMessageBox.warning(self, "Resumen diario", detail)
            self.set_status(detail, "warning")

    def generate_daily_summary(self, target_date: datetime.date, mode="auto"):
        if target_date is None:
            return False, "Fecha invalida."
        today = datetime.date.today()
        if mode == "auto" and target_date >= today:
            return False, "El resumen automatico se genera al cierre del dia."
        sales_csv = sales_path_for_date(target_date)
        if not sales_csv.exists():
            return False, f"No hay ventas registradas para {target_date}."

        rows = []
        with open(sales_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    row_date = datetime.datetime.strptime(row["fecha_hora"], "%Y-%m-%d %H:%M:%S").date()
                except Exception:
                    continue
                if row_date == target_date:
                    rows.append(row)
        if not rows:
            return False, f"No se encontraron ventas el {target_date}."

        totals_by_cat = {}
        totals_by_pay = {}
        tickets = set()
        total_amount = 0.0
        total_items = 0
        for row in rows:
            try:
                subtotal = float(row.get("subtotal", 0) or 0)
            except Exception:
                subtotal = 0.0
            try:
                qty = int(row.get("cantidad", 0) or 0)
            except Exception:
                qty = 0
            categoria = row.get("categoria", "Sin categoria") or "Sin categoria"
            totals_by_cat[categoria] = totals_by_cat.get(categoria, 0.0) + subtotal
            medio = row.get("medio_pago", "N/D") or "N/D"
            totals_by_pay[medio] = totals_by_pay.get(medio, 0.0) + subtotal
            tickets.add(row.get("ticket_id"))
            total_amount += subtotal
            total_items += qty

        try:
            import pandas as pd
        except Exception:
            return False, "Instala pandas y openpyxl para generar el resumen."

        df = pd.DataFrame(rows)
        df["subtotal"] = pd.to_numeric(df.get("subtotal"), errors="coerce").fillna(0.0)
        df["cantidad"] = pd.to_numeric(df.get("cantidad"), errors="coerce").fillna(0)
        if "categoria" not in df:
            df["categoria"] = "Sin categoria"
        else:
            df["categoria"] = df["categoria"].fillna("Sin categoria")
        if "medio_pago" not in df:
            df["medio_pago"] = "N/D"
        else:
            df["medio_pago"] = df["medio_pago"].fillna("N/D")

        meta = pd.DataFrame(
            [
                ("fecha", target_date.isoformat()),
                ("tickets", len(tickets)),
                ("items", int(df["cantidad"].sum())),
                ("total", float(df["subtotal"].sum())),
            ],
            columns=["metrica", "valor"],
        )
        cat_df = df.groupby("categoria")[["subtotal"]].sum().reset_index()
        pay_df = df.groupby("medio_pago")[["subtotal"]].sum().reset_index()

        base_name = f"resumen_{target_date:%Y-%m-%d}_{mode}"
        xlsx_path = SUMMARY_DIR / f"{base_name}.xlsx"
        existed = xlsx_path.exists()

        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            meta.to_excel(writer, index=False, sheet_name="Resumen")
            cat_df.to_excel(writer, index=False, sheet_name="Por categoria")
            pay_df.to_excel(writer, index=False, sheet_name="Por medio")
            df.to_excel(writer, index=False, sheet_name="Detalle")

        log_error(
            f"Resumen diario {mode} generado para {target_date}: {xlsx_path} "
            f"({'actualizado' if existed else 'nuevo'})"
        )
        return True, str(xlsx_path)

    def print_ticket(self, ticket_label: str, items_snapshot, total, medio):
        try:
            import win32print
        except Exception:
            log_error(f"Impresion no disponible para ticket #{ticket_label}: falta pywin32.")
            return False

        try:
            printer = PRINTER_NAME or win32print.GetDefaultPrinter()
        except Exception as exc:
            log_error(f"No se pudo resolver la impresora predeterminada para ticket #{ticket_label}.", exc)
            return False

        line_width = 40

        def wrap_line(text=""):
            return (text or "")[:line_width]

        border = "-" * line_width
        divider = "-" * line_width

        def format_line(item):
            desc = item["desc"]
            qty = item["cant"]
            subtotal = item["subtotal"]
            text = f"{qty:>2} x {desc:.26}"
            discount = float(item.get("discount") or 0.0)
            if discount:
                text += f" (-{discount:.2f}%)"
            return f"{text} ${subtotal:>7.2f}"

        lines = [
            border,
            wrap_line("Cafeteria POS"),
            wrap_line(f"Ticket #{ticket_label}"),
            wrap_line(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
            wrap_line(f"Pago: {medio}"),
            divider,
        ]
        for item in items_snapshot:
            lines.append(wrap_line(format_line(item)))
        lines.extend(
            [
                divider,
                wrap_line(f"TOTAL: ${total:,.2f}"),
                wrap_line(),
                wrap_line("Gracias por su compra!"),
                border,
            ]
        )
        content = "\r\n".join(lines) + "\r\n\r\n"
        payload = content.encode("utf-8")
        if CUT_COMMAND:
            payload += CUT_COMMAND

        if printer and "pdf" in printer.lower():
            pdf_path = Path.home() / "Documents" / f"Ticket_{ticket_label}.pdf"
            try:
                write_text_pdf(pdf_path, lines, title=f"Ticket {ticket_label}")
                self.set_status(f"Ticket guardado en {pdf_path}.", "info")
                return True
            except Exception as exc:
                log_error(f"No se pudo generar PDF para ticket #{ticket_label}.", exc)
                return False

        try:
            handle = win32print.OpenPrinter(printer)
            job = win32print.StartDocPrinter(handle, 1, ("Ticket Camelia", None, "RAW"))
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, payload)
            win32print.EndPagePrinter(handle)
            win32print.EndDocPrinter(handle)
            win32print.ClosePrinter(handle)
            return True
        except Exception as exc:
            log_error(f"Error al imprimir ticket #{ticket_label} en {printer}.", exc)
            try:
                win32print.ClosePrinter(handle)
            except Exception:
                pass
            return False

    def confirm_checkout(self, total, medio):
        entries, _, global_disc, _ = self.ticket_entries()
        lines = []
        for entry in entries:
            txt = f"{entry['cant']} x {entry['prod']['item_desc']}"
            if entry["discount"]:
                txt += f" (-{entry['discount']:.2f}%)"
            lines.append(txt)
        if self.ticket_discount and global_disc:
            lines.append(f"Descuento ticket {self.ticket_discount:.2f}% (-${global_disc:,.2f})")
        if len(lines) > 5:
            extra = len(lines) - 5
            lines = lines[:5] + [f"... ({extra} items mas)"]
        details = "\n".join(lines)

        confirm = QMessageBox(self)
        confirm.setWindowTitle("Confirmar cobro")
        confirm.setIcon(QMessageBox.Question)
        confirm.setText(f"Ticket #{self.ticket_id:06d}\nTotal: ${total:,.2f}\nMedio: {medio}")
        if details:
            confirm.setInformativeText(details)
        confirm.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        confirm.setDefaultButton(QMessageBox.Ok)
        confirm.button(QMessageBox.Ok).setText("Confirmar")
        confirm.button(QMessageBox.Cancel).setText("Cancelar")
        return confirm.exec() == QMessageBox.Ok

    # ---- Acciones ----
    def checkout(self):
        if not self.ticket:
            QMessageBox.information(self, "Cobrar", "No hay productos en el ticket.")
            self.set_status("No hay productos en el ticket.", "warning")
            return

        self.refresh_sales_target()

        inval = [it for it in self.ticket if not it["prod"]["item_desc"].strip() or it["prod"]["precio"] <= 0]
        if inval:
            names = ", ".join(it["prod"].get("item_desc", "N/D") or "N/D" for it in inval)
            log_error(f"Intento de cobro con productos invalidos: {names}")
            QMessageBox.critical(
                self,
                "Datos invalidos",
                "Hay productos sin descripcion o con precio 0.\nRevisar el CSV antes de continuar."
            )
            self.set_status("Hay productos invalidos en el ticket. Revisar CSV.", "error")
            return

        path = self.sales_path or current_sales_path()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        medio = self.mpago.currentText() if hasattr(self, "mpago") else "Efectivo"
        entries, subtotal, global_disc, total = self.ticket_entries()

        if not self.confirm_checkout(total, medio):
            return

        ticket_snapshot = [
            {
                "item_id": entry["prod"]["item_id"],
                "categoria": entry["prod"]["categoria"],
                "desc": entry["prod"]["item_desc"],
                "cant": entry["cant"],
                "unit_price": entry["unit_price"],
                "subtotal": entry["line_total"],
                "discount": entry["discount"],
            }
            for entry in entries
        ]
        if self.ticket_discount and subtotal:
            ticket_snapshot.append(
                {
                    "item_id": "DESC_TICKET",
                    "categoria": "Descuentos",
                    "desc": "Descuento ticket",
                    "cant": 1,
                    "unit_price": -global_disc,
                    "subtotal": -global_disc,
                    "discount": self.ticket_discount,
                }
            )

        try:
            ticket_label = f"{self.ticket_id:06d}"
            with open(path, "a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                for item in ticket_snapshot:
                    w.writerow(
                        [
                            now,
                            ticket_label,
                            item["item_id"],
                            item["desc"],
                            item["categoria"],
                            item["cant"],
                            f"{item['unit_price']:.2f}",
                            f"{item['subtotal']:.2f}",
                            medio,
                            "Cajero",
                            "",
                        ]
                    )
                f.flush()
                os.fsync(f.fileno())

            self.ticket_id += 1
            self.ticket = []
            self.ticket_discount = 0.0
            self.refresh_ticket(keep_status=True)
            QMessageBox.information(self, "Cobrar", "Venta registrada y guardada.")
            self.set_status(f"Venta #{ticket_label} registrada correctamente.", "success")
            log_event(f"Venta #{ticket_label} cobrada. Total ${total:,.2f} via {medio}.")
            self.ensure_daily_backup(notify=False)
            printed = self.print_ticket(ticket_label, ticket_snapshot, total, medio)
            if not printed:
                self.set_status("Ticket guardado, pero no se pudo imprimir.", "warning")
        except Exception as e:
            log_error(f"Error al guardar ticket #{self.ticket_id:06d}.", e)
            self.set_status("Error al guardar la venta. Revisar logs.", "error")
            QMessageBox.critical(self, "Cobrar", f"Error al guardar:\n{e}")

    def export_excel(self):
        try:
            import pandas as pd
        except Exception:
            QMessageBox.warning(self, "Exportar", "Necesitas instalar pandas y openpyxl.\n\npip install pandas openpyxl")
            self.set_status("Instala pandas y openpyxl para exportar a Excel.", "warning")
            return

        self.refresh_sales_target()
        src = self.sales_path or current_sales_path()
        if not src.exists():
            QMessageBox.information(self, "Exportar", "No hay ventas del mes para exportar.")
            self.set_status("No hay ventas del mes para exportar.", "info")
            return

        suggested = src.with_suffix(".xlsx")
        dest_path, _ = QFileDialog.getSaveFileName(self, "Guardar Excel", str(suggested), "Excel (*.xlsx)")
        if not dest_path:
            return

        try:
            df = pd.read_csv(src, encoding="utf-8")
            with pd.ExcelWriter(dest_path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Ventas")
                try:
                    resumen = df.groupby("categoria")[["subtotal"]].sum().reset_index()
                    resumen.to_excel(writer, index=False, sheet_name="Resumen por categoria")
                except Exception:
                    pass
            QMessageBox.information(self, "Exportar", f"Exportado a:\n{dest_path}")
            self.set_status(f"Ventas exportadas a {dest_path}.", "success")
            log_event(f"Export de ventas generado en {dest_path}.")
        except Exception as e:
            log_error("Error exportando a Excel.", e)
            self.set_status("Error exportando a Excel. Revisar logs.", "error")
            QMessageBox.critical(self, "Exportar", f"Error exportando:\n{e}")

# --- Entry point ---
if __name__ == "__main__":
    install_exception_logger()
    try:
        app = QApplication(sys.argv)
        w = POS()
        w.resize(1200, 720)
        w.show()
        sys.exit(app.exec())
    except Exception as exc:
        log_error("Fallo fatal al iniciar la aplicacion.", exc)
        raise
