# main.py
import sys, os, csv, datetime, traceback, shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QListWidget, QListWidgetItem, QLineEdit, QScrollArea, QFileDialog,
    QMessageBox, QSplitter, QComboBox
)

# --- Rutas base ---
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
PRODS_CSV  = DATA_DIR / "productos.csv"
LOG_FILE   = BASE_DIR / "logs.txt"
BACKUP_DIR = DATA_DIR / "historial" / "backups"


def ensure_log_file():
    """Crea logs.txt vacío si aún no existe (para que el staff lo ubique)."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not LOG_FILE.exists():
            with open(LOG_FILE, "w", encoding="utf-8") as log:
                log.write("=== Cafeteria POS logs ===\n")
    except Exception:
        pass


def log_error(message: str, exc: Exception | None = None):
    """Persist simple timestamped logs for soporte."""
    try:
        ensure_log_file()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"[{timestamp}] {message}\n")
            if exc:
                log.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            log.write("\n")
    except Exception:
        # No hacemos nada si fallan los logs para no romper el flujo principal.
        pass

# --- Utilidades de datos ---
def ensure_dirs():
    hist_dir = DATA_DIR / "historial"
    hist_dir.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

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
                background: #3a3a3a; color: #eee;
            }
            QPushButton:hover { background: #505050; }
        """)
        v = QVBoxLayout(self)
        img_path = prod.get("imagen", "")
        if img_path and Path(img_path).exists():
            pix = QPixmap(str(img_path)).scaled(160, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl = QLabel(); lbl.setPixmap(pix); lbl.setAlignment(Qt.AlignCenter)
            v.addWidget(lbl, alignment=Qt.AlignCenter)
        name = QLabel(prod["item_desc"])
        price = QLabel(f"${prod['precio']:,.2f}")
        v.addWidget(name); v.addWidget(price)
        self.clicked.connect(lambda: on_add(prod, 1))

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
            "padding:8px; border-radius:8px; background:#252525; color:#d0d0d0;"
        )
        self.sales_path = None
        self.current_period = None
        self.last_backup_signature = None
        self.refresh_sales_target(force=True)

        # ----- Buscador (definido ANTES de señales) -----
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar producto…")
        self.search.textChanged.connect(self.apply_filters)
        self.search.setStyleSheet("""
            QLineEdit {
                background:#1f1f1f; color:#ddd; border:1px solid #7a2cff;
                border-radius:8px; padding:8px;
            }
        """)

        # ----- Sidebar de categorías -----
        self.categories = ["Todas"] + sorted({p["categoria"] for p in self.prods})
        self.cat_list = QListWidget()
        for c in self.categories:
            QListWidgetItem(c, self.cat_list)
        self.cat_list.setFixedWidth(200)
        self.cat_list.setSelectionMode(QListWidget.SingleSelection)
        self.cat_list.setStyleSheet("""
            QListWidget { background:#272727; color:#ddd; border:0; }
            QListWidget::item { padding:10px; margin:6px; border-radius:10px; }
            QListWidget::item:selected { background:#585858; color:white; }
        """)

        # ----- Grilla de productos (scroll) -----
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)

        grid_wrap = QWidget(); grid_wrap.setLayout(self.grid)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(grid_wrap)
        scroll.setStyleSheet("QScrollArea { background:#202020; border:0; }")

        # ----- Ticket / derecha -----
        self.ticket_list = QListWidget()
        self.ticket_list.setStyleSheet("""
            QListWidget { background:#2b2b2b; color:#e6e6e6; border:1px solid #3a3a3a; border-radius:8px; }
        """)

        self.mpago = QComboBox()
        self.mpago.addItems(["Efectivo", "Tarjeta", "QR", "Debito"])

        self.total_lbl = QLabel("Total: $0.00")
        self.total_lbl.setAlignment(Qt.AlignRight)
        self.total_lbl.setStyleSheet("color:#ddd; padding:8px;")

        btn_cobrar = QPushButton("Cobrar"); btn_cobrar.clicked.connect(self.checkout)
        btn_export = QPushButton("Exportar a Excel"); btn_export.clicked.connect(self.export_excel)
        for b in (btn_cobrar, btn_export):
            b.setMinimumHeight(36)
            b.setStyleSheet(
                "QPushButton { background:#7a2cff; color:white; border:0; border-radius:8px; padding:8px; }"
                "QPushButton:hover { background:#8b49ff; }"
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
        right.addWidget(self.status_lbl)
        right.addWidget(QLabel("Medio de pago"))
        right.addWidget(self.mpago)
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

        self.setStyleSheet("QWidget { background:#1b1b1b; color:#e0e0e0; }")

        # Conectar señales después de crear todo
        self.cat_list.currentTextChanged.connect(self.apply_filters)
        self.cat_list.setCurrentRow(0)
        self.render_products(self.prods)
        self.refresh_ticket()
        self.ensure_daily_backup()
        if self.prods_errors:
            self.show_validation_errors(self.prods_errors)

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
        cols = 4
        for idx, p in enumerate(items):
            r, c = divmod(idx, cols)
            self.grid.addWidget(ProductCard(p, self.add_item), r, c)

    # ---- Ticket ----
    def add_item(self, prod, cant):
        for it in self.ticket:
            if it["prod"]["item_id"] == prod["item_id"]:
                it["cant"] += cant
                self.refresh_ticket()
                return
        self.ticket.append({"prod": prod, "cant": cant})
        self.refresh_ticket()

    def refresh_ticket(self, keep_status=False):
        self.ticket_list.clear()
        total = 0.0
        for it in self.ticket:
            p, c = it["prod"], it["cant"]
            st = p["precio"] * c
            total += st
            self.ticket_list.addItem(f"{c} x {p['item_desc']}  ->  ${st:,.2f}")
        self.total_lbl.setText(f"Total: ${total:,.2f}")
        if not keep_status:
            self.update_ticket_status(total)

    def update_ticket_status(self, total):
        if not self.ticket:
            self.set_status("Ticket vacio. Agrega productos para cobrar.", "info")
            return
        items = sum(it["cant"] for it in self.ticket)
        self.set_status(f"Ticket con {items} items. Total ${total:,.2f}", "info")

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
            "padding:8px; border-radius:8px; background:#252525; "
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
        return sum(it["prod"]["precio"] * it["cant"] for it in self.ticket)

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

    def confirm_checkout(self, total, medio):
        lines = [f"{it['cant']} x {it['prod']['item_desc']}" for it in self.ticket]
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
        total = self.ticket_total()

        if not self.confirm_checkout(total, medio):
            return

        try:
            ticket_label = f"{self.ticket_id:06d}"
            with open(path, "a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                for it in self.ticket:
                    p, c = it["prod"], it["cant"]
                    st = p["precio"] * c
                    w.writerow([now, ticket_label, p["item_id"], p["item_desc"],
                                p["categoria"], c, p["precio"], st, medio, "Cajero", ""])
                f.flush()
                os.fsync(f.fileno())

            self.ticket_id += 1
            self.ticket = []
            self.refresh_ticket(keep_status=True)
            QMessageBox.information(self, "Cobrar", "Venta registrada y guardada.")
            self.set_status(f"Venta #{ticket_label} registrada correctamente.", "success")
            self.ensure_daily_backup(notify=False)
        except Exception as e:
            log_error("Error al guardar ticket.", e)
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
