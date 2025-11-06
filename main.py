# main.py
import sys, os, csv, datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QListWidget, QListWidgetItem, QListWidget, QLineEdit, QScrollArea, QListWidgetItem,
    QFileDialog, QMessageBox, QSplitter, QComboBox
)

# --- Rutas base ---
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
PRODS_CSV  = DATA_DIR / "productos.csv"

# --- Utilidades de datos ---
def ensure_dirs():
    (DATA_DIR / "historial").mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def bootstrap_products_csv():
    """Crea un productos.csv de ejemplo si no existe."""
    if not PRODS_CSV.exists():
        rows = [
            ["item_id","item_desc","categoria","precio","activo","imagen"],
            ["CAF_CHICO","Café chico","Bebidas","120.00","1", str(ASSETS_DIR / "cafe_chico.jpg")],
            ["MED_2U","Medialunas x2","Panadería","250.00","1", str(ASSETS_DIR / "medialunas.jpg")],
        ]
        with open(PRODS_CSV, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)

def load_products():
    """Lee productos.csv -> lista de dicts."""
    prods = []
    with open(PRODS_CSV, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("activo", "1") == "1":
                try:
                    row["precio"] = float(row["precio"])
                except Exception:
                    row["precio"] = 0.0
                prods.append(row)
    return prods

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
                # ticket_id está en la 2da columna
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
        name = QLabel(prod["item_desc"]); price = QLabel(f"${prod['precio']:,.2f}")
        v.addWidget(name); v.addWidget(price)
        self.clicked.connect(lambda: on_add(prod, 1))

class POS(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cafetería POS")
        self.setWindowIcon(QIcon())
        ensure_dirs()
        bootstrap_products_csv()

        self.prods = load_products()
        self.ticket = []  # lista de {"prod":dict, "cant":int}
        sales_csv = current_sales_path()
        self.ticket_id = last_ticket_id_from_csv(sales_csv)

        # ----- Sidebar de categorías -----
        self.categories = ["Todas"] + sorted({p["categoria"] for p in self.prods})
        self.cat_list = QListWidget()
        for c in self.categories:
            QListWidgetItem(c, self.cat_list)
        self.cat_list.setFixedWidth(200)
        self.cat_list.setSelectionMode(QListWidget.SingleSelection)
        self.cat_list.currentTextChanged.connect(self.apply_filters)
        self.cat_list.setCurrentRow(0)

        self.cat_list.setStyleSheet("""
            QListWidget { background:#272727; color:#ddd; border:0; }
            QListWidget::item { padding:10px; margin:6px; border-radius:10px; }
            QListWidget::item:selected { background:#585858; color:white; }
        """)

        # ----- Buscador -----
        self.search = QLineEdit(); self.search.setPlaceholderText("Buscar producto…")
        self.search.textChanged.connect(self.apply_filters)
        self.search.setStyleSheet("""
            QLineEdit {
                background:#1f1f1f; color:#ddd; border:1px solid #7a2cff;
                border-radius:8px; padding:8px;
            }
        """)

        # ----- Grilla de productos (scroll) -----
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(16); self.grid.setVerticalSpacing(16)

        grid_wrap = QWidget(); grid_wrap.setLayout(self.grid)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(grid_wrap)
        scroll.setStyleSheet("QScrollArea { background:#202020; border:0; }")

        # ----- Ticket / derecha -----
        self.ticket_list = QListWidget()
        self.ticket_list.setStyleSheet("""
            QListWidget { background:#2b2b2b; color:#e6e6e6; border:1px solid #3a3a3a; border-radius:8px; }
        """)
        self.mpago = QComboBox()
        self.mpago.addItems(["Efectivo", "Tarjeta", "QR", "Débito"])
        self.total_lbl = QLabel("Total: $0.00")
        self.total_lbl.setAlignment(Qt.AlignRight)
        self.total_lbl.setStyleSheet("color:#ddd; padding:8px;")

        btn_cobrar = QPushButton("Cobrar"); btn_cobrar.clicked.connect(self.checkout)
        btn_export = QPushButton("Exportar a Excel"); btn_export.clicked.connect(self.export_excel)
        for b in (btn_cobrar, btn_export):
            b.setMinimumHeight(36)
            b.setStyleSheet("QPushButton { background:#7a2cff; color:white; border:0; border-radius:8px; padding:8px; }"
                            "QPushButton:hover { background:#8b49ff; }")

        # ----- Layouts -----
        left_panel = QVBoxLayout(); left_panel.addWidget(self.cat_list)
        left_widget = QWidget(); left_widget.setLayout(left_panel)

        center_panel = QVBoxLayout(); center_panel.addWidget(self.search); center_panel.addWidget(scroll)
        center_widget = QWidget(); center_widget.setLayout(center_panel)

        right = QVBoxLayout()
        right.addWidget(QLabel("Ticket actual"))
        right.addWidget(self.ticket_list, 1)
        right.addWidget(self.total_lbl)
        right.addWidget(QLabel("Medio de pago"))
        right.addWidget(self.mpago)
        right.addWidget(btn_export)
        right.addWidget(btn_cobrar)
        right_widget = QWidget(); right_widget.setLayout(right)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(center_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)  # sidebar
        splitter.setStretchFactor(1, 1)  # grid
        splitter.setStretchFactor(2, 0)  # ticket

        root = QHBoxLayout(self)
        root.addWidget(splitter)

        self.setStyleSheet("QWidget { background:#1b1b1b; color:#e0e0e0; }")
        self.render_products(self.prods)

    # ---- Render y filtros ----
    def apply_filters(self):
        cat = self.cat_list.currentItem().text() if self.cat_list.currentItem() else "Todas"
        text = self.search.text().strip().lower()

        items = self.prods
        if cat != "Todas":
            items = [p for p in items if p["categoria"] == cat]
        if text:
            items = [p for p in items if text in p["item_desc"].lower() or text in p["categoria"].lower()]
        self.render_products(items)

    def render_products(self, items):
        # limpiar grid
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w: w.setParent(None)
        # repintar
        cols = 4
        for idx, p in enumerate(items):
            r, c = divmod(idx, cols)
            self.grid.addWidget(ProductCard(p, self.add_item), r, c)

    # ---- Ticket ----
    def add_item(self, prod, cant):
        # Si ya existe el mismo item, acumula
        for it in self.ticket:
            if it["prod"]["item_id"] == prod["item_id"]:
                it["cant"] += cant
                self.refresh_ticket()
                return
        self.ticket.append({"prod": prod, "cant": cant})
        self.refresh_ticket()

    def refresh_ticket(self):
        self.ticket_list.clear()
        total = 0.0
        for it in self.ticket:
            p, c = it["prod"], it["cant"]
            st = p["precio"] * c
            total += st
            self.ticket_list.addItem(f"{c} x {p['item_desc']}  —  ${st:,.2f}")
        self.total_lbl.setText(f"Total: ${total:,.2f}")

    # ---- Acciones ----
    def checkout(self):
        if not self.ticket:
            QMessageBox.information(self, "Cobrar", "No hay productos en el ticket.")
            return

        path = current_sales_path()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        medio = self.mpago.currentText() if hasattr(self, "mpago") else "Efectivo"

        try:
            # Abrimos en append y forzamos a disco
            with open(path, "a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                for it in self.ticket:
                    p, c = it["prod"], it["cant"]
                    st = p["precio"] * c
                    w.writerow([now, f"{self.ticket_id:06d}", p["item_id"], p["item_desc"],
                                p["categoria"], c, p["precio"], st, medio, "Cajero", ""])
                f.flush()
                os.fsync(f.fileno())

            self.ticket_id += 1
            self.ticket = []
            self.refresh_ticket()
            QMessageBox.information(self, "Cobrar", "Venta registrada y guardada.")
        except Exception as e:
            QMessageBox.critical(self, "Cobrar", f"Error al guardar:\n{e}")


    def export_excel(self):
        """Convierte el CSV del mes a .xlsx con pandas."""
        try:
            import pandas as pd
        except Exception:
            QMessageBox.warning(self, "Exportar", "Necesitás instalar pandas y openpyxl.\n\npip install pandas openpyxl")
            return

        src = current_sales_path()
        if not src.exists():
            QMessageBox.information(self, "Exportar", "No hay ventas del mes para exportar.")
            return

        suggested = src.with_suffix(".xlsx")
        dest_path, _ = QFileDialog.getSaveFileName(self, "Guardar Excel", str(suggested), "Excel (*.xlsx)")
        if not dest_path:
            return

        try:
            df = pd.read_csv(src, encoding="utf-8")
            # opcional: totales por categoría en otra hoja
            with pd.ExcelWriter(dest_path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Ventas")
                try:
                    resumen = df.groupby("categoria")[["subtotal"]].sum().reset_index()
                    resumen.to_excel(writer, index=False, sheet_name="Resumen por categoría")
                except Exception:
                    pass
            QMessageBox.information(self, "Exportar", f"Exportado a:\n{dest_path}")
        except Exception as e:
            QMessageBox.critical(self, "Exportar", f"Error exportando:\n{e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = POS(); w.resize(1200, 720); w.show()
    sys.exit(app.exec())
