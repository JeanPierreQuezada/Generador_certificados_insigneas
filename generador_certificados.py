import io
import re
import streamlit as st
import pandas as pd
import os
import PyPDF2
import zipfile
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from zipfile import ZipFile
from datetime import datetime
from tempfile import NamedTemporaryFile
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(
    page_title="Validador de Archivos",
    page_icon="📊",
    layout="wide"
)

if 'tipo_certificado_seleccionado' not in st.session_state:
    st.session_state.tipo_certificado_seleccionado = None
if 'usar_marca_agua_seleccionado' not in st.session_state:
    st.session_state.usar_marca_agua_seleccionado = False
if 'fecha_certificado_seleccionada' not in st.session_state:
    st.session_state.fecha_certificado_seleccionada = datetime.now().date()
if 'tab4_reset_counter' not in st.session_state:
    st.session_state.tab4_reset_counter = 0
if 'df_procesado' not in st.session_state:
    st.session_state.df_procesado = None
if 'grupos' not in st.session_state:
    st.session_state.grupos = None
if 'plantillas' not in st.session_state:
    st.session_state.plantillas = None
if 'certificados_generados' not in st.session_state:
    st.session_state.certificados_generados = False
if 'zip_buffer' not in st.session_state:
    st.session_state.zip_buffer = None
if 'tab5_reset_counter' not in st.session_state:
    st.session_state.tab5_reset_counter = 0

CONFIG_INSIGNIAS = {
            'IDENTIFICADOR': {
                'font_size_inicial': 60,
                'max_width': 765,
                'max_height': 90,
                'min_font_size': 30
            },
            'CURSO': {
                'font_size_inicial': 60,
                'max_width': 765,
                'max_height': 200,
                'min_font_size': 25
            },
            'AÑO': {
                'font_size_inicial': 65,
                'max_width': 400,
                'max_height': 80,
                'min_font_size': 40
            }
        }

# Cursos que deben mostrarse con una grafía específica (marca registrada, etc.)
# Clave: nombre canónico en MAYÚSCULAS | Valor: cómo debe verse impreso/en pantalla
CURSOS_FORMATO_ESPECIAL = {
    #"ADOBE INDESIGN": "Adobe InDesign",
}

def _normalizar_curso(curso):
    """Mayúsculas y espacios simples (forma canónica usada en validaciones)."""
    if pd.isna(curso):
        return ""
    return ' '.join(str(curso).strip().upper().split())

def formatear_curso_salida(curso):
    """
    Nombre del curso para certificados, constancias, reportes e insignias.
    Por defecto en MAYÚSCULAS; si está en CURSOS_FORMATO_ESPECIAL usa su grafía.
    """
    curso_norm = _normalizar_curso(curso)
    return CURSOS_FORMATO_ESPECIAL.get(curso_norm, curso_norm)

def aplicar_formato_curso_vista(df):
    """
    Devuelve una COPIA del DataFrame con la columna CURSO formateada para mostrar
    en pantalla. Solo cambia los cursos especiales; el resto queda intacto.
    """
    df_vista = df.copy()
    for col in df_vista.columns:
        if str(col).strip().upper() == "CURSO":
            df_vista[col] = df_vista[col].apply(
                lambda v: CURSOS_FORMATO_ESPECIAL.get(_normalizar_curso(v), v) if pd.notna(v) else v
            )
    return df_vista

def register_custom_font():
    """Registra la fuente Trebuchet MS si está disponible"""
    font_path = os.path.join("fonts", "trebuchet.ttf")
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont('Trebuchet', font_path))
            return True
        except Exception as e:
            st.warning(f"No se pudo cargar la fuente Trebuchet MS: {e}")
            return False
    else:
        st.info("Fuente Trebuchet MS no encontrada. Usando fuente por defecto.")
        return False

TREBUCHET_AVAILABLE = register_custom_font()
styles_config = None

def mes_en_espanol(fecha):
    meses = {
        'January': 'enero',
        'February': 'febrero',
        'March': 'marzo',
        'April': 'abril',
        'May': 'mayo',
        'June': 'junio',
        'July': 'julio',
        'August': 'agosto',
        'September': 'septiembre',
        'October': 'octubre',
        'November': 'noviembre',
        'December': 'diciembre'
    }

    mes_ingles = fecha.strftime('%B')
    mes_espanol = meses.get(mes_ingles, mes_ingles)
    return fecha.strftime(f"%d de {mes_espanol} del %Y")

def agregar_marca_agua(pdf_bytes, watermark_path):
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_bytes)
        watermark_reader = PyPDF2.PdfReader(watermark_path)
        
        watermark_page = watermark_reader.pages[0]
        
        pdf_writer = PyPDF2.PdfWriter()
        
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            is_landscape = page_width > page_height
            
            if is_landscape:
                landscape_watermark_path = os.path.join("watermarks", "marca_agua_landscape.pdf")
                if os.path.exists(landscape_watermark_path):
                    landscape_watermark_reader = PyPDF2.PdfReader(landscape_watermark_path)
                    watermark = landscape_watermark_reader.pages[0]
                else:
                    watermark = watermark_page
            else:
                watermark = watermark_page
            
            page.merge_page(watermark)
            pdf_writer.add_page(page)
        
        result_pdf = BytesIO()
        pdf_writer.write(result_pdf)
        result_pdf.seek(0)
        
        return result_pdf
    except Exception as e:
        st.error(f"Error al aplicar marca de agua: {e}")
        return pdf_bytes

def cargar_plantillas():
    """Carga las plantillas de fondo desde la carpeta plantillas"""
    plantillas = {}
    plantillas_path = "plantillas"

    if not os.path.exists(plantillas_path):
        st.error(f"❌ La carpeta '{plantillas_path}' no existe. Créala y agrega las imágenes de fondo.")
        return None

    archivos_plantilla = {
        'PROGRESIVO_1P_5S.jpg': 'fondo_1',
        'PARTICIPACION_1P_5S.jpg': 'fondo_2',
        'APROBADO_1P_3P.jpg': 'fondo_3',
        'APROBADO_4P_5S.jpg': 'fondo_4'
    }

    for archivo, clave in archivos_plantilla.items():
        ruta_completa = os.path.join(plantillas_path, archivo)
        if os.path.exists(ruta_completa):
            with open(ruta_completa, 'rb') as f:
                plantillas[clave] = f.read()
        else:
            st.warning(f"⚠️ No se encontró {archivo} en la carpeta plantillas")

    if len(plantillas) == 4:
        return plantillas
    else:
        st.error(f"❌ Se necesitan 4 plantillas, solo se encontraron {len(plantillas)}")
        return None

def clasificar_estudiantes_por_nota(df, tipo_certificado):
    """
    Clasifica estudiantes según el tipo de certificado seleccionado.
    
    Args:
        df: DataFrame con los datos de estudiantes
        tipo_certificado: "Progresivo" o "Regular"
    
    Returns:
        dict con grupos de estudiantes clasificados
    """
    grupos = {
        'grupo_1': pd.DataFrame(),  # Progresivo
        'grupo_2': pd.DataFrame(),  # Nota < 12.5 / Participación
        'grupo_3': pd.DataFrame(),  # Nota ≥ 12.5 y Grado = 1P-3P
        'grupo_4': pd.DataFrame()   # Nota ≥ 12.5 y Grado = 4P-5S
    }

    if 'nota final' not in df.columns:
        st.error("❌ No se encontró la columna 'NOTA FINAL' en el DataFrame")
        return None

    if 'grado' not in df.columns:
        st.error("❌ No se encontró la columna 'GRADO' en el DataFrame")
        return None

    # Verificar si el tipo de certificado es Progresivo (Grupo1)
    if tipo_certificado == "Progresivo":
        grupos['grupo_1'] = df.copy()
        st.info(f"📋 **Modo Progresivo seleccionado**: Todos los certificados usarán el formato Progresivo")

    else:  # "Regular"
        df['nota_final_num'] = pd.to_numeric(df['nota final'], errors='coerce')

        # Grupo 2: Nota < 12.5 - Participación
        grupos['grupo_2'] = df[df['nota_final_num'] < 12.5].copy()

        # Grupos 3 y 4: Nota ≥ 12.5
        df_nota_alta = df[df['nota_final_num'] >= 12.5].copy()

        grupos['grupo_3'] = df_nota_alta[df_nota_alta['grado'].str.lower().str.strip().isin(['1p', '2p', '3p'])].copy()
        grupos['grupo_4'] = df_nota_alta[
            df_nota_alta['grado'].str.lower().str.strip().isin(['4p', '5p', '6p', '1s', '2s', '3s', '4s', '5s'])].copy()
        
        st.info(f"📋 **Modo Normal seleccionado**: Certificados según nota (aprobado/participación)")

    return grupos

def validar_y_mapear_columnas(df, tipo_certificado="Regular"):
    """
    Valida que el DataFrame tenga las columnas esperadas del usuario y las mapea
    a los nombres que espera procesar_excel_inicial.
    
    Args:
        df: DataFrame a validar
        tipo_certificado: "Progresivo" o "Regular". Si es None, no valida HORAS PROGRESIVO.
    
    Retorna: (df_mapeado, exito, mensaje)
    """
    columnas_esperadas = [
        "NRO.", "PATERNO", "MATERNO", "NOMBRE", "GRADO", "SECCIÓN", "CURSO", 
        "NOTA LABORATORIO", "¿ASISTIÓ?", "P1 4PTOS.", "P2 4PTOS.", "P3 4PTOS.", 
        "P4 4PTOS.", "P5 4PTOS.", "NOTA EVALUADOR", "NOTA FINAL", "OBSERVADOS", 
        "ESTATUS", "NUMERACIÓN"
    ]
    
    df.columns = df.columns.str.strip()
    columnas_faltantes = [col for col in columnas_esperadas if col not in df.columns]
    requiere_horas_progresivo = tipo_certificado == "Progresivo"
    
    if requiere_horas_progresivo and "HORAS PROGRESIVO" not in df.columns:
        columnas_faltantes.append("HORAS PROGRESIVO")
    
    if columnas_faltantes:
        mensaje_error = f"❌ El archivo no tiene las columnas requeridas. Faltan: {', '.join(columnas_faltantes)}"
        if requiere_horas_progresivo and "HORAS PROGRESIVO" in columnas_faltantes:
            mensaje_error += "\n\n💡 Nota: La columna 'HORAS PROGRESIVO' es requerida cuando se selecciona el tipo 'Progresivo'."
        return None, False, mensaje_error
    
    mapeo_columnas = {
        "NRO.": "nro",
        "PATERNO": "paterno",
        "MATERNO": "materno",
        "NOMBRE": "nombre",
        "GRADO": "grado",
        "SECCIÓN": "sección",
        "CURSO": "curso",
        "NOTA LABORATORIO": "nota lab",
        "¿ASISTIÓ?": "lista de asistencia",
        "NOTA EVALUADOR": "nota de examen cibertec",
        "NOTA FINAL": "nota final",
        "OBSERVADOS": "observación sobre nota desaprobatoria",
        "ESTATUS": "status",
        "NUMERACIÓN": "numeración"
    }

    orden_final = [
        "NRO.", "PATERNO", "MATERNO", "NOMBRE", "GRADO", "SECCIÓN", "CURSO",
        "NOTA LABORATORIO", "¿ASISTIÓ?", "NOTA EVALUADOR", "NOTA FINAL",
        "OBSERVADOS", "ESTATUS", "NUMERACIÓN"
    ]

    tiene_horas_progresivo = "HORAS PROGRESIVO" in df.columns
    if tiene_horas_progresivo:
        mapeo_columnas["HORAS PROGRESIVO"] = "horas_progresivo"
        orden_final.append("HORAS PROGRESIVO")
    
    columnas_a_mantener = [col for col in orden_final if col in df.columns]
    df_filtrado = df[columnas_a_mantener].copy()
    
    if not tiene_horas_progresivo and not requiere_horas_progresivo:
        df_filtrado["HORAS PROGRESIVO"] = ""
        orden_final.append("HORAS PROGRESIVO")
    
    df_filtrado = df_filtrado[orden_final]
    filas_vacias = pd.DataFrame(columns=df_filtrado.columns, index=range(10))

    if tiene_horas_progresivo:
        mapeo_columnas["HORAS PROGRESIVO"] = "horas_progresivo"
    elif "HORAS PROGRESIVO" in orden_final:
        mapeo_columnas["HORAS PROGRESIVO"] = "horas_progresivo"
    
    nombres_mapeados = [mapeo_columnas.get(col, col.lower()) for col in orden_final]
    fila_encabezado = pd.DataFrame([nombres_mapeados], columns=df_filtrado.columns)
    
    df_formateado = pd.concat([filas_vacias, fila_encabezado, df_filtrado], ignore_index=True)

    return df_formateado, True, "✅ Columnas validadas y mapeadas correctamente"

def detectar_fila_encabezado(df):
    """
    Detecta la fila que contiene el encabezado buscando palabras clave.
    Retorna el índice de la fila o None si no la encuentra.
    """
    palabras_clave = ['paterno', 'materno', 'nombre', 'nro', 'grado', 'sección', 'curso', 'nota final']
    
    for idx, row in df.iterrows():
        row_str = ' '.join(str(val).lower() for val in row if pd.notna(val))
        coincidencias = sum(1 for palabra in palabras_clave if palabra in row_str)
        if coincidencias >= 4:
            return idx
    
    return None

def procesar_excel_inicial(uploaded_file):
    """
    Procesa el archivo Excel eliminando las primeras 9 filas y columnas J-N y desde la T
    """
    try:
        columnas_requeridas = [
            "nro", "paterno", "materno", "nombre", "grado", "sección", "curso", 
            "nota lab", "lista de asistencia", "nota de examen cibertec", "nota final", 
            "observación sobre nota desaprobatoria", "status", "numeración", "horas_progresivo"
        ]
        
        df_original = pd.read_excel(uploaded_file)
        df_procesado = df_original.iloc[10:].copy()
        df_procesado = df_procesado.reset_index(drop=True)
        df_procesado.columns = df_procesado.iloc[0].str.lower()
        df_procesado = df_procesado.drop(df_procesado.index[0]).reset_index(drop=True)
        columnas_existentes = [col for col in columnas_requeridas if col in df_procesado.columns]
        df_procesado = df_procesado[columnas_existentes]

        if 'nota final' in df_procesado.columns:
            df_procesado['nota final'] = df_procesado['nota final'].apply(
                lambda x: 0 if isinstance(x, str) and x.strip().upper() == 'NP' else x
            )

        df_procesado['nombre_certificado'] = df_procesado['nombre'].fillna('').str.strip() + ' ' + df_procesado[
            'paterno'].fillna('').str.strip() + ' ' + df_procesado['materno'].fillna('').str.strip()

        if 'nro' in df_procesado.columns:
            columnas = df_procesado.columns.tolist()
            columnas.remove('nombre_certificado')
            posicion_nro = columnas.index('nro')
            columnas.insert(posicion_nro + 1, 'nombre_certificado')
            df_procesado = df_procesado[columnas]

        return df_procesado, True, "Archivo procesado correctamente"

    except Exception as e:
        return None, False, f"Error al procesar el archivo: {str(e)}"

def wrap_text_to_width(canvas, text, font_name, font_size, max_width_mm):
    max_width_points = max_width_mm * 2.83465
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = current_line + [word]
        test_text = ' '.join(test_line)
        text_width = canvas.stringWidth(test_text, font_name, font_size)

        if text_width <= max_width_points:
            current_line = test_line
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)

    if current_line:
        lines.append(' '.join(current_line))

    return lines

def draw_multiline_text(canvas, text, style_key, page_width, styles_config, max_width_mm=None):
    style = styles_config[style_key]
    font_name = style['font_family'] if TREBUCHET_AVAILABLE else 'Helvetica'

    is_bold = style.get('bold', False)

    if is_bold:
        try:
            bold_font_name = f"{font_name}-Bold"
            canvas.setFont(bold_font_name, style['font_size'])
            font_name = bold_font_name
        except Exception as e:
            try:
                canvas.setFont(font_name, style['font_size'])
            except Exception as e:
                canvas.setFont('Helvetica-Bold' if is_bold else 'Helvetica', style['font_size'])
                font_name = 'Helvetica-Bold' if is_bold else 'Helvetica'
    else:
        try:
            canvas.setFont(font_name, style['font_size'])
        except Exception as e:
            canvas.setFont('Helvetica', style['font_size'])
            font_name = 'Helvetica'

    canvas.setFillColor(HexColor(style['color']))
    x_points = style['x'] * 2.83465
    y_points = style['y'] * 2.83465

    if max_width_mm is None:
        if style['x'] == 148 or style['x'] == 105:
            text_width = canvas.stringWidth(text, font_name, style['font_size'])
            x_points = (page_width - text_width) / 2
        canvas.drawString(x_points, y_points, text)
        return style['font_size']

    lines = wrap_text_to_width(canvas, text, font_name, style['font_size'], max_width_mm)
    line_height = style['font_size'] * 1.2
    start_y = y_points

    for i, line in enumerate(lines):
        line_y = start_y - (i * line_height)
        if style['x'] == 148 or style['x'] == 105:
            text_width = canvas.stringWidth(line, font_name, style['font_size'])
            line_x = (page_width - text_width) / 2
        else:
            line_x = x_points
        canvas.drawString(line_x, line_y, line)

    return line_height * len(lines)

def generar_certificados_grupo(grupo_df, plantilla_bytes, plantilla_key, nombre_grupo, zip_file, progress_bar,
    estudiantes_base, total_estudiantes, styles_config_by_template):
    certificados_generados = 0

    usar_marca_agua = st.session_state.get('usar_marca_agua_seleccionado', False)
    aplicar_marca_agua = usar_marca_agua and plantilla_key != 'fondo_2'
    
    watermark_path = os.path.join("watermarks", "marca_agua.pdf")
    if aplicar_marca_agua and not os.path.exists(watermark_path):
        st.warning(f"⚠️ No se encontró el archivo de marca de agua en {watermark_path}. Se generarán PDFs sin marca de agua.")
        aplicar_marca_agua = False

    styles_config = styles_config_by_template[plantilla_key]

    if styles_config.get('orientation') == 'portrait':
        page_size = A4
        page_width, page_height = A4
    else:
        page_size = landscape(A4)
        page_width, page_height = landscape(A4)

    for i, row in grupo_df.iterrows():
        try:
            nombre = str(row["nombre_certificado"]).strip().upper()
            curso_base = _normalizar_curso(row["curso"])      # para nombres de archivo
            curso = formatear_curso_salida(curso_base)         # para lo impreso en el PDF

            fecha_seleccionada = st.session_state.get('fecha_certificado_seleccionada', datetime.now().date())
            if isinstance(fecha_seleccionada, datetime):
                fecha_para_certificado = fecha_seleccionada
            else:
                fecha_para_certificado = datetime.combine(fecha_seleccionada, datetime.min.time())
            
            fecha = mes_en_espanol(fecha_para_certificado)
            numero = (
                str(row["numeración"]).strip()
                if "numeración" in row and pd.notnull(row["numeración"])
                else f"GEN-{i + 1:03}"
            )

            horas = "horas_progresivo"
            horas_progresivo = ""
            if plantilla_key == 'fondo_1' and horas in row and pd.notnull(row[horas]):
                horas_progresivo = str(row[horas])

            with NamedTemporaryFile(delete=False, suffix=".png") as tmp_img:
                tmp_img.write(plantilla_bytes)
                tmp_img.flush()
                tmp_img_path = tmp_img.name

            pdf_buffer = BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=page_size)
            c.drawImage(tmp_img_path, 0, 0, width=page_width, height=page_height)
            draw_multiline_text(c, nombre, 'nombre', page_width, styles_config, styles_config['nombre']['max_width'])
            draw_multiline_text(c, curso, 'curso', page_width, styles_config, styles_config['curso']['max_width'])
            draw_multiline_text(c, f"Lima, {fecha}", 'fecha', page_width, styles_config)

            if plantilla_key == 'fondo_1' and horas_progresivo:
                draw_multiline_text(c, horas_progresivo, 'horas', page_width, styles_config)
            
            if plantilla_key != 'fondo_2':
                draw_multiline_text(c, f"Certificado Nº {numero}", 'numero', page_width, styles_config)

            c.save()
            pdf_bytes = pdf_buffer.getvalue()

            if aplicar_marca_agua:
                pdf_buffer = agregar_marca_agua(BytesIO(pdf_bytes), watermark_path)
                pdf_bytes = pdf_buffer.getvalue()

            if plantilla_key == 'fondo_2':
                pdf_name = f"Constancias/{nombre.strip().replace(' ', '_') + '_' + curso_base[0:11].replace(' ', '_')}.pdf"
            else:
                pdf_name = f"{nombre.strip().replace(' ', '_') + '_' + curso_base[0:11].replace(' ', '_')}.pdf"

            zip_file.writestr(pdf_name, pdf_bytes)

            certificados_generados += 1

            progreso_actual = (estudiantes_base + certificados_generados) / total_estudiantes
            progress_bar.progress(min(progreso_actual, 1.0))

            try:
                if os.path.exists(tmp_img_path):
                    os.unlink(tmp_img_path)
            except:
                pass

        except Exception as e:
            st.error(f"Error generando certificado para {nombre}: {e}")

    return certificados_generados

def generar_todos_certificados():
    if st.session_state.grupos and st.session_state.plantillas:
        st.info("Generando certificados por grupos...")

        total_estudiantes = sum(len(grupo) for grupo in st.session_state.grupos.values() if not grupo.empty)
        progress_bar = st.progress(0)
        estudiantes_procesados = 0

        zip_buffer = BytesIO()

        with ZipFile(zip_buffer, "a") as zip_file:
            zip_file.writestr("Constancias/", "")

            styles_config_by_template = {
            "fondo_1": {
                'curso': {
                    'font_family': 'Trebuchet',
                    'font_size': 32,
                    'color': '#000000',
                    'x': 52,
                    'y': 129,
                    'max_width': 220,
                    'bold': True
                },
                'nombre': {
                    'font_family': 'Trebuchet',
                    'font_size': 25,
                    'color': '#000000',
                    'x': 52,
                    'y': 85,
                    'max_width': 210
                },
                'fecha': {
                    'font_family': 'Trebuchet',
                    'font_size': 18,
                    'color': '#004064',
                    'x': 52,
                    'y': 36,
                    'max_width': None,
                    'bold': True
                },
                'numero': {
                    'font_family': 'Trebuchet',
                    'font_size': 15.5,
                    'color': '#004064',
                    'x': 52,
                    'y': 27,
                    'max_width': None
                },
                'horas': {
                    'font_family': 'Trebuchet',
                    'font_size': 15.5,
                    'color': '#004064',
                    'x': 132.5,
                    'y': 65.2,
                    'max_width': None
                },
                'orientation': 'landscape'
            },
            "fondo_2": {  # Vertical
                'curso': {
                    'font_family': 'Trebuchet',
                    'font_size': 30.5,
                    'color': '#000000',
                    'x': 105,
                    'y': 185,
                    'max_width': 160,
                    'bold': True
                },
                'nombre': {
                    'font_family': 'Trebuchet',
                    'font_size': 29,
                    'color': '#000000',
                    'x': 105,
                    'y': 133,
                    'max_width': 160,
                    'bold': True
                },
                'fecha': {
                    'font_family': 'Trebuchet',
                    'font_size': 18,
                    'color': '#004064',
                    'x': 105,
                    'y': 78,
                    'max_width': None
                },
                # No aparece en el certificado, sólo está para evitar errores en f()
                'numero': {
                    'font_family': 'Trebuchet',
                    'font_size': 1,
                    'color': '#ffffff',
                    'x': 0,
                    'y': 0,
                    'max_width': None
                },
                'orientation': 'portrait'
            },
            "fondo_3": {
                'curso': {
                    'font_family': 'Trebuchet',
                    'font_size': 30.5,
                    'color': '#000000',
                    'x': 148,
                    'y': 117,
                    'max_width': 245,
                    'bold': True
                },
                'nombre': {
                    'font_family': 'Trebuchet',
                    'font_size': 29,
                    'color': '#000000',
                    'x': 148,
                    'y': 75,
                    'max_width': 245,
                    'bold': True
                },
                'fecha': {
                    'font_family': 'Trebuchet',
                    'font_size': 18,
                    'color': '#004064',
                    'x': 20,
                    'y': 41,
                    'max_width': None,
                    'bold': True
                },
                'numero': {
                    'font_family': 'Trebuchet',
                    'font_size': 15.5,
                    'color': '#004064',
                    'x': 20,
                    'y': 32,
                    'max_width': None
                },
                'orientation': 'landscape'
            },
            "fondo_4": {
                'curso': {
                    'font_family': 'Trebuchet',
                    'font_size': 30.5,
                    'color': '#000000',
                    'x': 148,
                    'y': 117,
                    'max_width': 245,
                    'bold': True
                },
                'nombre': {
                    'font_family': 'Trebuchet',
                    'font_size': 29,
                    'color': '#000000',
                    'x': 148,
                    'y': 75,
                    'max_width': 245,
                    'bold': True
                },
                'fecha': {
                    'font_family': 'Trebuchet',
                    'font_size': 18,
                    'color': '#004064',
                    'x': 20,
                    'y': 41,
                    'max_width': None,
                    'bold': True
                },
                'numero': {
                    'font_family': 'Trebuchet',
                    'font_size': 15.5,
                    'color': '#004064',
                    'x': 20,
                    'y': 32,
                    'max_width': None
                },
                'orientation': 'landscape'
            }
        }

            mapeo_plantillas = {
                'grupo_1': 'fondo_1',  # Progresiva
                'grupo_2': 'fondo_2',  # Participación Nota < 12.5
                'grupo_3': 'fondo_3',  # Base - Nota ≥ 12.5 y Grado = 1P-3P
                'grupo_4': 'fondo_4'   # Base - Nota ≥ 12.5 y Grado = 4P-5S
            }

            for grupo_nombre, grupo_df in st.session_state.grupos.items():
                if not grupo_df.empty:
                    plantilla_key = mapeo_plantillas[grupo_nombre]
                    plantilla_bytes = st.session_state.plantillas[plantilla_key]

                    st.write(f"Procesando {grupo_nombre} ({len(grupo_df)} estudiantes) con plantilla {plantilla_key}...")

                    certificados_gen = generar_certificados_grupo(
                        grupo_df,
                        plantilla_bytes,
                        plantilla_key,
                        grupo_nombre,
                        zip_file,
                        progress_bar,
                        estudiantes_procesados,
                        total_estudiantes,
                        styles_config_by_template
                    )

                    estudiantes_procesados += len(grupo_df)

                    st.success(f"✅ {grupo_nombre}: {certificados_gen} certificados generados con estilo {plantilla_key}")

        zip_buffer.seek(0)
        st.success("🎉 Todos los certificados han sido generados correctamente y están listos para su descarga.")
        
        st.session_state.zip_buffer = zip_buffer
        st.session_state.certificados_generados = True
        
        return True
    return False

def ajustar_texto_inteligente(draw, text, font_path, font_size_inicial, max_width, max_height, 
                               min_font_size=20, line_spacing=1.2):
    """
    Ajusta el texto para que quepa en el espacio disponible.
    Intenta primero dividir en dos líneas, si no cabe, reduce el tamaño de fuente.
    """
    
    def get_text_size(text, font):
        """Obtiene el ancho y alto del texto"""
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        return width, height
    
    def dividir_texto_en_dos_lineas(text):
        """Divide el texto en dos líneas de manera inteligente"""
        palabras = text.split()
        if len(palabras) <= 2:
            return [text]
        mitad = len(palabras) // 2
        linea1 = ' '.join(palabras[:mitad])
        linea2 = ' '.join(palabras[mitad:])
        return [linea1, linea2]
    
    current_font_size = font_size_inicial
    
    try:
        font = ImageFont.truetype(font_path, current_font_size)
    except:
        font = ImageFont.load_default()
        return [text], font
    
    text_width, text_height = get_text_size(text, font)
    
    # Caso 1: El texto cabe en una sola línea con el tamaño original
    if text_width <= max_width and text_height <= max_height:
        return [text], font
    
    # Caso 2: Intentar dividir en dos líneas con el tamaño original
    lineas = dividir_texto_en_dos_lineas(text)
    
    if len(lineas) == 2:
        ancho_linea1, alto_linea1 = get_text_size(lineas[0], font)
        ancho_linea2, alto_linea2 = get_text_size(lineas[1], font)
        max_ancho_lineas = max(ancho_linea1, ancho_linea2)
        alto_total = (alto_linea1 + alto_linea2) * line_spacing
        
        if max_ancho_lineas <= max_width and alto_total <= max_height:
            return lineas, font
    
    # Caso 3: Reducir tamaño de fuente gradualmente
    for size in range(current_font_size - 5, min_font_size - 1, -5):
        try:
            font = ImageFont.truetype(font_path, size)
        except:
            continue
        
        lineas = dividir_texto_en_dos_lineas(text)
        
        if len(lineas) == 2:
            ancho_linea1, alto_linea1 = get_text_size(lineas[0], font)
            ancho_linea2, alto_linea2 = get_text_size(lineas[1], font)
            max_ancho_lineas = max(ancho_linea1, ancho_linea2)
            alto_total = (alto_linea1 + alto_linea2) * line_spacing
            
            if max_ancho_lineas <= max_width and alto_total <= max_height:
                return lineas, font
        
        text_width, text_height = get_text_size(text, font)
        if text_width <= max_width and text_height <= max_height:
            return [text], font
    
    # Último recurso: usar tamaño mínimo
    try:
        font = ImageFont.truetype(font_path, min_font_size)
    except:
        font = ImageFont.load_default()
    
    return dividir_texto_en_dos_lineas(text), font

def draw_centered_text_adaptive(draw, text, x_center, y_center, font_path, 
                                font_size_inicial, max_width, max_height,
                                min_font_size=20, fill="white", line_spacing=1.2):
    """
    Dibuja texto centrado con ajuste automático de tamaño y división en líneas.
    """
    
    lineas, fuente_final = ajustar_texto_inteligente(
        draw, text, font_path, font_size_inicial, 
        max_width, max_height, min_font_size, line_spacing
    )
    
    lineas_info = []
    for linea in lineas:
        bbox = draw.textbbox((0, 0), linea, font=fuente_final)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        lineas_info.append({'text': linea, 'width': width, 'height': height})
    
    if len(lineas_info) == 1:
        total_height = lineas_info[0]['height']
    else:
        total_height = sum(info['height'] for info in lineas_info) * line_spacing
    
    y_actual = y_center - (total_height / 2)
    
    for i, info in enumerate(lineas_info):
        x_pos = x_center - (info['width'] / 2)
        draw.text((x_pos, y_actual), info['text'], fill=fill, font=fuente_final)
        
        if i < len(lineas_info) - 1:
            y_actual += info['height'] * line_spacing
    
    return {
        'lineas': len(lineas),
        'font_size': fuente_final.size if hasattr(fuente_final, 'size') else font_size_inicial
    }

st.title("📊 Sistema de Validación de Archivos")

tab5, tab6 = st.tabs(["🎓 Emisión de Diplomas, Certificados y Constancias", "🏅 Emisión de Insignias (Docente y Alumno)"])

# TAB 4: Generador de Certificados
with tab5:
    st.markdown("## 🎓 Emisión de Diplomas, Certificados y Constancias")
    st.markdown("""
                **DESCRIPCIÓN:**
                
                Permite emitir los diplomas, certificados, certificados progresivos y constancias manera automática a partir de la información registrada de diplomados, certificados y constancias, según el archivo cargado. El proceso crea archivos PDF independientes para cada alumno, los cuales pueden descargarse de manera consolidada en un archivo ZIP, facilitando la revisión, distribución y trazabilidad de la información.
                """)
    st.info("""
    📌 **INSTRUCCIONES:**
    1.	Sube un archivo OK con formato:
            
        •	{NombreColegio}_1P-3P_OK.xlsx
            
        •	{NombreColegio}_4P-5S_OK_EVALUADOR_REV.xlsx
            
    2.	Selecciona el tipo de certificado que a generar
    3.	Elige si deseas incluir marca de agua en los certificados
    4.	Se generarán archivos comprimidos con todos los certificados correspondientes
            
    ⚠️ **IMPORTANTE**
    1.	**Columnas base requeridas:** NRO., PATERNO, MATERNO, NOMBRE, GRADO, SECCIÓN, CURSO, NOTA LABORATORIO, ¿ASISTIÓ?, P1 4PTOS., P2 4PTOS., P3 4PTOS., P4 4PTOS., P5 4PTOS., NOTA EVALUADOR, NOTA FINAL, OBSERVADOS, ESTATUS, NUMERACIÓN
    2.	**Columna HORAS PROGRESIVO:** Solo es REQUERIDA cuando se selecciona el tipo "Progresivo". Para certificados normales, esta columna es opcional.
    3.	La columna "NOTA FINAL" debe estar completa (sin valores vacíos)
    """)

    if 'archivo_procesado' not in st.session_state:
        st.session_state.archivo_procesado = False

    st.markdown("### 📤 Subir y procesar archivo Excel")

    if 'tipo_certificado_seleccionado' not in st.session_state:
        st.session_state.tipo_certificado_seleccionado = None
    if 'usar_marca_agua_seleccionado' not in st.session_state:
        st.session_state.usar_marca_agua_seleccionado = False

    uploaded_file = st.file_uploader(
        "Selecciona un archivo Excel", 
        type=["xlsx"],
        key=f"tab4_uploader_{st.session_state.tab4_reset_counter}"
    )

    if uploaded_file:
        st.markdown("### ⚙️ Configuración de certificados")
        
        deshabilitar_opciones = st.session_state.certificados_generados

        col1, col2 = st.columns(2)
        
        with col1:
            opciones_display = {
                "Regulares (diplomados, certificados y constancias)": "Regular",
                "Progresivo": "Progresivo"
            }
            
            valor_actual = st.session_state.tipo_certificado_seleccionado
            if valor_actual:
                display_actual = [k for k, v in opciones_display.items() if v == valor_actual][0]
            else:
                display_actual = list(opciones_display.keys())[0]
            
            tipo_certificado_display = st.selectbox(
                "📋 Seleccionar la plantilla automática",
                options=list(opciones_display.keys()),
                index=list(opciones_display.keys()).index(display_actual) if valor_actual else 0,
                help="**Regulares (diplomados, certificados y constancias):** Se genera según nota de aprobación (≥12.5 = aprobado, <12.5 = participación)\n\n**Progresivo:** Todos los estudiantes reciben certificado.",
                key="select_tipo_certificado",
                disabled=deshabilitar_opciones
            )
            st.session_state.tipo_certificado_seleccionado = opciones_display[tipo_certificado_display]
        
        with col2:
            st.markdown("""
                <style>
                    div[data-testid="stCheckbox"] {
                        padding-top: 1.3rem;
                    }
                </style>
            """, unsafe_allow_html=True)

            usar_marca_agua = st.checkbox(
                "Incluir marca de agua",
                value=st.session_state.usar_marca_agua_seleccionado,
                help="Agrega marca de agua 'PRELIMINAR' a los certificados generados",
                key="check_marca_agua",
                disabled=deshabilitar_opciones
            )
            st.session_state.usar_marca_agua_seleccionado = usar_marca_agua
        
        st.markdown("### 📅 Fecha de los certificados")
        col_fecha1, col_fecha2 = st.columns([2, 1])
        
        with col_fecha1:
            fecha_seleccionada = st.date_input(
                "Selecciona la fecha de emisión",
                value=st.session_state.fecha_certificado_seleccionada,
                help="Esta fecha aparecerá en todos los certificados generados",
                key="date_certificado",
                disabled=deshabilitar_opciones,
                format="DD/MM/YYYY"
            )
            st.session_state.fecha_certificado_seleccionada = fecha_seleccionada
        
        with col_fecha2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Usar fecha de hoy", disabled=deshabilitar_opciones, use_container_width=True):
                st.session_state.fecha_certificado_seleccionada = datetime.now().date()
                st.rerun()
        
        from datetime import date
        fecha_para_certificado = st.session_state.fecha_certificado_seleccionada
        if isinstance(fecha_para_certificado, date):
            fecha_dt = datetime.combine(fecha_para_certificado, datetime.min.time())
        else:
            fecha_dt = fecha_para_certificado
        fecha_formateada = mes_en_espanol(fecha_dt)
        st.info(f"📄 Los certificados mostrarán: **Lima, {fecha_formateada}**")
        
        tipo_certificado_actual = st.session_state.tipo_certificado_seleccionado
        if tipo_certificado_actual == "Regular":
            st.info("""
                    ℹ️ **Modo Regulares (diplomados, certificados y constancias):** 
                    - Se generarán certificados de aprobación (nota ≥12.5) o participación (nota <12.5) según corresponda.
                    - Los estudiantes de 1P-3P y 4P-5S usarán plantillas diferentes.
                    """)
        else:
            st.success("ℹ️ **Modo Progresivo:** Todos los estudiantes recibirán certificados progresivos")
        
        if usar_marca_agua:
            st.warning("⚠️ Los certificados incluirán la marca de agua 'PRELIMINAR'")
        
        st.markdown("---")

    if uploaded_file and not st.session_state.archivo_procesado:
        if st.button("🚀 Procesar archivo y generar certificados", type="primary", use_container_width=True, key="btn_procesar_certificados"):
                with st.spinner("Validando y procesando archivo..."):
                    try:
                        uploaded_file.seek(0)
                        df_temp = pd.read_excel(uploaded_file, header=None)
                        fila_encabezado = detectar_fila_encabezado(df_temp)
                        
                        if fila_encabezado is None:
                            st.warning("⚠️ No se pudo detectar automáticamente la fila del encabezado. Usando fila 7 por defecto.")
                            fila_encabezado = 8
                        else:
                            st.info(f"📍 Encabezado detectado en la fila {fila_encabezado + 1}")
                        
                        uploaded_file.seek(0)
                        df_usuario = pd.read_excel(uploaded_file, header=fila_encabezado)

                    except Exception as e:
                        st.error(f"❌ Error al leer el archivo: {str(e)}")
                        st.stop()
                    
                    tipo_certificado_para_validar = st.session_state.get('tipo_certificado_seleccionado', 'Regular')
                    df_formateado, exito_mapeo, mensaje_mapeo = validar_y_mapear_columnas(df_usuario, tipo_certificado_para_validar)
                    
                    if not exito_mapeo:
                        st.error(mensaje_mapeo)
                        
                        if tipo_certificado_para_validar == "Progresivo":
                            st.info(""" 
                                    El archivo de Excel debe contener exactamente estas columnas:
                                    - NRO., PATERNO, MATERNO, NOMBRE, GRADO, SECCIÓN, CURSO, NOTA LABORATORIO, ¿ASISTIÓ?, P1 4PTOS., P2 4PTOS., P3 4PTOS., P4 4PTOS., P5 4PTOS., NOTA EVALUADOR, NOTA FINAL, OBSERVADOS, ESTATUS, NUMERACIÓN, HORAS PROGRESIVO
                                    
                                    ⚠️ Nota: La columna 'HORAS PROGRESIVO' es obligatoria para certificados Progresivos.
                                    """)
                        else:
                            st.info(""" 
                                    El archivo de Excel debe contener estas columnas base:
                                    - NRO., PATERNO, MATERNO, NOMBRE, GRADO, SECCIÓN, CURSO, NOTA LABORATORIO, ¿ASISTIÓ?, P1 4PTOS., P2 4PTOS., P3 4PTOS., P4 4PTOS., P5 4PTOS., NOTA EVALUADOR, NOTA FINAL, OBSERVADOS, ESTATUS, NUMERACIÓN
                                    
                                    ℹ️ Nota: La columna 'HORAS PROGRESIVO' no es necesaria para certificados Normales.
                                    """)
                        st.stop()
                    
                    st.success(mensaje_mapeo)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_formateado.to_excel(writer, index=False, sheet_name='Sheet1')
                    output.seek(0)
                    
                    df_procesado, exito, mensaje = procesar_excel_inicial(output)
                    
                    if exito:
                        st.session_state.df_procesado = df_procesado
                        st.session_state.nombre_archivo = uploaded_file.name
                        st.session_state.grupos = None
                        st.session_state.plantillas = None
                        st.session_state.certificados_generados = False
                        st.session_state.zip_buffer = None
                        st.success(mensaje)
                        st.subheader("✅ Archivo procesado - Vista previa de datos limpios")
                        st.write(f"**Dimensiones procesadas:** {df_procesado.shape[0]} filas x {df_procesado.shape[1]} columnas")
                        
                        df_mostrar = df_procesado.copy()
                        df_mostrar.columns = df_mostrar.columns.str.upper()
                        
                        st.dataframe(aplicar_formato_curso_vista(df_mostrar), hide_index=True)
                        st.session_state.plantillas = cargar_plantillas()
                        
                        tipo_certificado_actual = st.session_state.get('tipo_certificado_seleccionado', 'Regular')
                        st.session_state.grupos = clasificar_estudiantes_por_nota(
                            st.session_state.df_procesado, 
                            tipo_certificado_actual
                        )
                        
                        if st.session_state.grupos:
                            st.markdown("### 📋 Preview de certificados a generar")
                            
                            col_prev1, col_prev2, col_prev3, col_prev4 = st.columns(4)
                            
                            with col_prev1:
                                cant_progresivos = len(st.session_state.grupos.get('grupo_1', pd.DataFrame()))
                                if cant_progresivos > 0:
                                    st.metric("🎓 Progresivos", cant_progresivos)
                            
                            with col_prev2:
                                cant_participacion = len(st.session_state.grupos.get('grupo_2', pd.DataFrame()))
                                if cant_participacion > 0:
                                    st.metric("📜 Participación", cant_participacion)
                            
                            with col_prev3:
                                cant_1p3p = len(st.session_state.grupos.get('grupo_3', pd.DataFrame()))
                                if cant_1p3p > 0:
                                    st.metric("✅ 1P-3P Aprobados", cant_1p3p)
                            
                            with col_prev4:
                                cant_4p5s = len(st.session_state.grupos.get('grupo_4', pd.DataFrame()))
                                if cant_4p5s > 0:
                                    st.metric("✅ 4P-5S Aprobados", cant_4p5s)
                            
                            total_certificados = cant_progresivos + cant_participacion + cant_1p3p + cant_4p5s
                            st.info(f"🎯 **Total de certificados a generar:** {total_certificados}")
                            
                            st.markdown("---")

                        generar_todos_certificados()

                        st.session_state.archivo_procesado = True
                    else:
                        st.error(mensaje)

    elif uploaded_file and st.session_state.archivo_procesado:
        st.success("✅ Archivo ya procesado. Los certificados están listos para descargar.")

    if st.session_state.certificados_generados and st.session_state.zip_buffer:
        nombre_archivo = st.session_state.get('nombre_archivo', '')
        nombre_base = os.path.splitext(nombre_archivo)[0] if nombre_archivo else "CERTIFICADOS"

        import re
        match = re.match(r'(.+?)_(1P-3P|4P-5S)', nombre_base)
        if match:
            nombre_colegio = match.group(1)
            rango_grados = match.group(2)
            nombre_limpio = f"{nombre_colegio}_{rango_grados}"
        else:
            nombre_limpio = nombre_base
        
        tipo_certificado = st.session_state.get('tipo_certificado_seleccionado', 'Regular')
        prefijo_tipo = "Regulares" if tipo_certificado == "Regular" else "Progresivos"
        usar_marca_agua = st.session_state.get('usar_marca_agua_seleccionado', False)

        if usar_marca_agua:
            zip_filename = f"{prefijo_tipo}_{nombre_limpio}_Preliminar.zip"
        else:
            zip_filename = f"{prefijo_tipo}_{nombre_limpio}.zip"
        
        st.download_button(
            label="📥 Descargar todos los certificados (ZIP)",
            data=st.session_state.zip_buffer,
            file_name=zip_filename,
            mime="application/zip"
        )
        
        st.markdown("---")
        if st.button("🔄 Limpiar y Generar nuevos certificados", use_container_width=True, key="btn_regenerar_certificados"):
            st.session_state.archivo_procesado = False
            st.session_state.df_procesado = None     
            st.session_state.nombre_archivo = None   
            st.session_state.grupos = None
            st.session_state.plantillas = None
            st.session_state.certificados_generados = False
            st.session_state.zip_buffer = None
            st.session_state.tipo_certificado_seleccionado = None 
            st.session_state.usar_marca_agua_seleccionado = False 
            st.session_state.fecha_certificado_seleccionada = datetime.now().date()
            st.session_state.tab4_reset_counter += 1
            st.rerun()
        
    elif not uploaded_file:
        st.info("👆 Sube un archivo Excel para generar los certificados automáticamente.")
        st.session_state.archivo_procesado = False

# TAB 5: GENERADOR DE INSIGNIAS
with tab6:
    st.markdown("## 🏅 Emisión de Insignias (Docente y Alumno)")
    st.markdown("""
                **DESCRIPCIÓN:**
                
                Permite emitir las insignias de reconocimiento a los docentes y alumnos manera automática a partir de la información registrada de diplomados, certificados y constancias, según el archivo cargado. El proceso crea archivos PDF independientes para cada alumno o docente, los cuales pueden descargarse de manera consolidada en un archivo ZIP, facilitando la revisión, distribución y trazabilidad de la información.
                """)
    st.info("""
    📌 **INSTRUCCIONES**
    1.	Columnas base requeridas (Columnas con valores completos):
            
        •	ALUMNO: NOMBRE, PATERNO, MATERNO, CURSO, AÑO.
            
        •	DOCENTE: NOMBRE, PATERNO, MATERNO, TIPO DE INSIGNEA, AÑO.
                    
    ⚠️ **IMPORTANTE**
    1.	Todos los datos se convertirán automáticamente a MAYÚSCULAS.
    2.	La cabecera debe estar en la fila 9 del Excel.
    3.	Las columnas deben estar correctamente nombradas y pueden variar de orden.
    4.	El nombre del PDF será: {TIPO DE INSIGNEA}_{NOMBRE COMPLETO}.pdf.
    """)
    
    tipo_insignia = st.radio(
            "Selecciona el tipo de insignia a generar:",
            ["ALUMNO", "DOCENTE"],
            horizontal=True
        )

    uploaded_file = st.file_uploader(
            f"Sube tu archivo Excel (.xlsx) con los datos de {tipo_insignia.lower()}s",
            type=["xlsx"],
            key=f"tab5_uploader_{st.session_state.tab5_reset_counter}",
            help="El archivo debe contener las columnas requeridas según el tipo de insignia seleccionado"
        )
    
    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, header=8)
            df = df.dropna(how='all')
            df = df.fillna('')
            
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.upper()

            columnas_base = ['NOMBRE', 'PATERNO', 'MATERNO', 'AÑO']

            if tipo_insignia == "ALUMNO":
                columnas_requeridas = columnas_base + ['CURSO']
                mensaje_error = "❌ El archivo debe contener las columnas: NOMBRE, PATERNO, MATERNO, CURSO y AÑO"
            else:  # DOCENTE
                columnas_requeridas = columnas_base + ['TIPO DE INSIGNEA']
                mensaje_error = "❌ El archivo debe contener las columnas: NOMBRE, PATERNO, MATERNO, TIPO DE INSIGNEA y AÑO"
            
            columnas_faltantes = [col for col in columnas_requeridas if col not in df.columns]

            if columnas_faltantes:
                st.error(f"{mensaje_error}")
                st.error(f"📋 Columnas faltantes: {', '.join(columnas_faltantes)}")
                st.info(f"📋 Columnas encontradas en el archivo: {', '.join(df.columns.tolist())}")
                st.stop()

            df['IDENTIFICADOR'] = (
                df['NOMBRE'].astype(str).str.strip() + ' ' + 
                df['PATERNO'].astype(str).str.strip() + ' ' + 
                df['MATERNO'].astype(str).str.strip()
            )
            df['IDENTIFICADOR'] = df['IDENTIFICADOR'].str.replace(r'\s+', ' ', regex=True).str.strip()
            df['IDENTIFICADOR'] = df['IDENTIFICADOR'].str.replace('NAN', '', regex=True).str.strip()

            def es_vacio(valor):
                if pd.isna(valor):
                    return True
                valor_str = str(valor).strip().upper()
                return valor_str == '' or valor_str == 'NAN' or valor_str == 'NONE'
            
            filas_invalidas = []
            
            for idx, row in df.iterrows():
                campos_vacios = []
                
                if es_vacio(row.get('NOMBRE', '')):
                    campos_vacios.append('NOMBRE')
                if es_vacio(row.get('PATERNO', '')):
                    campos_vacios.append('PATERNO')
                if es_vacio(row.get('MATERNO', '')):
                    campos_vacios.append('MATERNO')
                if es_vacio(row.get('AÑO', '')):
                    campos_vacios.append('AÑO')
                
                if tipo_insignia == "ALUMNO":
                    if es_vacio(row.get('CURSO', '')):
                        campos_vacios.append('CURSO')
                else:  # DOCENTE
                    if es_vacio(row.get('TIPO DE INSIGNEA', '')):
                        campos_vacios.append('TIPO DE INSIGNEA')
                
                if campos_vacios:
                    filas_invalidas.append({
                        'fila': idx + 1,
                        'identificador': row.get('IDENTIFICADOR', 'N/A'),
                        'campos_vacios': ', '.join(campos_vacios)
                    })
            
            total_filas = len(df)

            if filas_invalidas:
                st.error(f"❌ VALIDACIÓN FALLIDA: Se encontraron {len(filas_invalidas)} registro(s) con datos incompletos de {total_filas} totales")
                
                with st.expander(f"🔍 Ver detalles de {len(filas_invalidas)} registro(s) incompleto(s)", expanded=True):
                    st.markdown("**Los siguientes registros tienen campos vacíos:**")
                    
                    df_invalidas = pd.DataFrame(filas_invalidas)
                    df_invalidas.columns = ['Fila Excel', 'Identificador', 'Campos Vacíos']
                    st.dataframe(df_invalidas, hide_index=True, use_container_width=True)
                
                st.error("🛑 **PROCESO DETENIDO**: Todos los registros deben tener datos completos para continuar.")
                st.info("📝 **Instrucciones**: Corrije los registros incompletos en tu archivo Excel y vuelve a subirlo.")
                st.stop()
            else:
                st.success(f"✅ Archivo validado correctamente: {len(df)} registros completos encontrados")
            
            with st.expander("👁️ Vista previa de los datos"):
                df_preview = df.drop(columns=['IDENTIFICADOR'])
                st.dataframe(aplicar_formato_curso_vista(df_preview), hide_index=True)
            
            if st.button("🎨 Generar Insignias PDF", key="generar_insignias", type="primary", use_container_width=True):
                with st.spinner("Generando insignias..."):
                    temp_dir = "temp_insignias"
                    os.makedirs(temp_dir, exist_ok=True)
                    pdf_files = []
                    errores = []
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    total_rows = len(df)

                    for idx, row in df.iterrows():
                        try:
                            status_text.text(f"Procesando insignia {idx + 1} de {total_rows}...")
                            progress_bar.progress((idx + 1) / total_rows)
                            
                            if tipo_insignia == "ALUMNO":
                                imagen_fondo = "plantillas_insignias/ALUMNO.jpg"
                            else:  # DOCENTE
                                tipo_doc = str(row.get("TIPO DE INSIGNEA", "SENIOR")).upper()
                                if "ESPECIALISTA" in tipo_doc:
                                    imagen_fondo = "plantillas_insignias/DOCENTE_ESPECIALISTA.jpg"
                                else:
                                    imagen_fondo = "plantillas_insignias/DOCENTE_SENIOR.jpg"
                            
                            if not os.path.exists(imagen_fondo):
                                errores.append(f"Fila {idx+2}: No se encontró la imagen {imagen_fondo}")
                                continue
                            
                            img = Image.open(imagen_fondo)
                            draw = ImageDraw.Draw(img)
                            font_path = "fonts/trebuchet.ttf"
                            identificador = str(row.get("IDENTIFICADOR", "")).upper()
                            ano = str(row.get("AÑO", "")).upper()
                            tipo_doc = str(row.get("TIPO DE INSIGNEA", "ALUMNO")).upper()
                            
                            if tipo_insignia == "ALUMNO":
                                curso = formatear_curso_salida(row.get("CURSO", ""))

                                config_id = CONFIG_INSIGNIAS['IDENTIFICADOR']
                                draw_centered_text_adaptive(
                                        draw=draw,
                                        text=identificador,
                                        x_center=621,
                                        y_center=435,
                                        font_path=font_path,
                                        font_size_inicial=config_id['font_size_inicial'],
                                        max_width=config_id['max_width'],
                                        max_height=config_id['max_height'],
                                        min_font_size=config_id['min_font_size'],
                                        fill="white"
                                    )
                                    
                                config_curso = CONFIG_INSIGNIAS['CURSO']
                                draw_centered_text_adaptive(
                                        draw=draw,
                                        text=curso,
                                        x_center=621,
                                        y_center=677,
                                        font_path=font_path,
                                        font_size_inicial=config_curso['font_size_inicial'],
                                        max_width=config_curso['max_width'],
                                        max_height=config_curso['max_height'],
                                        min_font_size=config_curso['min_font_size'],
                                        fill="white"
                                    )
                                    
                                config_ano = CONFIG_INSIGNIAS['AÑO']
                                draw_centered_text_adaptive(
                                        draw=draw,
                                        text=ano,
                                        x_center=621,
                                        y_center=926,
                                        font_path=font_path,
                                        font_size_inicial=config_ano['font_size_inicial'],
                                        max_width=config_ano['max_width'],
                                        max_height=config_ano['max_height'],
                                        min_font_size=config_ano['min_font_size'],
                                        fill="white"
                                    )
                                    
                                pdf_name = f"ALUMNO_{identificador}.pdf"
                                    
                            else:  # DOCENTE
                                config_id = CONFIG_INSIGNIAS['IDENTIFICADOR']
                                draw_centered_text_adaptive(
                                        draw=draw,
                                        text=identificador,
                                        x_center=641,
                                        y_center=536,
                                        font_path=font_path,
                                        font_size_inicial=config_id['font_size_inicial'],
                                        max_width=config_id['max_width'],
                                        max_height=config_id['max_height'],
                                        min_font_size=config_id['min_font_size'],
                                        fill="white"
                                    )
                                    
                                config_ano = CONFIG_INSIGNIAS['AÑO']
                                draw_centered_text_adaptive(
                                        draw=draw,
                                        text=ano,
                                        x_center=641,
                                        y_center=905,
                                        font_path=font_path,
                                        font_size_inicial=config_ano['font_size_inicial'],
                                        max_width=config_ano['max_width'],
                                        max_height=config_ano['max_height'],
                                        min_font_size=config_ano['min_font_size'],
                                        fill="white"
                                    )
                                    
                                pdf_name = f"{tipo_doc}_{identificador}.pdf"
                            
                            pdf_name = pdf_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
                            pdf_path = os.path.join(temp_dir, pdf_name)
                            img_rgb = img.convert('RGB')
                            img_rgb.save(pdf_path, "PDF", resolution=100.0)
                            pdf_files.append(pdf_path)
                            
                        except Exception as e:
                            errores.append(f"Fila {idx+2}: {str(e)}")
                    
                    progress_bar.empty()
                    status_text.empty()
                    
                    if pdf_files:
                        st.success(f"✅ Se generaron {len(pdf_files)} insignias correctamente")
                        
                        zip_filename = f"insignias_{tipo_insignia.lower()}.zip"
                        zip_path = os.path.join(temp_dir, zip_filename)
                        
                        with zipfile.ZipFile(zip_path, 'w') as zipf:
                            for pdf_file in pdf_files:
                                zipf.write(pdf_file, os.path.basename(pdf_file))
                        
                        with open(zip_path, 'rb') as f:
                            st.download_button(
                                label="📦 Descargar ZIP con todas las insignias",
                                data=f.read(),
                                file_name=zip_filename,
                                mime="application/zip",
                                use_container_width=True
                            )
                    
                    if errores:
                        st.warning(f"⚠️ Se encontraron {len(errores)} errores:")
                        with st.expander("Ver errores"):
                            for error in errores:
                                st.text(error)
                    
                    try:
                        import shutil
                        if os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir)
                    except:
                        pass

            st.markdown("---")
            if st.button("🔄 Limpiar y Generar nuevas Insignias", use_container_width=True, key="btn_regenerar_insigneas"):
                st.session_state.df_procesado = None
                st.session_state.grupos = None     
                st.session_state.plantillas = None   
                st.session_state.certificados_generados = False
                st.session_state.zip_buffer = None
                st.session_state.tab5_reset_counter += 1
                st.rerun()
                        
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo: {str(e)}")
            st.exception(e)
    
    else:
        st.info("👆 Sube un archivo Excel para comenzar a generar insignias")