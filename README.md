# Generador de Certificados e Insignias

Aplicación Streamlit con dos pestañas:

- 🎓 Emisión de Diplomas, Certificados y Constancias
- 🏅 Emisión de Insignias (Docente y Alumno)

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
```

## Ejecución

Desde esta carpeta (las rutas de recursos son relativas al directorio de trabajo):

```bash
streamlit run generador_certificados.py
```

## Carpetas de recursos requeridas

| Carpeta | Contenido | Uso |
|---|---|---|
| `plantillas/` | `PROGRESIVO_1P_5S.jpg`, `PARTICIPACION_1P_5S.jpg`, `APROBADO_1P_3P.jpg`, `APROBADO_4P_5S.jpg` | Fondos de diplomas, certificados y constancias |
| `plantillas_insignias/` | `ALUMNO.jpg`, `DOCENTE_ESPECIALISTA.jpg`, `DOCENTE_SENIOR.jpg` | Fondos de insignias |
| `fonts/` | `trebuchet.ttf` | Fuente Trebuchet MS |
| `watermarks/` | `marca_agua.pdf`, `marca_agua_landscape.pdf` | Marca de agua opcional |

La carpeta `temp_insignias/` se crea y elimina automáticamente durante la generación de insignias.
