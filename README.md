# Cafetería POS

Sistema de gestión de pedidos para cafeterías pequeñas.  
Aplicación de escritorio desarrollada en **Python + PySide6**, con persistencia en archivos CSV mensuales y exportación a Excel.

---

## 🚀 Características actuales

- Interfaz gráfica moderna y simple.
- Menú de categorías (vertical) con grilla de productos con imágenes.
- Ticket con cálculo automático de totales.
- Persistencia de ventas en archivo CSV mensual.
- Exportación a Excel (.xlsx) con hoja de resumen por categoría.
- Selección de medio de pago.
- IDs de ticket continuos entre sesiones.
- Ejecutable portable (PyInstaller).

---

## 🧩 Estructura del proyecto

```
app/
│
├── main.py
├── data/
│   ├── productos.csv
│   └── historial/
│       └── ventas_YYYY-MM.csv
└── assets/
    ├── cafe_chico.jpg
    └── medialunas.jpg
```

---

## 🛠️ Instalación y ejecución

1. Instalar dependencias:

```bash
pip install PySide6 pandas openpyxl pillow
```

2. Ejecutar:

```bash
python main.py
```

3. (Opcional) Empaquetar a `.exe`:

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --add-data "data;data" --add-data "assets;assets" main.py
```

---

## 🧠 Posibles features futuras

- ✅ Reportes avanzados (por día, medio de pago, cajero, etc.).  
- ✅ Impresión de tickets (PDF o impresora térmica).  
- ✅ Control de stock básico.  
- ✅ Soporte multiusuario / roles (admin, cajero).  
- ✅ Resumen automático al cierre de día.  
- ✅ Importar/exportar datos históricos (para backups).  
- ✅ Modo “borrador” de ticket (autosave y recuperación tras cierre inesperado).  
- ✅ Atajos de teclado y lector de código de barras.  
- ✅ Interfaz touch optimizada.  
- ✅ Modo “Kiosco” pantalla completa.

---

## 🟢 Features recomendadas para salida a producción (MVP)

1. **Confirmación de cobro** antes de registrar la venta.  
2. **Logs de errores** (archivo `logs.txt` con traceback).  
3. **Validación de precios y productos** antes de guardar (no vacíos, no 0).  
4. **Control de mes** automático (archivos por mes se crean solos).  
5. **Backup automático diario** del CSV actual.  
6. **Mensaje de éxito/error** siempre visible (feedback visual al cajero).  
7. **Protección ante cierre accidental** (flush+fsync ya implementado).

---

## ⚠️ Posibles fallos actuales y limitaciones

| Situación | Comportamiento actual | Riesgo / mejora posible |
|------------|----------------------|--------------------------|
| Corte de energía durante escritura | Puede truncar última línea si no terminó el fsync | Mitigado con flush/fsync, pero no 100 % garantizado |
| CSV manualmente editado | Si se cambian encabezados o tipos, el export a Excel puede fallar | Validar CSV antes de leer |
| Productos sin imagen | Muestra botón vacío | OK visual, pero confunde |
| Múltiples usuarios abriendo la app al mismo tiempo | Pueden pisarse al escribir CSV | No soportado aún |
| Rutas con caracteres raros | Puede fallar en Windows | Normalizar paths |
| Ticket vacío y se presiona Cobrar | Mensaje, pero no bloquea ticket_id | Menor |
| No hay rollback si se interrumpe entre filas | Se guardan parciales | Añadir confirmación por ticket |
| Excel abierto mientras se intenta exportar | Falla de permiso | Capturado con error |
| Faltan backups automáticos | Depende del usuario hacerlos | Agregar backup diario |
| Ticket ID se basa en archivo mensual | Reinicia cada mes | Correcto, pero documentar comportamiento |

---

## 📋 Licencia y créditos

Desarrollado como prototipo para gestión de caja en cafetería local.  
Autor: *[Diego Méndez]*  
Versión: **MVP 0.9**
