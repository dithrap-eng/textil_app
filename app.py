import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import date
import numpy as np 
import time
from collections import defaultdict

# =====================
# CONFIGURACIÓN OPTIMIZADA GOOGLE SHEETS
# =====================
SHEET_NAME = "textil_sistema"

@st.cache_resource(ttl=1800)  # 30 minutos para la conexión
def init_connection():
    """Conexión más robusta a Google Sheets"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], 
                scopes=scope
            )
            client = gspread.authorize(creds)
            
            # Test de conexión
            sheet = client.open(SHEET_NAME)
            print(f"✅ Conexión exitosa a Google Sheets (intento {attempt + 1})")
            return client
            
        except Exception as e:
            if attempt == max_retries - 1:
                st.error(f"❌ Error de conexión después de {max_retries} intentos: {str(e)}")
                return None
            time.sleep(2)  # Esperar antes de reintentar

client = init_connection()

@st.cache_data(ttl=300)  # 5 minutos de caché para datos
def cargar_hoja(hoja_nombre):
    """Carga una hoja completa con manejo de errores"""
    try:
        if not client:
            return pd.DataFrame()
        
        sheet = client.open(SHEET_NAME).worksheet(hoja_nombre)
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Limpiar filas completamente vacías
        df = df.dropna(how='all')
        
        return df
        
    except Exception as e:
        print(f"⚠️ Error al cargar {hoja_nombre}: {str(e)}")
        return pd.DataFrame()

def guardar_hoja(df, hoja_nombre):
    """Guarda DataFrame en Google Sheet"""
    try:
        if not client:
            return False
        
        sheet = client.open(SHEET_NAME).worksheet(hoja_nombre)
        
        # Limpiar hoja existente
        sheet.clear()
        
        # Agregar encabezados primero
        if not df.empty:
            headers = df.columns.tolist()
            sheet.append_row(headers)
            
            # Agregar datos fila por fila
            for _, row in df.iterrows():
                sheet.append_row(row.tolist())
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error al guardar {hoja_nombre}: {str(e)}")
        return False

# =====================
# FUNCIONES DE GUARDADO OPTIMIZADAS
# =====================
def insert_purchase(fecha, proveedor, tipo_tela, precio_por_metro, total_metros, lineas):
    """Versión optimizada de inserción de compra"""
    try:
        # Cargar datos actuales (lotes completos)
        df_compras = cargar_hoja("Compras")
        df_detalle = cargar_hoja("Detalle_Compras")
        df_stock = cargar_hoja("Stock")
        
        # Inicializar DataFrames si están vacíos
        if df_compras.empty:
            df_compras = pd.DataFrame(columns=[
                "ID", "Fecha", "Proveedor", "Tipo de tela", "Total metros", 
                "Precio por metro", "Total rollos", "Valor total", "Precio promedio rollo"
            ])
        
        if df_detalle.empty:
            df_detalle = pd.DataFrame(columns=["ID Compra", "Tipo de tela", "Color", "Rollos"])
        
        if df_stock.empty:
            df_stock = pd.DataFrame(columns=["Tipo de tela", "Color", "Rollos"])
        
        # Generar ID
        compra_id = len(df_compras) + 1 if not df_compras.empty else 1
        
        # Calcular valores
        total_rollos = sum(l["rollos"] for l in lineas)
        total_valor = total_metros * precio_por_metro
        precio_promedio = total_valor / total_rollos if total_rollos > 0 else 0
        
        # 1. Agregar a Compras
        nueva_compra = {
            "ID": compra_id,
            "Fecha": str(fecha),
            "Proveedor": proveedor,
            "Tipo de tela": tipo_tela,
            "Total metros": total_metros,
            "Precio por metro": precio_por_metro,
            "Total rollos": total_rollos,
            "Valor total": total_valor,
            "Precio promedio rollo": precio_promedio
        }
        
        df_compras = pd.concat([df_compras, pd.DataFrame([nueva_compra])], ignore_index=True)
        
        # 2. Agregar a Detalle_Compras (histórico)
        for l in lineas:
            if l["rollos"] > 0:
                nuevo_detalle = {
                    "ID Compra": compra_id,
                    "Tipo de tela": tipo_tela,
                    "Color": l["color"],
                    "Rollos": l["rollos"]
                }
                df_detalle = pd.concat([df_detalle, pd.DataFrame([nuevo_detalle])], ignore_index=True)
        
        # 3. Actualizar Stock
        for l in lineas:
            if l["rollos"] > 0:
                mask = (df_stock["Tipo de tela"] == tipo_tela) & (df_stock["Color"] == l["color"])
                
                if mask.any():
                    # Actualizar existente
                    idx = df_stock[mask].index[0]
                    df_stock.at[idx, "Rollos"] += l["rollos"]
                else:
                    # Agregar nuevo
                    nuevo_stock = {
                        "Tipo de tela": tipo_tela,
                        "Color": l["color"],
                        "Rollos": l["rollos"]
                    }
                    df_stock = pd.concat([df_stock, pd.DataFrame([nuevo_stock])], ignore_index=True)
        
        # 4. Guardar todo (una sola operación por hoja)
        guardar_hoja(df_compras, "Compras")
        guardar_hoja(df_detalle, "Detalle_Compras")
        guardar_hoja(df_stock, "Stock")
        
        # Limpiar caché
        st.cache_data.clear()
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error en compra: {str(e)}")
        return False

def insert_corte(fecha, nro_corte, articulo, tipo_tela, lineas, consumo_total, prendas, consumo_x_prenda):
    """Versión optimizada de inserción de corte"""
    try:
        # Cargar datos actuales (lotes completos)
        df_cortes = cargar_hoja("Cortes")
        df_detalle = cargar_hoja("Detalle_Cortes")
        df_stock = cargar_hoja("Stock")
        
        # Inicializar DataFrames si están vacíos
        if df_cortes.empty:
            df_cortes = pd.DataFrame(columns=[
                "ID", "Fecha", "Número de corte", "Artículo", "Tipo de tela",
                "Total rollos", "Consumo total", "Prendas", "Consumo por prenda"
            ])
        
        if df_detalle.empty:
            df_detalle = pd.DataFrame(columns=["ID Corte", "Color", "Rollos", "Tipo de tela"])
        
        # Generar ID
        corte_id = len(df_cortes) + 1 if not df_cortes.empty else 1
        
        total_rollos = sum(l["rollos"] for l in lineas)
        
        # 1. Agregar a Cortes
        nuevo_corte = {
            "ID": corte_id,
            "Fecha": str(fecha),
            "Número de corte": nro_corte,
            "Artículo": articulo,
            "Tipo de tela": tipo_tela,
            "Total rollos": total_rollos,
            "Consumo total": consumo_total,
            "Prendas": prendas,
            "Consumo por prenda": consumo_x_prenda
        }
        
        df_cortes = pd.concat([df_cortes, pd.DataFrame([nuevo_corte])], ignore_index=True)
        
        # 2. Agregar a Detalle_Cortes
        for l in lineas:
            nuevo_detalle = {
                "ID Corte": corte_id,
                "Color": l["color"],
                "Rollos": l["rollos"],
                "Tipo de tela": tipo_tela
            }
            df_detalle = pd.concat([df_detalle, pd.DataFrame([nuevo_detalle])], ignore_index=True)
        
        # 3. Actualizar Stock (restar)
        for l in lineas:
            mask = (df_stock["Tipo de tela"] == tipo_tela) & (df_stock["Color"] == l["color"])
            
            if mask.any():
                idx = df_stock[mask].index[0]
                nuevo_stock = df_stock.at[idx, "Rollos"] - l["rollos"]
                df_stock.at[idx, "Rollos"] = max(0, nuevo_stock)  # No negativo
            else:
                st.warning(f"⚠️ No se encontró en stock: {tipo_tela} - {l['color']}")
        
        # 4. Guardar todo (una sola operación por hoja)
        guardar_hoja(df_cortes, "Cortes")
        guardar_hoja(df_detalle, "Detalle_Cortes")
        guardar_hoja(df_stock, "Stock")
        
        # Limpiar caché
        st.cache_data.clear()
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error en corte: {str(e)}")
        return False

# =====================
# CONSULTAS OPTIMIZADAS
# =====================
@st.cache_data(ttl=300)
def get_stock_resumen():
    """Obtiene stock actual desde la hoja Stock"""
    df = cargar_hoja("Stock")
    if df.empty:
        return pd.DataFrame(columns=["Tipo de tela", "Color", "Rollos"])
    
    # Asegurar columnas correctas
    required_cols = ["Tipo de tela", "Color", "Rollos"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        st.error(f"❌ Faltan columnas en Stock: {missing_cols}")
        return pd.DataFrame(columns=required_cols)
    
    # Convertir rollos a numérico y agrupar por si hay duplicados
    df["Rollos"] = pd.to_numeric(df["Rollos"], errors="coerce").fillna(0)
    df_stock = df.groupby(["Tipo de tela", "Color"])["Rollos"].sum().reset_index()
    
    return df_stock

@st.cache_data(ttl=300)
def get_compras_resumen():
    """Obtiene resumen de compras"""
    df = cargar_hoja("Compras")
    if df.empty:
        return pd.DataFrame()
    return df

@st.cache_data(ttl=300)
def get_detalle_compras():
    """Obtiene el detalle de colores por compra"""
    df = cargar_hoja("Detalle_Compras")
    if df.empty:
        return pd.DataFrame()
    return df

@st.cache_data(ttl=3600)  # 1 hora para proveedores (cambia poco)
def get_proveedores():
    """Obtiene lista de proveedores"""
    try:
        df = cargar_hoja("Proveedores")
        if not df.empty and "Nombre" in df.columns:
            return df["Nombre"].dropna().unique().tolist()
        
        # Si no existe la hoja o columna, crear lista vacía
        return []
    except:
        return []

def insert_proveedor(nombre):
    """Inserta un nuevo proveedor"""
    try:
        df = cargar_hoja("Proveedores")
        
        if df.empty:
            df = pd.DataFrame(columns=["Nombre"])
        
        # Verificar si ya existe
        if nombre in df["Nombre"].values:
            st.warning(f"⚠️ El proveedor '{nombre}' ya existe")
            return False
        
        # Agregar nuevo
        nuevo_proveedor = {"Nombre": nombre}
        df = pd.concat([df, pd.DataFrame([nuevo_proveedor])], ignore_index=True)
        
        # Guardar
        if guardar_hoja(df, "Proveedores"):
            st.cache_data.clear()  # Limpiar caché de proveedores
            return True
        return False
        
    except Exception as e:
        st.error(f"❌ Error al agregar proveedor: {str(e)}")
        return False

@st.cache_data(ttl=300)
def get_cortes_resumen():
    """Obtiene resumen de cortes"""
    df = cargar_hoja("Cortes")
    if df.empty:
        return pd.DataFrame()
    return df

@st.cache_data(ttl=300)
def get_talleres_data():
    """Obtiene datos de talleres"""
    df = cargar_hoja("Talleres")
    if df.empty:
        return pd.DataFrame()
    return df

@st.cache_data(ttl=300)
def get_nombre_talleres():
    """Obtiene lista de nombres de talleres"""
    try:
        df = cargar_hoja("Nombre_talleres")
        if not df.empty:
            if "Taller" in df.columns:
                talleres = df["Taller"].dropna().unique().tolist()
            else:
                # Intentar primera columna
                talleres = df.iloc[:, 0].dropna().unique().tolist()
            
            # Filtrar y ordenar
            talleres = [t for t in talleres if str(t).strip()]
            return sorted(list(set(talleres)))
        
        return []
    except:
        return []

@st.cache_data(ttl=300)
def get_historial_entregas():
    """Obtiene historial de entregas"""
    try:
        df = cargar_hoja("Historial_Entregas")
        if df.empty:
            return pd.DataFrame()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_devoluciones():
    """Obtiene datos de devoluciones"""
    try:
        df = cargar_hoja("Devoluciones")
        if df.empty:
            return pd.DataFrame()
        return df
    except:
        return pd.DataFrame()

# =====================
# INTERFAZ STREAMLIT
# =====================
st.set_page_config(page_title="Sistema Textil", layout="wide")

# Actualizar el menú de navegación
menu = st.sidebar.radio(
    "Navegación",
    ["📥 Compras", "📊 Resumen Compras", "📦 Stock", "✂ Cortes", "🏭 Talleres", "👥 Proveedores"]
)

# -------------------------------
# COMPRAS
# -------------------------------
if menu == "📥 Compras":
    st.header("Registrar compra de tela")

    fecha = st.date_input("Fecha", value=date.today())
    proveedores = get_proveedores()
    proveedor = st.selectbox("Proveedor", proveedores if proveedores else ["---"])
    
    # --- TIPO DE TELA ---
    st.subheader("Tipo de Tela")
    
    @st.cache_data(ttl=300)
    def get_telas_existentes():
        """Obtiene los tipos de tela existentes del STOCK"""
        try:
            df_stock = get_stock_resumen()
            if not df_stock.empty and "Tipo de tela" in df_stock.columns:
                return sorted(df_stock["Tipo de tela"].dropna().unique().tolist())
            return []
        except:
            return []
    
    telas_existentes = get_telas_existentes()
    
    # Selector para tipo de tela con opción de agregar nuevo
    opciones_telas = telas_existentes + ["➕ Agregar nuevo tipo de tela"]
    
    seleccion_tela = st.selectbox(
        "Tipo de tela", 
        options=opciones_telas,
        index=0,
        help="Selecciona un tipo de tela existente en el stock o 'Agregar nuevo' para crear uno"
    )
    
    if seleccion_tela == "➕ Agregar nuevo tipo de tela":
        tela_nueva = st.text_input(
            "Nuevo tipo de tela",
            placeholder="Escribe el nombre del nuevo tipo de tela...",
            help="El tipo de tela se guardará con formato 'Primera Mayúscula'"
        )
        tipo_tela = tela_nueva.strip()
    else:
        tipo_tela = seleccion_tela
    
    # Normalizar el tipo de tela (primera letra mayúscula, resto minúsculas)
    if tipo_tela and tipo_tela != "➕ Agregar nuevo tipo de tela":
        tipo_tela = tipo_tela.title().strip()
        
        # Mostrar advertencia si el tipo de tela nuevo es similar a uno existente
        if seleccion_tela == "➕ Agregar nuevo tipo de tela" and telas_existentes:
            telas_similares = [t for t in telas_existentes if t.lower() == tipo_tela.lower()]
            if telas_similares:
                st.warning(f"💡 **Tipo de tela similar existe**: '{telas_similares[0]}'. ¿Quieres usar el existente?")
                
                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.button(f"Usar '{telas_similares[0]}'", key="usar_tela_existente"):
                        tipo_tela = telas_similares[0]
                        st.rerun()
                with col2:
                    st.info("Si continúas con el nuevo nombre, se creará como un tipo de tela diferente.")
    
    # Mostrar el tipo de tela que se va a registrar
    if tipo_tela and tipo_tela != "➕ Agregar nuevo tipo de tela":
        st.info(f"🎯 **Tipo de tela a registrar:** {tipo_tela}")
    
    precio_por_metro = st.number_input("Precio por metro (USD)", min_value=0.0, step=0.5)
    total_metros = st.number_input("Total de metros de la compra", min_value=0.0, step=0.5)

    st.subheader("Colores y rollos")
    
    @st.cache_data(ttl=300)
    def get_colores_existentes():
        try:
            df_stock = get_stock_resumen()
            if not df_stock.empty and "Color" in df_stock.columns:
                return sorted(df_stock["Color"].dropna().unique().tolist())
            return []
        except:
            return []
    
    colores_existentes = get_colores_existentes()
    
    lineas = []
    num_colores = st.number_input("Cantidad de colores", min_value=1, max_value=10, value=3, step=1)
    
    for i in range(num_colores):
        col1, col2 = st.columns([2,1])
        with col1:
            opciones_colores = colores_existentes + ["➕ Agregar nuevo color"]
            
            seleccion_color = st.selectbox(
                f"Color {i+1}", 
                options=opciones_colores,
                index=0,
                key=f"color_select_{i}",
                help="Selecciona un color existente en el stock o 'Agregar nuevo color' para crear uno"
            )
            
            if seleccion_color == "➕ Agregar nuevo color":
                color_nuevo = st.text_input(
                    f"Nuevo color {i+1}",
                    key=f"color_nuevo_{i}",
                    placeholder="Escribe el nombre del nuevo color...",
                    help="El color se guardará con formato 'Primera Mayúscula'"
                )
                color = color_nuevo.strip()
            else:
                color = seleccion_color
            
            if color and color != "➕ Agregar nuevo color":
                color = color.title().strip()
                
                if seleccion_color == "➕ Agregar nuevo color" and colores_existentes:
                    colores_similares = [c for c in colores_existentes if c.lower() == color.lower()]
                    if colores_similares:
                        st.warning(f"💡 **Color similar existe**: '{colores_similares[0]}'. ¿Quieres usar el existente?")
                        
                        if st.button(f"Usar '{colores_similares[0]}'", key=f"usar_existente_{i}"):
                            color = colores_similares[0]
                            st.rerun()
        
        with col2:
            rollos = st.number_input(f"Rollos {i+1}", min_value=0, step=1, key=f"rollos_{i}")
        
        if color and color != "➕ Agregar nuevo color" and rollos > 0:
            lineas.append({"color": color, "rollos": rollos})

    if lineas:
        st.markdown("---")
        st.subheader("🎨 Resumen de colores a registrar")
        
        resumen_colores = defaultdict(int)
        for linea in lineas:
            resumen_colores[linea["color"]] += linea["rollos"]
        
        for color in sorted(resumen_colores.keys()):
            total_rollos = resumen_colores[color]
            st.write(f"• **{color}**: {total_rollos} rollo{'s' if total_rollos > 1 else ''}")

    # Mostrar resumen completo antes de guardar
    if tipo_tela and tipo_tela != "➕ Agregar nuevo tipo de tela" and lineas and total_metros > 0 and precio_por_metro > 0:
        total_rollos = sum(l["rollos"] for l in lineas)
        total_valor = total_metros * precio_por_metro
        
        st.markdown("---")
        st.subheader("📋 Resumen Final de la Compra")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Tipo de Tela:** {tipo_tela}")
            st.write(f"**Proveedor:** {proveedor}")
            st.write(f"**Fecha:** {fecha}")
        with col2:
            st.write(f"**Total metros:** {total_metros:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            st.write(f"**Precio por metro:** USD {precio_por_metro:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            st.write(f"**Total rollos:** {total_rollos}")
        
        st.info(f"💲 **Valor total de la compra:** USD {total_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    if st.button("💾 Guardar compra", type="primary"):
        # Validación final
        if not tipo_tela or tipo_tela == "➕ Agregar nuevo tipo de tela":
            st.error("❌ Debe seleccionar o ingresar un tipo de tela válido")
        elif not lineas:
            st.error("❌ Debe agregar al menos un color con rollos")
        elif total_metros <= 0:
            st.error("❌ El total de metros debe ser mayor a 0")
        elif precio_por_metro <= 0:
            st.error("❌ El precio por metro debe ser mayor a 0")
        else:
            # Verificar colores duplicados
            colores_unicos = set()
            colores_duplicados = []
            
            for linea in lineas:
                color_normalizado = linea["color"]
                if color_normalizado in colores_unicos:
                    colores_duplicados.append(color_normalizado)
                colores_unicos.add(color_normalizado)
            
            if colores_duplicados:
                st.error(f"❌ Colores duplicados: {', '.join(set(colores_duplicados))}")
            else:
                if insert_purchase(fecha, proveedor, tipo_tela, precio_por_metro, total_metros, lineas):
                    st.success("✅ Compra registrada exitosamente!")
                    st.balloons()
                    time.sleep(2)
                    st.rerun()

# -------------------------------
# RESUMEN DE COMPRAS - VERSIÓN SIMPLE CON TABLA
# -------------------------------
elif menu == "📊 Resumen Compras":
    st.header("📊 Resumen de Compras")
    
    # Obtener datos de compras y detalles
    df_compras = get_compras_resumen()
    df_detalle = get_detalle_compras()
    
    if not df_compras.empty:
        # Limpiar y formatear datos
        df_compras["Total metros"] = pd.to_numeric(df_compras["Total metros"], errors="coerce")
        df_compras["Precio por metro"] = pd.to_numeric(df_compras["Precio por metro"], errors="coerce")
        df_compras["Total rollos"] = pd.to_numeric(df_compras["Total rollos"], errors="coerce")
        df_compras["Valor total"] = pd.to_numeric(df_compras["Valor total"], errors="coerce")
        df_compras["Precio promedio rollo"] = pd.to_numeric(df_compras["Precio promedio rollo"], errors="coerce")
        
        # Formatear fecha
        if "Fecha" in df_compras.columns:
            df_compras["Fecha"] = pd.to_datetime(df_compras["Fecha"], errors='coerce')
            df_compras["Fecha"] = df_compras["Fecha"].dt.strftime("%d/%m/%Y")
        
        # Función para formatear números en estilo argentino
        def formato_argentino(valor, es_moneda=False):
            if pd.isna(valor) or valor == 0:
                return ""
            formatted = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"USD {formatted}" if es_moneda else formatted
        
        # Aplicar formato a las columnas numéricas
        df_mostrar = df_compras.copy()
        
        # Seleccionar y ordenar columnas para mostrar - AGREGAR ID PRIMERO
        columnas_mostrar = []
        mapeo_columnas = {
            "ID": "ID Compra",
            "Fecha": "Fecha",
            "Proveedor": "Proveedor", 
            "Tipo de tela": "Tipo de Tela",
            "Total metros": "Total Metros",
            "Total rollos": "Total Rollos",
            "Precio por metro": "Precio x Metro",
            "Valor total": "Total USD",
            "Precio promedio rollo": "Precio Promedio x Rollo"
        }
        
        for col_original, col_nuevo in mapeo_columnas.items():
            if col_original in df_mostrar.columns:
                columnas_mostrar.append(col_nuevo)
                if col_original in ["Precio por metro", "Valor total", "Precio promedio rollo"]:
                    df_mostrar[col_nuevo] = df_mostrar[col_original].apply(lambda x: formato_argentino(x, True))
                elif col_original == "Total metros":
                    df_mostrar[col_nuevo] = df_mostrar[col_original].apply(formato_argentino)
                elif col_original == "Total rollos":
                    df_mostrar[col_nuevo] = df_mostrar[col_original].astype(int)
                else:
                    df_mostrar[col_nuevo] = df_mostrar[col_original]
        
        # Mostrar tabla principal de compras
        st.subheader("📋 Historial de Compras")
        st.dataframe(df_mostrar[columnas_mostrar], use_container_width=True)
        
        # --- DETALLES DE COLORES POR COMPRA ---
        st.markdown("---")
        st.subheader("🎨 Detalles de Colores por Compra")
        
        if not df_detalle.empty and "ID Compra" in df_detalle.columns:
            # Crear lista de compras con ID + Tipo de Tela para mejor identificación
            compras_con_info = []
            for compra_id in df_compras["ID"].unique():
                tipo_tela = df_compras[df_compras["ID"] == compra_id]["Tipo de tela"].iloc[0] if "Tipo de tela" in df_compras.columns else "N/A"
                compras_con_info.append({
                    "id": compra_id,
                    "display": f"ID: {compra_id} - {tipo_tela}"
                })
            
            # Ordenar por ID descendente (más reciente primero)
            compras_con_info.sort(key=lambda x: x["id"], reverse=True)
            
            if compras_con_info:
                compra_seleccionada = st.selectbox(
                    "Selecciona una compra para ver los detalles de colores:",
                    options=[c["id"] for c in compras_con_info],
                    format_func=lambda x: next((c["display"] for c in compras_con_info if c["id"] == x), f"ID: {x}")
                )
                
                # Filtrar detalles de la compra seleccionada
                detalle_compra = df_detalle[df_detalle["ID Compra"] == compra_seleccionada]
                
                if not detalle_compra.empty:
                    # Obtener información de la compra principal
                    info_compra = df_compras[df_compras["ID"] == compra_seleccionada].iloc[0]
                    
                    # Mostrar información general de la compra
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.write(f"**ID Compra:** {compra_seleccionada}")
                    with col2:
                        st.write(f"**Proveedor:** {info_compra.get('Proveedor', 'N/A')}")
                    with col3:
                        st.write(f"**Tipo de Tela:** {info_compra.get('Tipo de tela', 'N/A')}")
                    with col4:
                        st.write(f"**Fecha:** {info_compra.get('Fecha', 'N/A')}")
                    
                    # Mostrar tabla de colores
                    df_colores = detalle_compra[["Color", "Rollos"]].copy()
                    df_colores = df_colores.groupby("Color")["Rollos"].sum().reset_index()
                    df_colores = df_colores.sort_values("Rollos", ascending=False)
                    
                    st.dataframe(df_colores, use_container_width=True)
                    
                    # Mostrar resumen
                    total_colores = len(df_colores)
                    total_rollos_color = df_colores["Rollos"].sum()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("🎨 Total de Colores", total_colores)
                    with col2:
                        st.metric("📦 Total de Rollos", total_rollos_color)
                else:
                    st.info("No se encontraron detalles de colores para esta compra.")
            else:
                st.info("No hay compras disponibles para mostrar detalles.")
        else:
            st.info("No hay información de detalles de colores disponible.")
        
        # --- ESTADÍSTICAS GENERALES ---
        st.markdown("---")
        st.subheader("📈 Estadísticas Generales")
        
        total_compras = len(df_compras)
        total_inversion = df_compras["Valor total"].sum()
        total_metros = df_compras["Total metros"].sum()
        total_rollos = df_compras["Total rollos"].sum()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("🛒 Total Compras", total_compras)
        with col2:
            st.metric("💰 Inversión Total", formato_argentino(total_inversion, True))
        with col3:
            st.metric("📏 Metros Totales", f"{total_metros:,.0f}")
        with col4:
            st.metric("📦 Rollos Totales", f"{total_rollos:,.0f}")
            
    else:
        st.info("No hay compras registradas aún.")

# -------------------------------
# STOCK (CON GRÁFICO DE COMPARACIÓN VISUAL Y VALORIZACIÓN)
# -------------------------------
elif menu == "📦 Stock":
    st.header("📦 Stock disponible (en rollos)")

    df = get_stock_resumen()
    if df.empty:
        st.warning("No hay stock registrado")
    else:
        # Crear DataFrames separados
        df_con_stock = df[df["Rollos"] > 0]
        df_sin_stock = df[df["Rollos"] == 0]
        
        # Mostrar resumen rápido
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📊 Telas con Stock", len(df_con_stock["Tipo de tela"].unique()))
        with col2:
            st.metric("🎨 Colores Activos", len(df_con_stock["Color"].unique()))
        with col3:
            st.metric("📦 Total Rollos", df_con_stock["Rollos"].sum())
        
        # Filtros SOLO con telas que tienen stock
        st.subheader("🔍 Filtros")
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            telas_con_stock = sorted(df_con_stock["Tipo de tela"].unique())
            filtro_tela = st.multiselect(
                "Filtrar por tela", 
                telas_con_stock,
                placeholder="Todas las telas con stock"
            )
        
        with col_f2:
            if filtro_tela:
                colores_filtrados = df_con_stock[df_con_stock["Tipo de tela"].isin(filtro_tela)]["Color"].unique()
            else:
                colores_filtrados = df_con_stock["Color"].unique()
            
            filtro_color = st.multiselect(
                "Filtrar por color", 
                sorted(colores_filtrados),
                placeholder="Todos los colores"
            )

        # Aplicar filtros
        df_filtrado = df_con_stock.copy()
        
        if filtro_tela:
            df_filtrado = df_filtrado[df_filtrado["Tipo de tela"].isin(filtro_tela)]
        if filtro_color:
            df_filtrado = df_filtrado[df_filtrado["Color"].isin(filtro_color)]
        
        # Mostrar tabla principal
        if not df_filtrado.empty:
            st.subheader("📋 Stock Disponible")
            
            # Agregar indicadores visuales
            def estilo_fila(row):
                rollos = row["Rollos"]
                if rollos >= 10:
                    return "✅ Buen stock"
                elif rollos >= 5:
                    return "⚠️ Stock medio"
                else:
                    return "🔴 Stock bajo"
            
            df_mostrar = df_filtrado.copy()
            df_mostrar["Estado"] = df_mostrar.apply(estilo_fila, axis=1)
            df_mostrar = df_mostrar[["Tipo de tela", "Color", "Rollos", "Estado"]]
            
            st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
            
            # GRÁFICO DE COMPARACIÓN VISUAL
            st.markdown("---")
            st.subheader("📊 Comparación Visual de Stock")
            
            # Preparar datos para el gráfico
            resumen_telas = df_filtrado.groupby("Tipo de tela").agg({
                "Rollos": "sum",
                "Color": "nunique"
            }).round(0)
            
            resumen_telas.columns = ["Total Rollos", "Cantidad Colores"]
            resumen_telas = resumen_telas.sort_values("Total Rollos", ascending=False)
            
            # Gráfico de barras de progreso personalizado
            st.write("**Distribución de Stock por Tela:**")
            
            for tela, datos in resumen_telas.iterrows():
                rollos = int(datos["Total Rollos"])
                colores = int(datos["Cantidad Colores"])
                max_rollos = resumen_telas["Total Rollos"].max()
                porcentaje = (rollos / max_rollos) * 100 if max_rollos > 0 else 0
                
                # Determinar color según cantidad
                if rollos >= 6:
                    color_barra = "#4CAF50"  # Verde
                    emoji = "✅"
                elif rollos >= 3:
                    color_barra = "#FF9800"  # Naranja
                    emoji = "⚠️"
                else:
                    color_barra = "#F44336"  # Rojo
                    emoji = "🔴"
                
                st.markdown(f"""
                <div style='margin: 15px 0; padding: 10px; background: #f8f9fa; border-radius: 8px;'>
                    <div style='display: flex; justify-content: space-between; margin-bottom: 8px;'>
                        <span style='font-weight: bold;'>{emoji} {tela}</span>
                        <span style='font-weight: bold;'>{rollos} rollos</span>
                    </div>
                    <div style='background: #e0e0e0; border-radius: 10px; height: 20px; position: relative;'>
                        <div style='background: {color_barra}; height: 100%; border-radius: 10px; width: {porcentaje}%; 
                                    transition: width 0.5s;'></div>
                    </div>
                    <div style='display: flex; justify-content: space-between; margin-top: 5px; font-size: 12px; color: #666;'>
                        <span>🎨 {colores} color{'es' if colores != 1 else ''}</span>
                        <span>{porcentaje:.0f}% del máximo</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # SECCIÓN DE VALORIZACIÓN
            st.markdown("---")
            st.subheader("💰 Valorización del Stock")
            
            # Obtener el resumen de compras para calcular precios promedios
            df_compras = get_compras_resumen()
            total_rollos_filtrado = df_filtrado["Rollos"].sum()
            
            # 1. Mostrar precio promedio por tipo de tela seleccionado
            if not df_compras.empty and "Precio promedio rollo" in df_compras.columns:
                # Función para convertir correctamente el formato argentino
                def convertir_formato_argentino(valor):
                    if pd.isna(valor):
                        return 0.0
                    if isinstance(valor, (int, float)):
                        return float(valor)
                    valor_str = str(valor).replace("USD", "").replace(" ", "").strip()
                    try:
                        # Si tiene formato 15.012,00 -> convertir a 15012.00
                        if "." in valor_str and "," in valor_str:
                            return float(valor_str.replace(".", "").replace(",", "."))
                        # Si tiene formato 150,12 -> convertir a 150.12
                        elif "," in valor_str:
                            return float(valor_str.replace(",", "."))
                        else:
                            return float(valor_str)
                    except:
                        return 0.0
                
                # Función para formatear en estilo argentino
                def formato_argentino_moneda(valor):
                    if pd.isna(valor) or valor == 0:
                        return "USD 0,00"
                    formatted = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    return f"USD {formatted}"
                
                # Convertir la columna de precios
                df_compras["Precio promedio rollo num"] = df_compras["Precio promedio rollo"].apply(convertir_formato_argentino)
                
                # Calcular precio promedio por tipo de tela si hay filtro
                precios_telas = {}
                if filtro_tela:
                    for tela in filtro_tela:
                        precio_promedio_tela = df_compras[
                            df_compras["Tipo de tela"] == tela
                        ]["Precio promedio rollo num"].mean()
                        
                        if not pd.isna(precio_promedio_tela) and precio_promedio_tela > 0:
                            precio_corregido = precio_promedio_tela
                            precios_telas[tela] = precio_corregido
                
                # Mostrar precios individuales si hay múltiples telas
                if precios_telas:
                    st.write("**Precios Promedio por Tela:**")
                    for tela, precio in precios_telas.items():
                        st.write(f"• **{tela}**: {formato_argentino_moneda(precio)} x rollo")
                
                # 2. Calcular valor estimado CORRECTAMENTE
                if precios_telas:
                    if len(precios_telas) == 1:
                        precio_promedio_global = list(precios_telas.values())[0]
                    else:
                        precio_promedio_global = sum(precios_telas.values()) / len(precios_telas)
                    
                    # Calcular valorización
                    total_valorizado = total_rollos_filtrado * precio_promedio_global
                    
                    # Mostrar métricas de valorización
                    col_v1, col_v2, col_v3 = st.columns(3)
                    
                    with col_v1:
                        st.metric("📦 Total Rollos", total_rollos_filtrado)
                    
                    with col_v2:
                        st.metric("💰 Precio Promedio", formato_argentino_moneda(precio_promedio_global))
                    
                    with col_v3:
                        st.metric("💲 Valor Total", formato_argentino_moneda(total_valorizado))
                    
                    # Detalle adicional
                    st.info(f"**Valorización calculada:** {total_rollos_filtrado} rollos × {formato_argentino_moneda(precio_promedio_global)} = **{formato_argentino_moneda(total_valorizado)}**")
                else:
                    st.info("ℹ️ No hay información de precios para las telas seleccionadas")
            else:
                st.info("ℹ️ No hay información de precios disponible para valorización")
            
            # Totales generales
            st.markdown("---")
            st.subheader("📈 Totales Generales")
            
            total_telas_filtrado = len(df_filtrado["Tipo de tela"].unique())
            total_colores_filtrado = len(df_filtrado["Color"].unique())
            
            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                st.metric("📦 Total Rollos", total_rollos_filtrado)
            with col_t2:
                st.metric("🎨 Tipos de Tela", total_telas_filtrado)
            with col_t3:
                st.metric("🌈 Colores", total_colores_filtrado)
                
        else:
            st.info("ℹ️ No hay stock disponible con los filtros aplicados")
        
        # Sección informativa sobre stock cero
        with st.expander("📋 Ver telas sin stock"):
            if not df_sin_stock.empty:
                st.write("Estas telas actualmente no tienen stock:")
                st.dataframe(df_sin_stock[["Tipo de tela", "Color", "Rollos"]], use_container_width=True)
            else:
                st.success("🎉 ¡Todas las telas tienen stock disponible!")

# -------------------------------
# CORTES (CON DESGLOSE POR ROLLOS Y TOTALES AUTOMÁTICOS)
# -------------------------------
elif menu == "✂ Cortes":
    st.header("Registrar corte de tela")

    fecha = st.date_input("Fecha de corte", value=date.today())
    nro_corte = st.text_input("Número de corte")
    articulo = st.text_input("Artículo")

    df_stock = get_stock_resumen()
    telas = df_stock["Tipo de tela"].unique() if not df_stock.empty else []
    tipo_tela = st.selectbox("Tela usada", telas if len(telas) else ["---"])

    # Filtrar colores con stock > 0
    if not df_stock.empty and tipo_tela != "---":
        stock_tela = df_stock[df_stock["Tipo de tela"] == tipo_tela]
        colores_con_stock = stock_tela[stock_tela["Rollos"] > 0]["Color"].unique()
        colores_sin_stock = stock_tela[stock_tela["Rollos"] == 0]["Color"].unique()
    else:
        colores_con_stock = []
        colores_sin_stock = []

    colores_sel = st.multiselect(
        "Colores usados", 
        colores_con_stock,
        help="Solo se muestran colores con stock disponible"
    )

    # Mostrar información sobre colores sin stock
    if len(colores_sin_stock) > 0:
        st.info(f"ℹ️ Colores sin stock disponible: {', '.join(colores_sin_stock)}")

    # ================================
    # MODO DE CARGA: TOTALES vs DESGLOSE POR ROLLO
    # ================================
    st.subheader("📊 Gestión de Colores y Talles")
    
    if colores_sel:
        # Selección del modo de carga
        modo_carga = st.radio(
            "Seleccione el modo de carga:",
            ["📋 Por totales (actual)", "📦 Desglosado por rollos"],
            help="""Por totales: Carga cantidades totales por color\nDesglosado por rollos: Crea una fila por cada rollo utilizado"""
        )
        
        talles = [5, 6, 7, 8, 9, 10]
        lineas = []
        suma_total_color = 0
        
        if modo_carga == "📋 Por totales (actual)":
            # MODO ACTUAL (TOTALES)
            tabla_data = {}
            totales_x_color = []
            totales_rollos = []
            
            st.write("Complete las cantidades por color y talle:")
        
            # Encabezado
            cols = st.columns(len(talles) + 4)
            cols[0].markdown("**Color**")
            for j, t in enumerate(talles):
                cols[j+1].markdown(f"**{t}**")
            cols[-3].markdown("**Total x color**")
            cols[-2].markdown("**Stock actual**")
            cols[-1].markdown("**Total rollos**")
        
            # Filas dinámicas por color
            for c in colores_sel:
                valores_fila = []
                total_color = 0
        
                cols = st.columns(len(talles) + 4)
                cols[0].write(f"🎨 {c}")
        
                for j, t in enumerate(talles):
                    val = cols[j+1].number_input(
                        f"{c}_{t}",
                        min_value=0,
                        step=1,
                        key=f"total_{c}_{t}"
                    )
                    valores_fila.append(val)
                    total_color += val
        
                # Total x color (resaltado)
                cols[-3].markdown(
                    f"<div style='background-color:#ffcccb; color:black; text-align:center; padding:6px; "
                    f"border-radius:6px; font-weight:bold;'>{total_color}</div>",
                    unsafe_allow_html=True
                )
        
                # Stock real desde df_stock
                stock_color = int(df_stock[(df_stock["Tipo de tela"] == tipo_tela) & 
                                           (df_stock["Color"] == c)]["Rollos"].sum())
        
                # Campo manual para rollos consumidos
                total_rollos = cols[-1].number_input(
                    f"Rollos {c}",
                    min_value=0,
                    max_value=stock_color,
                    step=1,
                    key=f"rollos_total_{c}"
                )
        
                # Stock actualizado dinámicamente
                stock_disp = stock_color - total_rollos
                if stock_disp > 5:
                    cols[-2].success(f"{stock_disp}")
                elif stock_disp > 2:
                    cols[-2].warning(f"{stock_disp}")
                else:
                    cols[-2].error(f"{stock_disp}")
        
                # Guardar info
                tabla_data[c] = valores_fila
                lineas.append({"color": c, "rollos": total_rollos, "tipo_tela": tipo_tela})
        
                totales_x_color.append(total_color)
                totales_rollos.append(total_rollos)
                suma_total_color += total_color
        
            # Totales por columna (x talle)
            st.markdown("---")
            cols = st.columns(len(talles) + 4)
            cols[0].markdown("**Total x talle**")
            for j, t in enumerate(talles):
                suma_col = sum(tabla_data[c][j] for c in colores_sel)
                cols[j+1].markdown(
                    f"<div style='background-color:#d1e7dd; padding:6px; border-radius:6px; text-align:center;'><b>{suma_col}</b></div>",
                    unsafe_allow_html=True
                )
        
            # Totales generales
            suma_total_rollos = sum(totales_rollos)
        
            cols[-3].markdown(
                f"<div style='background-color:#dc3545; color:white; padding:8px; border-radius:8px; text-align:center; font-size:16px; font-weight:bold;'>"
                f"{suma_total_color}</div>",
                unsafe_allow_html=True
            )
            cols[-2].markdown(" ")
            cols[-1].markdown(
                f"<div style='background-color:#0d6efd; color:white; padding:8px; border-radius:8px; text-align:center; font-size:16px; font-weight:bold;'>"
                f"{suma_total_rollos}</div>",
                unsafe_allow_html=True
            )
            
        else:
            # MODO DESGLOSADO POR ROLLOS (ACTUALIZADO)
            st.info("💡 **Modo desglosado:** Se creará una fila por cada rollo utilizado")
            
            # Crear estructura para almacenar datos
            tabla_data = {}
            totales_x_color = {}
            totales_rollos = {}
            
            # Encabezado de tabla para modo desglosado
            st.write("### 📊 Desglose por Rollos")
            cols = st.columns(len(talles) + 4)
            cols[0].markdown("**Color / Rollo**")
            for j, t in enumerate(talles):
                cols[j+1].markdown(f"**{t}**")
            cols[-3].markdown("**Total x rollo**")
            cols[-2].markdown("**Stock actual**")
            cols[-1].markdown("**Rollos usados**")
            
            for c in colores_sel:
                st.markdown(f"### 🎨 Color: {c}")
                
                # Stock disponible para este color
                stock_color = int(df_stock[(df_stock["Tipo de tela"] == tipo_tela) & 
                                           (df_stock["Color"] == c)]["Rollos"].sum())
                
                # Número de rollos a utilizar
                num_rollos = st.number_input(
                    f"¿Cuántos rollos de {c} utilizará?",
                    min_value=1,
                    max_value=stock_color,
                    value=1,
                    step=1,
                    key=f"num_rollos_{c}"
                )
                
                # Inicializar datos para este color
                tabla_data[c] = []
                total_color = 0
                
                # Crear filas para cada rollo
                for rollo_num in range(1, num_rollos + 1):
                    # Crear fila para el rollo
                    cols_rollo = st.columns(len(talles) + 4)
                    cols_rollo[0].write(f"Rollo {rollo_num}")
                    
                    valores_rollo = []
                    total_rollo = 0
                    
                    # Inputs para cada talle
                    for j, t in enumerate(talles):
                        val = cols_rollo[j+1].number_input(
                            f"{c}_rollo{rollo_num}_{t}",
                            min_value=0,
                            step=1,
                            key=f"rollo_{c}_{rollo_num}_{t}",
                            label_visibility="collapsed"
                        )
                        valores_rollo.append(val)
                        total_rollo += val
                    
                    # Mostrar total del rollo
                    cols_rollo[-3].markdown(
                        f"<div style='background-color:#e7f3ff; padding:4px; border-radius:4px; text-align:center;'><b>{total_rollo}</b></div>",
                        unsafe_allow_html=True
                    )
                    
                    # Mostrar stock actual (solo en primera fila del color)
                    if rollo_num == 1:
                        stock_disp = stock_color - num_rollos
                        if stock_disp > 5:
                            cols_rollo[-2].success(f"{stock_disp}")
                        elif stock_disp > 2:
                            cols_rollo[-2].warning(f"{stock_disp}")
                        else:
                            cols_rollo[-2].error(f"{stock_disp}")
                    else:
                        cols_rollo[-2].write("")
                    
                    # Mostrar rollos usados (solo en primera fila del color)
                    if rollo_num == 1:
                        cols_rollo[-1].markdown(
                            f"<div style='background-color:#d4edda; padding:4px; border-radius:4px; text-align:center;'><b>{num_rollos}</b></div>",
                            unsafe_allow_html=True
                        )
                    else:
                        cols_rollo[-1].write("")
                    
                    # Guardar datos del rollo
                    tabla_data[c].append(valores_rollo)
                    total_color += total_rollo
                    
                    # Agregar a lineas (cada rollo es una línea separada)
                    lineas.append({"color": c, "rollos": 1, "tipo_tela": tipo_tela})
                
                # Guardar totales por color
                totales_x_color[c] = total_color
                totales_rollos[c] = num_rollos
                suma_total_color += total_color
                
                # Mostrar resumen del color
                st.success(f"**Total {c}:** {total_color} prendas en {num_rollos} rollo{'s' if num_rollos > 1 else ''}")
                st.markdown("---")
            
            # SECCIÓN DE TOTALES PARA MODO DESGLOSADO
            st.subheader("📊 Totales Generales")
            
            # Totales por columna (x talle)
            cols_totales = st.columns(len(talles) + 4)
            cols_totales[0].markdown("**Total x talle**")
            
            # Calcular totales por talle
            for j, t in enumerate(talles):
                suma_col = 0
                for c in colores_sel:
                    for rollo_data in tabla_data[c]:
                        suma_col += rollo_data[j]
                
                cols_totales[j+1].markdown(
                    f"<div style='background-color:#d1e7dd; padding:6px; border-radius:6px; text-align:center;'><b>{suma_col}</b></div>",
                    unsafe_allow_html=True
                )
            
            # Totales generales
            suma_total_rollos = sum(totales_rollos.values())
            suma_total_prendas = sum(totales_x_color.values())
            
            cols_totales[-3].markdown(
                f"<div style='background-color:#dc3545; color:white; padding:8px; border-radius:8px; text-align:center; font-size:16px; font-weight:bold;'>"
                f"{suma_total_prendas}</div>",
                unsafe_allow_html=True
            )
            cols_totales[-2].markdown(" ")
            cols_totales[-1].markdown(
                f"<div style='background-color:#0d6efd; color:white; padding:8px; border-radius:8px; text-align:center; font-size:16px; font-weight:bold;'>"
                f"{suma_total_rollos}</div>",
                unsafe_allow_html=True
            )
    
    else:
        if tipo_tela != "---" and len(colores_con_stock) == 0:
            st.warning("⚠️ No hay colores con stock disponible para la tela seleccionada")
        else:
            st.info("Seleccione colores para habilitar la gestión de talles.")

    # ================================
    # DATOS DE PRODUCCIÓN (MEJORADO)
    # ================================
    st.markdown("---")
    st.subheader("📦 Datos de Producción")
    
    col_consumo, col_prendas = st.columns(2)
    
    with col_consumo:
        consumo_total = st.number_input("Consumo total (m)", min_value=0.0, step=0.5, format="%.2f")
    
    with col_prendas:
        # AUTOMÁTICO: Usar el total calculado en la sección anterior
        prendas_auto = suma_total_color if 'suma_total_color' in locals() and suma_total_color > 0 else 0
        prendas = st.number_input(
            "Cantidad de prendas", 
            min_value=1, 
            step=1,
            value=prendas_auto if prendas_auto > 0 else 1,
            help="Se sugiere automáticamente el total de prendas calculado arriba"
        )
    
    # Mostrar consumo por prenda
    if prendas > 0 and consumo_total > 0:
        consumo_x_prenda = consumo_total / prendas
        st.metric(
            "🧵 Consumo por prenda", 
            f"{consumo_x_prenda:.2f} m",
            help="Consumo total dividido por cantidad de prendas"
        )
    else:
        st.info("ℹ️ Complete consumo total y cantidad de prendas para calcular el consumo por prenda")

    # Información adicional
    if colores_sel and 'suma_total_color' in locals() and suma_total_color > 0:
        if prendas != suma_total_color:
            st.warning(f"💡 El total de prendas calculado en colores y talles es: **{suma_total_color}**")
        else:
            st.success(f"✅ Total de prendas coincidente: **{suma_total_color}**")

    # Botón de guardar
    st.markdown("---")
    col_btn, _ = st.columns([1, 3])
    
    with col_btn:
        if st.button("💾 Guardar corte", type="primary", use_container_width=True):
            # Validaciones
            if not colores_sel:
                st.error("❌ Debe seleccionar al menos un color")
            elif consumo_total <= 0:
                st.error("❌ El consumo total debe ser mayor a 0")
            elif prendas <= 0:
                st.error("❌ La cantidad de prendas debe ser mayor a 0")
            elif 'lineas' not in locals() or not lineas:
                st.error("❌ Debe completar la información de colores y talles")
            else:
                try:
                    # Asegurar que todas las líneas tengan el tipo de tela
                    for linea in lineas:
                        linea["tipo_tela"] = tipo_tela
                    
                    if insert_corte(fecha, nro_corte, articulo, tipo_tela, lineas, consumo_total, prendas, consumo_x_prenda):
                        st.success("✅ Corte registrado y stock actualizado correctamente")
                        st.balloons()
                        time.sleep(2)
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar el corte: {str(e)}")

  # -------------------------------
    # RESUMEN DE CORTES (VERSIÓN CORREGIDA)
    # -------------------------------
    st.subheader("📊 Resumen de cortes registrados")
    
    df_cortes = get_cortes_resumen()
    
    if not df_cortes.empty:
        
        # Buscar nombres alternativos de columnas
        column_mapping = {
            'consumo_total': ['Consumo total', 'Consumo', 'Total metros'],
            'cantidad_prendas': ['Prendas', 'Cantidad prendas', 'Cantidad'],
            'consumo_x_prenda': ['Consumo por prenda', 'Metros por prenda']
        }
        
        # Encontrar los nombres reales de las columnas
        real_columns = {}
        for key, possible_names in column_mapping.items():
            for name in possible_names:
                if name in df_cortes.columns:
                    real_columns[key] = name
                    break
        
        # Convertir columnas numéricas si existen
        if 'consumo_total' in real_columns:
            df_cortes[real_columns['consumo_total']] = pd.to_numeric(
                df_cortes[real_columns['consumo_total']], errors="coerce"
            )
        
        if 'cantidad_prendas' in real_columns:
            df_cortes[real_columns['cantidad_prendas']] = pd.to_numeric(
                df_cortes[real_columns['cantidad_prendas']], errors="coerce"
            )
        
        # Calcular consumo por prenda si no existe la columna
        if 'consumo_x_prenda' not in real_columns and 'consumo_total' in real_columns and 'cantidad_prendas' in real_columns:
            df_cortes['Consumo por prenda'] = df_cortes[real_columns['consumo_total']] / df_cortes[real_columns['cantidad_prendas']]
            real_columns['consumo_x_prenda'] = 'Consumo por prenda'
        
        # Formatear para mostrar
        df_mostrar_cortes = df_cortes.copy()
        
        # Formatear columnas numéricas
        if 'consumo_total' in real_columns:
            df_mostrar_cortes[real_columns['consumo_total']] = df_mostrar_cortes[real_columns['consumo_total']].apply(
                lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(x) else ""
            )
        
        if 'consumo_x_prenda' in real_columns:
            df_mostrar_cortes[real_columns['consumo_x_prenda']] = df_mostrar_cortes[real_columns['consumo_x_prenda']].apply(
                lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(x) else ""
            )
        
        # Mostrar columnas relevantes (usar nombres reales)
        columnas_a_mostrar = []
        for col in ["Fecha", "Número de corte", "Artículo", "Tipo de tela"]:
            if col in df_mostrar_cortes.columns:
                columnas_a_mostrar.append(col)
        
        # Agregar columnas numéricas si existen
        for key in ['consumo_total', 'cantidad_prendas', 'consumo_x_prenda']:
            if key in real_columns:
                columnas_a_mostrar.append(real_columns[key])
        
        st.dataframe(df_mostrar_cortes[columnas_a_mostrar], use_container_width=True)
        
        # Mostrar estadísticas
        if 'consumo_total' in real_columns and 'cantidad_prendas' in real_columns:
            total_consumo = df_cortes[real_columns['consumo_total']].sum()
            total_prendas = df_cortes[real_columns['cantidad_prendas']].sum()
            consumo_promedio = total_consumo / total_prendas if total_prendas > 0 else 0
            
            st.write(f"**Total general:** {total_prendas:,.0f} prendas, {total_consumo:,.2f} m de tela")
                 
    else:
        st.info("No hay cortes registrados aún.")

# -------------------------------
# PROVEEDORES
# -------------------------------
elif menu == "👥 Proveedores":
    st.header("Administrar proveedores")

    nuevo = st.text_input("Nuevo proveedor")
    if st.button("➕ Agregar proveedor"):
        if nuevo:
            if insert_proveedor(nuevo):
                st.success(f"Proveedor '{nuevo}' agregado")
                time.sleep(2)
                st.rerun()
        else:
            st.warning("Ingrese un nombre válido")

    st.subheader("Listado de proveedores")
    proveedores = get_proveedores()
    if proveedores:
        st.table(pd.DataFrame(proveedores, columns=["Proveedor"]))
    else:
        st.info("No hay proveedores registrados aún.")

# -------------------------------
# TALLERES (VERSIÓN COMPLETA UNIFICADA)
# -------------------------------
elif menu == "🏭 Talleres":
    # Configuración de estilo KANBAN CON SCROLL
    st.markdown("""
        <style>
        .metric-card {
            padding: 15px;
            border-radius: 10px;
            border-left: 4px solid;
            margin-bottom: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .pending { border-left-color: #FFA726; background-color: #FFF3E0; }
        .production { border-left-color: #42A5F5; background-color: #E3F2FD; }
        .delivered { border-left-color: #66BB6A; background-color: #E8F5E9; }
        .alert { border-left-color: #EF5350; background-color: #FFEBEE; }
        
        .kanban-column {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #dee2e6;
            margin: 10px 0;
            max-height: 600px;
            overflow-y: auto;
        }
        
        .corte-card {
            background: white;
            padding: 12px;
            margin: 8px 0;
            border-radius: 8px;
            border-left: 4px solid #42A5F5;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            cursor: pointer;
        }
        
        .corte-card:hover {
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }
        
        .corte-card.urgente {
            border-left-color: #EF5350;
            background-color: #FFEBEE;
        }
        
        .corte-card.completado {
            border-left-color: #66BB6A;
            background-color: #E8F5E9;
        }
        
        .progress-bar {
            height: 15px;
            background-color: #e0e0e0;
            border-radius: 10px;
            margin: 8px 0;
        }
        
        .progress-fill {
            height: 100%;
            border-radius: 10px;
            background: linear-gradient(90deg, #42A5F5, #64B5F6);
        }
        
        .green-button {
            background-color: #4CAF50 !important;
            color: white !important;
            border: none !important;
        }
        
        /* Scroll personalizado */
        .kanban-column::-webkit-scrollbar {
            width: 8px;
        }
        
        .kanban-column::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 4px;
        }
        
        .kanban-column::-webkit-scrollbar-thumb {
            background: #c1c1c1;
            border-radius: 4px;
        }
        
        .kanban-column::-webkit-scrollbar-thumb:hover {
            background: #a8a8a8;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.header("📋 Tablero de Producción - Talleres")

    # Cargar todos los datos necesarios
    df_cortes = get_cortes_resumen()
    df_historial = get_historial_entregas()
    df_devoluciones = get_devoluciones()
    df_talleres = get_talleres_data()
    
    # Obtener lista de talleres
    talleres_existentes = get_nombre_talleres()
    
    if not df_cortes.empty:
        # ==============================================
        # 📊 SECCIÓN 1: RESUMEN GENERAL Y ASIGNACIÓN
        # ==============================================
        
        # Calcular métricas para el header
        cortes_sin_asignar = df_cortes[~df_cortes["ID"].astype(str).isin(df_talleres["ID Corte"].astype(str))] if not df_talleres.empty else df_cortes
        
        en_produccion = len(df_talleres[df_talleres["Estado"] == "EN PRODUCCIÓN"]) if not df_talleres.empty else 0
        entregados = len(df_talleres[df_talleres["Estado"].str.contains("ENTREGADO", na=False)]) if not df_talleres.empty else 0
        
        # CALCULAR ALERTAS
        alertas = 0
        if not df_talleres.empty:
            # Cortes con faltantes
            cortes_faltantes = df_talleres[df_talleres["Estado"] == "ENTREGADO c/FALTANTES"]
            
            # Cortes con devoluciones
            cortes_devoluciones = df_talleres[df_talleres["Estado"] == "ARREGLANDO FALLAS"]
            
            alertas = len(cortes_faltantes) + len(cortes_devoluciones)
        
        # HEADER CON MÉTRICAS
        st.subheader("📊 Resumen General")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f'<div class="metric-card pending"><h4>📋 {len(cortes_sin_asignar)}</h4><p>Cortes sin asignar</p></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card production"><h4>🔄 {en_produccion}</h4><p>En producción</p></div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="metric-card delivered"><h4>✅ {entregados}</h4><p>Entregados</p></div>', unsafe_allow_html=True)
        with col4:
            st.markdown(f'<div class="metric-card alert"><h4>⚠️ {alertas}</h4><p>Con alertas</p></div>', unsafe_allow_html=True)
        
        # SECCIÓN: ASIGNAR CORTES
        st.subheader("📤 Asignar Cortes a Talleres")
        
        if not cortes_sin_asignar.empty:
            st.info(f"📋 **Cortes pendientes de asignar:** {len(cortes_sin_asignar)}")
            
            # Crear DataFrame para edición
            df_editable = cortes_sin_asignar.copy()
            df_editable["Taller"] = ""
            df_editable["Fecha Envío"] = date.today().strftime("%Y-%m-%d")
            df_editable["Asignar"] = False
            
            with st.form("form_asignar_tabla"):
                st.markdown('<div class="editable-table">', unsafe_allow_html=True)
                
                # Mostrar títulos de columnas
                cols = st.columns([1, 2, 1, 2, 2, 1, 1])
                with cols[0]: st.write("**Nro Corte**")
                with cols[1]: st.write("**Artículo**")
                with cols[2]: st.write("**Prendas**")
                with cols[3]: st.write("**Tela**")
                with cols[4]: st.write("**Taller**")
                with cols[5]: st.write("**Fecha Envío**")
                with cols[6]: st.write("**Asignar**")
                
                # Crear widgets para cada fila
                for i, row in df_editable.iterrows():
                    cols = st.columns([1, 2, 1, 2, 2, 1, 1])
                    
                    with cols[0]:
                        st.write(f"{row['Número de corte']}")
                    with cols[1]:
                        st.write(row['Artículo'])
                    with cols[2]:
                        st.write(row['Prendas'])
                    with cols[3]:
                        st.write(row['Tipo de tela'])
                    with cols[4]:
                        # Selectbox simple con talleres existentes
                        taller = st.selectbox(
                            f"Taller_{i}",
                            options=talleres_existentes,
                            index=0,
                            key=f"taller_{i}",
                            label_visibility="collapsed"
                        )
                        df_editable.at[i, "Taller"] = taller
                        
                    with cols[5]:
                        fecha = st.date_input(
                            f"Fecha_{i}",
                            value=pd.to_datetime(row['Fecha Envío']).date(),
                            key=f"fecha_{i}",
                            label_visibility="collapsed"
                        )
                        df_editable.at[i, "Fecha Envío"] = fecha.strftime("%Y-%m-%d")
                    with cols[6]:
                        asignar = st.checkbox("✓", key=f"asignar_{i}", value=row['Asignar'])
                        df_editable.at[i, "Asignar"] = asignar
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Botón verde para asignar
                if st.form_submit_button("🚀 Asignar Cortes Seleccionados", type="primary"):
                    cortes_a_asignar = df_editable[df_editable["Asignar"] == True]
                    
                    if not cortes_a_asignar.empty:
                        # Cargar datos actuales de talleres
                        df_talleres_actual = cargar_hoja("Talleres")
                        
                        if df_talleres_actual.empty:
                            df_talleres_actual = pd.DataFrame(columns=[
                                "ID Corte", "Número de Corte", "Artículo", "Taller", 
                                "Fecha Envío", "Fecha Entrega", "Prendas Recibidas", 
                                "Prendas Falladas", "Estado", "Días Transcurridos"
                            ])
                        
                        success_count = 0
                        for _, corte in cortes_a_asignar.iterrows():
                            if corte["Taller"].strip():
                                # Crear nuevo registro
                                nuevo_registro = {
                                    "ID Corte": str(corte.get("ID", "")),
                                    "Número de Corte": str(corte.get("Número de corte", "")),
                                    "Artículo": str(corte.get('Artículo', '')),
                                    "Taller": str(corte.get("Taller", "")).strip(),
                                    "Fecha Envío": str(corte.get("Fecha Envío", date.today().strftime("%Y-%m-%d"))),
                                    "Fecha Entrega": "",
                                    "Prendas Recibidas": 0,
                                    "Prendas Falladas": 0,
                                    "Estado": "EN PRODUCCIÓN",
                                    "Días Transcurridos": 0
                                }
                                
                                # Agregar al DataFrame
                                df_talleres_actual = pd.concat([df_talleres_actual, pd.DataFrame([nuevo_registro])], ignore_index=True)
                                success_count += 1
                            else:
                                st.warning(f"⚠️ El corte {corte['Número de corte']} no tiene taller asignado")
                        
                        if success_count > 0:
                            # Guardar en Google Sheets
                            if guardar_hoja(df_talleres_actual, "Talleres"):
                                st.success(f"✅ {success_count} cortes asignados correctamente")
                                time.sleep(2)
                                st.rerun()
                    else:
                        st.warning("⚠️ Selecciona al menos un corte para asignar")
        else:
            st.success("🎉 ¡Todos los cortes han sido asignados!")
        
        # ==============================================
        # 📋 SECCIÓN 2: TABLERO KANBAN DE PRODUCCIÓN
        # ==============================================
        st.subheader("📋 Tablero Kanban de Producción")
        
        if not df_talleres.empty:
            # Convertir fechas de manera segura
            try:
                df_talleres["Fecha Envío"] = pd.to_datetime(df_talleres["Fecha Envío"], errors='coerce')
                df_talleres["Días Transcurridos"] = df_talleres["Fecha Envío"].apply(
                    lambda x: (date.today() - x.date()).days if pd.notnull(x) else 0
                )
            except Exception as e:
                df_talleres["Días Transcurridos"] = 0
            
            # Ordenar cortes: los más recientes primero
            df_talleres = df_talleres.sort_values("Fecha Envío", ascending=False)
            
            # Crear columnas Kanban CON SCROLL
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown('<div class="kanban-column">', unsafe_allow_html=True)
                st.markdown("### 🟦 En Producción")
                en_produccion_df = df_talleres[df_talleres["Estado"] == "EN PRODUCCIÓN"]
                
                # Limitar visualmente a 10 cortes, pero permitir scroll
                cortes_mostrar = en_produccion_df.head(10)
                
                for idx, corte in cortes_mostrar.iterrows():
                    # Determinar clase CSS por urgencia
                    card_class = "corte-card"
                    dias = corte.get("Días Transcurridos", 0)
                    if dias > 20:
                        card_class += " urgente"
                    
                    # Obtener información completa
                    articulo = corte.get('Artículo', 'Sin nombre')
                    taller = corte.get('Taller', 'Sin taller')
                    nro_corte = corte.get('Número de Corte', '')
                    prendas_recibidas = corte.get('Prendas Recibidas', 0)
                    total_prendas = 0
                    
                    # Obtener total de prendas del corte original
                    try:
                        id_corte = corte.get('ID Corte', '')
                        corte_original = df_cortes[df_cortes["ID"].astype(str) == str(id_corte)]
                        if not corte_original.empty:
                            total_prendas = int(corte_original.iloc[0].get('Prendas', 0))
                    except:
                        pass
                    
                    # Barra de progreso de días
                    progreso_dias = min(dias / 20, 1.0)
                    
                    st.markdown(f'''
                    <div class="{card_class}">
                        <strong>{articulo}</strong>
                        <small>Corte: {nro_corte} | Taller: {taller}</small>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {progreso_dias*100}%"></div>
                        </div>
                        <small>Días: {dias}/20 | Recibidas: {prendas_recibidas}/{total_prendas}</small>
                    </div>
                    ''', unsafe_allow_html=True)
                
                if len(en_produccion_df) > 10:
                    st.info(f"📜 ... y {len(en_produccion_df) - 10} cortes más (usa scroll)")
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                st.markdown('<div class="kanban-column">', unsafe_allow_html=True)
                st.markdown("### 🟨 Pendientes de Revisión")
                
                # Incluir cortes con faltantes y devoluciones
                pendientes_df = df_talleres[
                    (df_talleres["Estado"] == "ENTREGADO c/FALTANTES") |
                    (df_talleres["Estado"] == "ARREGLANDO FALLAS")
                ]
                
                # Limitar visualmente
                cortes_mostrar_pendientes = pendientes_df.head(10)
                
                for idx, corte in cortes_mostrar_pendientes.iterrows():
                    articulo = corte.get('Artículo', 'Sin nombre')
                    taller = corte.get('Taller', 'Sin taller')
                    nro_corte = corte.get('Número de Corte', '')
                    estado = corte.get('Estado', '')
                    prendas_recibidas = int(corte.get('Prendas Recibidas', 0))
                    prendas_falladas = int(corte.get('Prendas Falladas', 0))
                    total_prendas = 0
                    
                    # Obtener total de prendas
                    try:
                        id_corte = corte.get('ID Corte', '')
                        corte_original = df_cortes[df_cortes["ID"].astype(str) == str(id_corte)]
                        if not corte_original.empty:
                            total_prendas = int(corte_original.iloc[0].get('Prendas', 0))
                    except:
                        pass
                    
                    faltante = total_prendas - prendas_recibidas - prendas_falladas
                    
                    # Determinar tipo de pendiente
                    detalle = ""
                    if estado == "ENTREGADO c/FALTANTES":
                        icono = "⚠️"
                        detalle = f"Recibidas: {prendas_recibidas}/{total_prendas} | Faltan: {faltante}"
                    elif estado == "ARREGLANDO FALLAS":
                        icono = "🔧"
                        detalle = f"Recibidas: {prendas_recibidas}/{total_prendas} | Falladas: {prendas_falladas} | En reparación"
                    
                    st.markdown(f'''
                    <div class="corte-card">
                        <strong>{articulo}</strong>
                        <small>Corte: {nro_corte} | Taller: {taller}</small>
                        <small>{icono} {estado}</small>
                        <small>{detalle}</small>
                    </div>
                    ''', unsafe_allow_html=True)
                
                if len(pendientes_df) > 10:
                    st.info(f"📜 ... y {len(pendientes_df) - 10} cortes más (usa scroll)")
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col3:
                st.markdown('<div class="kanban-column">', unsafe_allow_html=True)
                st.markdown("### 🟩 Completados")
                completados_df = df_talleres[df_talleres["Estado"] == "ENTREGADO"]
                
                # Limitar visualmente
                cortes_mostrar_completados = completados_df.head(10)
                
                for idx, corte in cortes_mostrar_completados.iterrows():
                    articulo = corte.get('Artículo', 'Sin nombre')
                    taller = corte.get('Taller', 'Sin taller')
                    nro_corte = corte.get('Número de Corte', '')
                    fecha_entrega = corte.get('Fecha Entrega', '')
                    prendas_recibidas = int(corte.get('Prendas Recibidas', 0))
                    total_prendas = 0
                    
                    # Obtener total de prendas
                    try:
                        id_corte = corte.get('ID Corte', '')
                        corte_original = df_cortes[df_cortes["ID"].astype(str) == str(id_corte)]
                        if not corte_original.empty:
                            total_prendas = int(corte_original.iloc[0].get('Prendas', 0))
                    except:
                        pass
                    
                    st.markdown(f'''
                    <div class="corte-card completado">
                        <strong>{articulo}</strong>
                        <small>Corte: {nro_corte} | Taller: {taller}</small>
                        <small>✅ 100% completado ({prendas_recibidas}/{total_prendas})</small>
                        <small>Entregado: {fecha_entrega}</small>
                    </div>
                    ''', unsafe_allow_html=True)
                
                if len(completados_df) > 10:
                    st.info(f"📜 ... y {len(completados_df) - 10} cortes más (usa scroll)")
                
                st.markdown('</div>', unsafe_allow_html=True)

# =====================
# BOTÓN DE ACTUALIZACIÓN GLOBAL
# =====================
if st.sidebar.button("🔄 Actualizar todos los datos", key="refresh_all"):
    st.cache_data.clear()
    st.success("✅ Caché limpiado. Los datos se recargarán.")
    st.rerun()

# =====================
# VERIFICACIÓN DE CONEXIÓN
# =====================
if client is None:
    st.error("❌ No se pudo conectar a Google Sheets. Verifica las credenciales y la conexión a internet.")
    st.stop()




































































