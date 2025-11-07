# Cafeteria POS

Sistema de gestion de pedidos para cafeterias pequenas.
Aplicacion de escritorio desarrollada en **Python + PySide6**, con persistencia en archivos CSV mensuales y exportacion a Excel.

---

## Caracteristicas actuales

- Interfaz grafica moderna y simple.
- Menu lateral de categorias con grilla de productos con imagenes.
- Ticket con calculo automatico de totales y seleccion de medio de pago.
- Confirmacion de cobro antes de guardar cada venta.
- Validacion de productos y precios (sin nombres vacios ni valores menores o iguales a 0).
- Control automatico del CSV mensual (detecta cambio de mes y reinicia IDs).
- Persistencia de ventas en archivos CSV mensuales.
- Backup diario del CSV activo en `data/historial/backups`.
- Resumen automatico de fin de dia (Excel) con boton manual.
- Exportacion a Excel (.xlsx) con hoja de resumen por categoria.
- Registro de errores en `logs.txt` (con traceback) para soporte rapido.
- Indicador de estado permanente (exito/error) visible para el cajero.
- Codigo rapido / lector: escribir `ITEM_ID` o `ITEM_ID*3` y Enter.
- Atajos: `Ctrl+Enter` (cobrar), `Ctrl+E` (exportar), `Ctrl+R` (resumen), `Ctrl+L` (codigo rapido).
- IDs de ticket continuos entre sesiones.
- Ejecutable portable (PyInstaller).

---

## Estructura del proyecto

```
app/
+-- main.py
+-- data/
|   +-- productos.csv
|   +-- historial/
|       +-- ventas_YYYY-MM.csv
|       +-- backups/
|           +-- ventas_YYYY-MM-DD.csv
|       +-- resumenes/
|           +-- resumen_YYYY-MM-DD_auto.xlsx
+-- assets/
    +-- cafe_chico.jpg
    +-- medialunas.jpg
```

---

## Instalacion y ejecucion

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
pyinstaller --clean --name Avocado --onefile --noconsole --icon assets/icono.ico --add-data "data;data" --add-data "assets;assets" --version-file version_info.txt main.py
```

4. Logs de errores: se generan automaticamente en `logs.txt` junto al ejecutable (o en la carpeta donde se copie el `.exe`). El archivo queda creado desde el arranque para que el staff lo pueda compartir ante incidentes. Todos los archivos (data/, assets/, backups, resumenes) se crean en la misma carpeta del ejecutable para facilitar su respaldo.

---

## Features recomendadas para salida a produccion (MVP)

1. Confirmacion de cobro antes de registrar la venta (**implementado**).
2. Logs de errores en `logs.txt` (**implementado**).
3. Validacion de precios y productos al leer/guardar (**implementado**).
4. Control de mes automatico (archivos por mes se crean solos) (**implementado**).
5. Backup automatico diario del CSV actual (**implementado**).
6. Mensaje de exito/error siempre visible (feedback visual al cajero) (**implementado**).
7. Resumen automatico al cierre del dia + boton manual (**implementado**).
8. Proteccion ante cierre accidental (flush+fsync ya implementado).

---

## Posibles fallos actuales y limitaciones

| Situacion | Comportamiento actual | Riesgo / mejora posible |
|-----------|----------------------|-------------------------|
| Corte de energia durante escritura | Puede truncar ultima linea si no termino el fsync | Mitigado con flush/fsync, pero no garantiza 100% |
| CSV manualmente editado | Si se cambian encabezados o tipos, el export a Excel puede fallar | Validar CSV antes de leer (en proceso) |
| Productos sin imagen | Muestra boton vacio | OK visual, pero confunde |
| Multiples usuarios abriendo la app al mismo tiempo | Pueden pisarse al escribir CSV | No soportado aun |
| Rutas con caracteres raros | Puede fallar en Windows | Normalizar paths |
| Ticket vacio y se presiona Cobrar | Mensaje, pero no bloquea ticket_id | Menor |
| No hay rollback si se interrumpe entre filas | Se guardan parciales | Confirmacion previa reduce el riesgo, pero no hay rollback |
| Excel abierto mientras se intenta exportar | Falla de permiso | Capturado con error |
| Backups automaticos diarios | Se generan en `data/historial/backups` al primer uso del dia | Revisar el espacio disponible y copiar fuera de la PC |
| Resumenes automaticos | Se crean/actualizan en `data/historial/resumenes` (archivos .xlsx) | Consultar estos archivos para el arqueo diario |
| Ticket ID se basa en archivo mensual | Reinicia cada mes | Comportamiento esperado, documentado |

---

## Licencia y creditos

Desarrollado como prototipo para gestion de caja en cafeterias locales.
Autor: *[Diego Mendez]*
Version: **MVP 1.0**

