import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import date
import numpy as np 

# =====================
# CONFIGURACIÓN GOOGLE SHEETS (con secrets)
# =====================
SHEET_NAME = "textil_sistema"

@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scope
    )
    client = gspread.authorize(creds)
    return client

client = init_connection()

@st.cache_data(ttl=600)
def cargar_datos(solapa):
    """
    Carga datos de una solapa específica de Google Sheets
    """
    try:
        sheet = client.open(SHEET_NAME).worksheet(solapa)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error al cargar datos de {solapa}: {str(e)}")
        return pd.DataFrame()
        
spreadsheet = client.open(SHEET_NAME)

# =====================
# FUNCIONES DE GUARDADO
# =====================
def insert_purchase(fecha, proveedor, tipo_tela, precio_por_metro, total_metros, lineas):
    ws_compras = spreadsheet.worksheet("Compras")
    ws_detalle = spreadsheet.worksheet("Detalle_Compras")

    total_rollos = sum(int(l["rollos"]) for l in lineas)
    total_valor = float(total_metros) * float(precio_por_metro)
    precio_promedio_rollo = total_valor / total_rollos if total_rollos > 0 else 0

    compra_id = len(ws_compras.col_values(1))
    ws_compras.append_row([
        compra_id, str(fecha), proveedor, tipo_tela,
        total_metros, precio_por_metro, total_rollos, total_valor, precio_promedio_rollo
    ])

    for l in lineas:
        if l["rollos"] > 0:
            ws_detalle.append_row([
                compra_id, tipo_tela, l["color"], l["rollos"]
            ])

def insert_corte(fecha, nro_corte, articulo, tipo_tela, lineas, consumo_total, prendas, consumo_x_prenda):
    ws_cortes = spreadsheet.worksheet("Cortes")
    ws_detalle = spreadsheet.worksheet("Detalle_Cortes")

    corte_id = len(ws_cortes.col_values(1))
    ws_cortes.append_row([
        corte_id, str(fecha), nro_corte, articulo, tipo_tela,
        sum(l["rollos"] for l in lineas), consumo_total, prendas, consumo_x_prenda
    ])

    for l in lineas:
        ws_detalle.append_row([corte_id, l["color"], l["rollos"]])

    ws_detalle_compras = spreadsheet.worksheet("Detalle_Compras")
    data = ws_detalle_compras.get_all_records()
    df = pd.DataFrame(data)

    for l in lineas:
        idx = df[(df["Tipo de tela"] == tipo_tela) & (df["Color"] == l["color"])].index
        if not idx.empty:
            row = idx[0] + 2
            new_value = int(df.loc[idx[0], "Rollos"]) - l["rollos"]
            if new_value < 0:
                new_value = 0
            ws_detalle_compras.update_cell(row, 4, new_value)

# =====================
# CONSULTAS
# =====================
def get_stock_resumen():
    ws_detalle = spreadsheet.worksheet("Detalle_Compras")
    data = ws_detalle.get_all_records()
    df = pd.DataFrame(data)

    if df.empty:
        return df

    df_stock = df.groupby(["Tipo de tela", "Color"])["Rollos"].sum().reset_index()
    return df_stock

def get_compras_resumen():
    try:
        ws_compras = spreadsheet.worksheet("Compras")
        data = ws_compras.get_all_records()
        df = pd.DataFrame(data)
        return df
    except:
        return pd.DataFrame()

def get_detalle_compras():
    """
    Obtiene el detalle de colores por compra
    """
    try:
        ws_detalle = spreadsheet.worksheet("Detalle_Compras")
        data = ws_detalle.get_all_records()
        df = pd.DataFrame(data)
        return df
    except:
        return pd.DataFrame()

def get_proveedores():
    ws = spreadsheet.worksheet("Proveedores")
    data = ws.col_values(1)[1:]
    return data

def update_stock(tipo_tela, color, nuevo_valor):
    ws = spreadsheet.worksheet("Stock")
    data = ws.get_all_records()
    headers = ws.row_values(1)

    col_idx = headers.index("Rollos") + 1

    for idx, row in enumerate(data, start=2):
        if row["Tipo de tela"] == tipo_tela and row["Color"] == color:
            ws.update_cell(idx, col_idx, nuevo_valor)
            break

def insert_proveedor(nombre):
    ws = spreadsheet.worksheet("Proveedores")
    ws.append_row([nombre])

def get_cortes_resumen():
    try:
        ws_cortes = spreadsheet.worksheet("Cortes")
        data = ws_cortes.get_all_records()
        df = pd.DataFrame(data)
        return df
    except:
        return pd.DataFrame()

def get_talleres():
    try:
        ws_talleres = spreadsheet.worksheet("Talleres")
        data = ws_talleres.get_all_records()
        df = pd.DataFrame(data)
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
    
    # --- NUEVA SECCIÓN: TIPO DE TELA CON UNIFICACIÓN ---
    st.subheader("Tipo de Tela")
    
    @st.cache_data
    def get_telas_existentes():
        """
        Obtiene los tipos de tela existentes de las compras anteriores
        """
        try:
            df_compras = get_compras_resumen()
            if not df_compras.empty and "Tipo de tela" in df_compras.columns:
                return sorted(df_compras["Tipo de tela"].dropna().unique().tolist())
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
        help="Selecciona un tipo de tela existente o 'Agregar nuevo' para crear uno"
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
    
    @st.cache_data
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
                help="Selecciona un color existente o 'Agregar nuevo color' para crear uno"
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
        
        from collections import defaultdict
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
                insert_purchase(fecha, proveedor, tipo_tela, precio_por_metro, total_metros, lineas)
                st.success("✅ Compra registrada exitosamente!")
                st.balloons()

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
        df_compras["Precio por metro (USD)"] = pd.to_numeric(df_compras["Precio por metro (USD)"], errors="coerce")
        df_compras["Rollos totales"] = pd.to_numeric(df_compras["Rollos totales"], errors="coerce")
        df_compras["Total USD"] = pd.to_numeric(df_compras["Total USD"], errors="coerce")
        
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
            "ID": "ID Compra",  # AGREGADO: Mostrar ID de compra
            "Fecha": "Fecha",
            "Proveedor": "Proveedor", 
            "Tipo de tela": "Tipo de Tela",
            "Total metros": "Total Metros",
            "Rollos totales": "Total Rollos",
            "Precio por metro (USD)": "Precio x Metro",
            "Total USD": "Total USD",
            "Precio promedio x rollo": "Precio Promedio x Rollo"
        }
        
        for col_original, col_nuevo in mapeo_columnas.items():
            if col_original in df_mostrar.columns:
                columnas_mostrar.append(col_nuevo)
                if col_original in ["Precio por metro (USD)", "Total USD", "Precio promedio x rollo"]:
                    df_mostrar[col_nuevo] = df_mostrar[col_original].apply(lambda x: formato_argentino(x, True))
                elif col_original == "Total metros":
                    df_mostrar[col_nuevo] = df_mostrar[col_original].apply(formato_argentino)
                elif col_original == "Rollos totales":
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
        total_inversion = df_compras["Total USD"].sum()
        total_metros = df_compras["Total metros"].sum()
        total_rollos = df_compras["Rollos totales"].sum()
        
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
# STOCK
# -------------------------------
elif menu == "📦 Stock":
    st.header("Stock disponible (en rollos)")

    df = get_stock_resumen()
    if df.empty:
        st.warning("No hay stock registrado")
    else:
        filtro_tela = st.multiselect("Filtrar por tela", df["Tipo de tela"].unique())
        filtro_color = st.multiselect("Filtrar por color", df["Color"].unique())

        df_filtrado = df.copy()
        if filtro_tela:
            df_filtrado = df_filtrado[df_filtrado["Tipo de tela"].isin(filtro_tela)]
        if filtro_color:
            df_filtrado = df_filtrado[df_filtrado["Color"].isin(filtro_color)]
        
        # ⬇️⬇️⬇️ FILTRAR Y OCULTAR STOCK EN CERO ⬇️⬇️⬇️
        df_filtrado = df_filtrado[df_filtrado["Rollos"] > 0]
        # ⬆️⬆️⬆️ ESTA LÍNEA OCULTA COMPLETAMENTE EL STOCK 0 ⬆️⬆️⬆️

        if not df_filtrado.empty:
            st.dataframe(df_filtrado, use_container_width=True)
            
            total_rollos = df_filtrado["Rollos"].sum()
            
            # Mostrar totales
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("📊 Total de rollos", total_rollos)
            
            with col2:
                if filtro_tela and len(filtro_tela) == 1:
                    tela_seleccionada = filtro_tela[0]
                    df_tela = df_filtrado[df_filtrado["Tipo de tela"] == tela_seleccionada]
                    if not df_tela.empty:
                        # Aquí puedes calcular el precio promedio si tienes esa data
                        # st.metric("💰 Precio promedio x rollo", "USD 598,15")
                        st.metric("💰 Precio promedio x rollo", "USD -")
        else:
            st.info("ℹ️ No hay stock disponible con los filtros aplicados")
        
        # Obtener el resumen de compras para calcular precios promedios
        df_compras = get_compras_resumen()
        
        st.subheader("Totales de la selección")
        st.write(f"📦 Total de rollos: {total_rollos}")
        
        # 1. Mostrar precio promedio por tipo de tela seleccionado
        if not df_compras.empty and "Precio promedio x rollo" in df_compras.columns:
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
            df_compras["Precio promedio x rollo num"] = df_compras["Precio promedio x rollo"].apply(convertir_formato_argentino)
            
            # Calcular precio promedio por tipo de tela si hay filtro
            precios_telas = {}
            if filtro_tela:
                for tela in filtro_tela:
                    precio_promedio_tela = df_compras[
                        df_compras["Tipo de tela"] == tela
                    ]["Precio promedio x rollo num"].mean()
                    
                    if not pd.isna(precio_promedio_tela) and precio_promedio_tela > 0:
                        # CORRECCIÓN: No dividir por 100 aquí
                        precio_corregido = precio_promedio_tela
                        precios_telas[tela] = precio_corregido
                        st.write(f"💲 Precio promedio x rollo ({tela}): {formato_argentino_moneda(precio_corregido)}")
            
            # 2. Calcular valor estimado CORRECTAMENTE
            if precios_telas:
                if len(precios_telas) == 1:
                    precio_promedio_global = list(precios_telas.values())[0]
                else:
                    precio_promedio_global = sum(precios_telas.values()) / len(precios_telas)
                
                # CORRECCIÓN: Calcular directamente sin dividir por 100
                total_valorizado = total_rollos * precio_promedio_global
                st.write(f"💲 Valor estimado (rollos × precio promedio): {formato_argentino_moneda(total_valorizado)}")
                    
# -------------------------------
# CORTES
# -------------------------------
elif menu == "✂ Cortes":
    st.header("Registrar corte de tela")

    fecha = st.date_input("Fecha de corte", value=date.today())
    nro_corte = st.text_input("Número de corte")
    articulo = st.text_input("Artículo")

    df_stock = get_stock_resumen()
    telas = df_stock["Tipo de tela"].unique() if not df_stock.empty else []
    tipo_tela = st.selectbox("Tela usada", telas if len(telas) else ["---"])

    # --- MODIFICACIÓN: Filtrar colores con stock > 0 ---
    if not df_stock.empty and tipo_tela != "---":
        # Filtrar por tipo de tela y stock mayor a 0
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

    lineas = []
    
    # ================================
    # GESTIÓN DE COLORES Y TALLES
    # ================================
    st.subheader("📊 Gestión de Colores y Talles")
    
    talles = [5, 6, 7, 8, 9, 10]
    tabla_data = {}
    lineas = []
    totales_x_color = []
    totales_rollos = []
    
    if colores_sel:
        st.write("Complete las cantidades por color y talle:")
    
        # Encabezado
        cols = st.columns(len(talles) + 4)  # +4 = Color + Total x color + Stock actual + Total rollos
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
                    key=f"{c}_{t}"
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
                max_value=stock_color,  # límite por stock
                step=1,
                key=f"rollos_{c}"
            )
    
            # Stock actualizado dinámicamente
            stock_disp = stock_color - total_rollos
            if stock_disp > 5:
                cols[-2].success(f"{stock_disp}")
            elif stock_disp > 2:
                cols[-2].warning(f"{stock_disp}")
            else:
                cols[-2].error(f"{stock_disp}")
    
            # Guardar info en estructuras
            tabla_data[c] = valores_fila
            lineas.append({"color": c, "rollos": total_rollos})
    
            totales_x_color.append(total_color)
            totales_rollos.append(total_rollos)
    
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
        suma_total_color = sum(totales_x_color)
        suma_total_rollos = sum(totales_rollos)
    
        cols[-3].markdown(
            f"<div style='background-color:#dc3545; color:white; padding:8px; border-radius:8px; text-align:center; font-size:16px; font-weight:bold;'>"
            f"{suma_total_color}</div>",
            unsafe_allow_html=True
        )
        cols[-2].markdown(" ")  # vacío porque stock no se suma
        cols[-1].markdown(
            f"<div style='background-color:#0d6efd; color:white; padding:8px; border-radius:8px; text-align:center; font-size:16px; font-weight:bold;'>"
            f"{suma_total_rollos}</div>",
            unsafe_allow_html=True
        )
    
    else:
        if tipo_tela != "---" and len(colores_con_stock) == 0:
            st.warning("⚠️ No hay colores con stock disponible para la tela seleccionada")
        else:
            st.info("Seleccione colores para habilitar la tabla de talles.")

    # Sección de consumo y prendas
    st.markdown("---")
    st.subheader("📦 Datos de Producción")
    
    col_consumo, col_prendas = st.columns(2)
    
    with col_consumo:
        consumo_total = st.number_input("Consumo total (m)", min_value=0.0, step=0.5, format="%.2f")
    
    with col_prendas:
        prendas = st.number_input("Cantidad de prendas", min_value=1, step=1)
    
    # Mostrar consumo por prenda con mejor diseño
    if prendas > 0 and consumo_total > 0:
        consumo_x_prenda = consumo_total / prendas
        st.metric(
            "🧵 Consumo por prenda", 
            f"{consumo_x_prenda:.2f} m",
            help="Consumo total dividido por cantidad de prendas"
        )
    else:
        st.info("ℹ️ Complete consumo total y cantidad de prendas para calcular el consumo por prenda")

    # Botón de guardar con mejor diseño
    st.markdown("---")
    col_btn, _ = st.columns([1, 3])
    
    with col_btn:
        if st.button("💾 Guardar corte", type="primary", use_container_width=True):
            if not colores_sel:
                st.error("❌ Debe seleccionar al menos un color")
            elif consumo_total <= 0:
                st.error("❌ El consumo total debe ser mayor a 0")
            elif prendas <= 0:
                st.error("❌ La cantidad de prendas debe ser mayor a 0")
            else:
                insert_corte(fecha, nro_corte, articulo, tipo_tela, lineas, consumo_total, prendas, consumo_x_prenda)
                st.success("✅ Corte registrado y stock actualizado correctamente")
                st.balloons()

  # -------------------------------
    # RESUMEN DE CORTES (VERSIÓN CORREGIDA)
    # -------------------------------
    st.subheader("📊 Resumen de cortes registrados")
    
    def get_cortes_resumen():
        try:
            ws_cortes = spreadsheet.worksheet("Cortes")
            data = ws_cortes.get_all_records()
            df = pd.DataFrame(data)
            return df
        except:
            return pd.DataFrame()
    
    df_cortes = get_cortes_resumen()
    
    if not df_cortes.empty:
        
        # Buscar nombres alternativos de columnas
        column_mapping = {
            'consumo_total': ['Consumo total (m)', 'Consumo total', 'Consumo', 'Total metros'],
            'cantidad_prendas': ['Cantidad de prendas', 'Prendas', 'Cantidad prendas', 'Cantidad'],
            'consumo_x_prenda': ['Consumo x prenda (m)', 'Consumo por prenda', 'Metros por prenda']
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
            df_cortes['Consumo x prenda (m)'] = df_cortes[real_columns['consumo_total']] / df_cortes[real_columns['cantidad_prendas']]
            real_columns['consumo_x_prenda'] = 'Consumo x prenda (m)'
        
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
        for col in ["Fecha", "Nro Corte", "Artículo", "Tipo de tela"]:
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
elif menu == "🏭 Proveedores":
    st.header("Administrar proveedores")

    nuevo = st.text_input("Nuevo proveedor")
    if st.button("➕ Agregar proveedor"):
        if nuevo:
            insert_proveedor(nuevo)
            st.success(f"Proveedor '{nuevo}' agregado")
        else:
            st.warning("Ingrese un nombre válido")

    st.subheader("Listado de proveedores")
    proveedores = get_proveedores()
    if proveedores:
        st.table(pd.DataFrame(proveedores, columns=["Proveedor"]))
    else:
        st.info("No hay proveedores registrados aún.")


# -------------------------------
# TALLERES (VERSIÓN COMPLETA UNIFICADA - AJUSTES)
# -------------------------------
elif menu == "🏭 Talleres":
    import time
    
    # Configuración de estilo KANBAN
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
        </style>
    """, unsafe_allow_html=True)
    
    st.header("📋 Tablero de Producción - Talleres")

    @st.cache_data(ttl=600)
    def cargar_datos(solapa):
        """
        Carga datos de una solapa específica de Google Sheets
        """
        try:
            sheet = client.open(SHEET_NAME).worksheet(solapa)
            data = sheet.get_all_records()
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Error al cargar datos de {solapa}: {str(e)}")
            return pd.DataFrame()
    
    # Función para obtener talleres desde Google Sheets
    def get_nombre_talleres():
        try:
            ws_talleres = spreadsheet.worksheet("Nombre_talleres")
            data = ws_talleres.get_all_records()
            if data and "Taller" in data[0]:
                talleres = [row["Taller"] for row in data if row["Taller"].strip()]
                return sorted(list(set(talleres)))  # Eliminar duplicados y ordenar
            else:
                # Si no hay datos o la columna no existe, obtener de la columna A
                talleres = ws_talleres.col_values(1)
                if talleres and talleres[0].lower() == "taller":
                    talleres = talleres[1:]  # Eliminar encabezado
                return sorted(list(set([t for t in talleres if t.strip()])))
        except Exception as e:
            st.error(f"Error al cargar talleres: {str(e)}")
            return []
    
    # Cargar todos los datos necesarios
    df_cortes = get_cortes_resumen()
    df_historial = cargar_datos("Historial_Entregas")
    df_devoluciones = cargar_datos("Devoluciones")
    
    # Obtener lista de talleres
    talleres_existentes = get_nombre_talleres()
    
    if not df_cortes.empty:
        # Crear o obtener worksheet de talleres
        try:
            ws_talleres = spreadsheet.worksheet("Talleres")
        except:
            spreadsheet.add_worksheet(title="Talleres", rows=100, cols=20)
            ws_talleres = spreadsheet.worksheet("Talleres")
            ws_talleres.append_row(["ID Corte", "Nro Corte", "Artículo", "Taller", 
                                  "Fecha Envío", "Fecha Entrega", "Prendas Recibidas", 
                                  "Prendas Falladas", "Estado", "Días Transcurridos"])
        
        # Leer datos existentes de talleres
        try:
            datos_talleres = ws_talleres.get_all_records()
            df_talleres = pd.DataFrame(datos_talleres)
        except:
            df_talleres = pd.DataFrame()
        
        # ==============================================
        # 📊 SECCIÓN 1: RESUMEN GENERAL Y ASIGNACIÓN
        # ==============================================
        
        # Calcular métricas para el header
        cortes_sin_asignar = df_cortes[~df_cortes["ID"].astype(str).isin(df_talleres["ID Corte"].astype(str))] if not df_talleres.empty else df_cortes
        
        en_produccion = len(df_talleres[df_talleres["Estado"] == "EN PRODUCCIÓN"]) if not df_talleres.empty else 0
        entregados = len(df_talleres[df_talleres["Estado"].str.contains("ENTREGADO", na=False)]) if not df_talleres.empty else 0
        
        # CALCULAR ALERTAS MEJORADO: Cortes con faltantes o devoluciones no entregadas
        alertas = 0
        if not df_talleres.empty:
            # Cortes con faltantes
            cortes_faltantes = df_talleres[df_talleres["Estado"] == "ENTREGADO c/FALTANTES"]
            
            # Cortes con devoluciones (ARREGLANDO FALLAS)
            cortes_devoluciones = df_talleres[df_talleres["Estado"] == "ARREGLANDO FALLAS"]
            
            alertas = len(cortes_faltantes) + len(cortes_devoluciones)
        
        # HEADER CON MÉTRICAS (TARJETAS DE COLORES)
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
        
        # SECCIÓN: ASIGNAR CORTES (TABLA EDITABLE)
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
                        st.write(f"{row['Nro Corte']}")
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
                        # CORREGIDO: Guardar como string en formato fecha
                        df_editable.at[i, "Fecha Envío"] = fecha.strftime("%Y-%m-%d")
                    with cols[6]:
                        asignar = st.checkbox("✓", key=f"asignar_{i}", value=row['Asignar'])
                        df_editable.at[i, "Asignar"] = asignar
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Botón verde para asignar
                if st.form_submit_button("🚀 Asignar Cortes Seleccionados", type="primary"):
                    cortes_a_asignar = df_editable[df_editable["Asignar"] == True]
                    
                    if not cortes_a_asignar.empty:
                        success_count = 0
                        for _, corte in cortes_a_asignar.iterrows():
                            if corte["Taller"].strip():
                                # CORREGIDO: Convertir todos los valores a string para evitar error JSON
                                nuevo_registro = [
                                    str(corte.get("ID", "")),  # ID Corte
                                    str(corte.get("Nro Corte", "")),  # Nro Corte
                                    str(corte.get('Artículo', '')),  # Artículo
                                    str(corte.get("Taller", "")).strip(),  # Taller
                                    str(corte.get("Fecha Envío", date.today().strftime("%Y-%m-%d"))),  # Fecha Envío
                                    "",  # Fecha Entrega
                                    "0",  # Prendas Recibidas
                                    "0",  # Prendas Falladas
                                    "EN PRODUCCIÓN",  # Estado
                                    "0"  # Días Transcurridos
                                ]
                                
                                try:
                                    ws_talleres.append_row(nuevo_registro)
                                    success_count += 1
                                except Exception as e:
                                    st.error(f"❌ Error al asignar corte {corte['Nro Corte']}: {str(e)}")
                            else:
                                st.warning(f"⚠️ El corte {corte['Nro Corte']} no tiene taller asignado")
                        
                        if success_count > 0:
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
            
            # Crear columnas Kanban
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown('<div class="kanban-column">', unsafe_allow_html=True)
                st.markdown("### 🟦 En Producción")
                en_produccion_df = df_talleres[df_talleres["Estado"] == "EN PRODUCCIÓN"]
                
                for idx, corte in en_produccion_df.iterrows():
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
                        corte_original = df_cortes[df_cortes["ID"].astype(str) == str(id_corte)].iloc[0]
                        total_prendas = int(corte_original.get('Prendas', 0))
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
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                st.markdown('<div class="kanban-column">', unsafe_allow_html=True)
                st.markdown("### 🟨 Pendientes de Revisión")
                
                # MEJORADO: Incluir cortes con faltantes y devoluciones
                pendientes_df = df_talleres[
                    (df_talleres["Estado"] == "ENTREGADO c/FALTANTES") |
                    (df_talleres["Estado"] == "ARREGLANDO FALLAS")
                ]
                
                for idx, corte in pendientes_df.iterrows():
                    articulo = corte.get('Artículo', 'Sin nombre')
                    taller = corte.get('Taller', 'Sin taller')
                    nro_corte = corte.get('Número de Corte', '')
                    estado = corte.get('Estado', '')
                    prendas_recibidas = corte.get('Prendas Recibidas', 0)
                    prendas_falladas = corte.get('Prendas Falladas', 0)
                    total_prendas = 0
                    
                    # Obtener total de prendas
                    try:
                        id_corte = corte.get('ID Corte', '')
                        corte_original = df_cortes[df_cortes["ID"].astype(str) == str(id_corte)].iloc[0]
                        total_prendas = int(corte_original.get('Prendas', 0))
                    except:
                        pass
                    
                    faltante = total_prendas - prendas_recibidas
                    
                    # Determinar tipo de pendiente y obtener información adicional
                    detalle = ""
                    if estado == "ENTREGADO c/FALTANTES":
                        icono = "⚠️"
                        detalle = f"Recibidas: {prendas_recibidas}/{total_prendas} | Faltan: {faltante}"
                        # Buscar información de devoluciones si existe
                        if not df_devoluciones.empty:
                            devolucion = df_devoluciones[df_devoluciones["Número de Corte"] == nro_corte]
                            if not devolucion.empty:
                                prendas_devueltas = devolucion.iloc[0].get("Prendas Devueltas", 0)
                                if prendas_devueltas > 0:  # SOLO mostrar si hay devoluciones
                                    detalle += f" | Devueltas: {prendas_devueltas}"
                    elif estado == "ARREGLANDO FALLAS":
                        icono = "🔧"
                        detalle = f"Recibidas: {prendas_recibidas}/{total_prendas}"
                        if prendas_falladas > 0:  # SOLO mostrar falladas si son > 0
                            detalle += f" | Falladas: {prendas_falladas}"
                        detalle += " | En reparación"
                        # Buscar información de devoluciones
                        if not df_devoluciones.empty:
                            devolucion = df_devoluciones[df_devoluciones["Número de Corte"] == nro_corte]
                            if not devolucion.empty:
                                prendas_devueltas = devolucion.iloc[0].get("Prendas Devueltas", 0)
                                observaciones = devolucion.iloc[0].get("Observaciones", "")
                                if prendas_devueltas > 0:  # SOLO mostrar si hay devoluciones
                                    detalle += f" | Devueltas: {prendas_devueltas}"
                                if observaciones:
                                    detalle += f" | Obs: {observaciones[:30]}..."
                    
                    st.markdown(f'''
                    <div class="corte-card">
                        <strong>{articulo}</strong>
                        <small>Corte: {nro_corte} | Taller: {taller}</small>
                        <small>{icono} {estado}</small>
                        <small>{detalle}</small>
                    </div>
                    ''', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col3:
                st.markdown('<div class="kanban-column">', unsafe_allow_html=True)
                st.markdown("### 🟩 Completados")
                completados_df = df_talleres[df_talleres["Estado"] == "ENTREGADO"]
                
                for idx, corte in completados_df.iterrows():
                    articulo = corte.get('Artículo', 'Sin nombre')
                    taller = corte.get('Taller', 'Sin taller')
                    nro_corte = corte.get('Número de Corte', '')
                    fecha_entrega = corte.get('Fecha Entrega', '')
                    prendas_recibidas = corte.get('Prendas Recibidas', 0)
                    total_prendas = 0
                    
                    # Obtener total de prendas
                    try:
                        id_corte = corte.get('ID Corte', '')
                        corte_original = df_cortes[df_cortes["ID"].astype(str) == str(id_corte)].iloc[0]
                        total_prendas = int(corte_original.get('Prendas', 0))
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
                st.markdown('</div>', unsafe_allow_html=True)
        
        # ==============================================
        # 📦 SISTEMA DE ENTREGAS (MEJORADO)
        # ==============================================
        st.markdown("---")
        st.header("📦 Sistema de Entregas")
        
        # Filtrar cortes que están EN PRODUCCIÓN
        if not df_talleres.empty and "Estado" in df_talleres.columns:
            cortes_produccion = df_talleres[df_talleres["Estado"] == "EN PRODUCCIÓN"]
        else:
            cortes_produccion = pd.DataFrame()
        
        # --- SELECCIÓN DE CORTE ---
        if not cortes_produccion.empty:
            # Crear lista de cortes para el dropdown
            opciones_cortes = []
            for _, corte in cortes_produccion.iterrows():
                nro_corte = corte.get("Número de Corte", "Desconocido")
                articulo = corte.get("Artículo", "Sin nombre")
                opciones_cortes.append(f"{str(nro_corte)} - {articulo}")
            
            corte_seleccionado_str = st.selectbox(
                "Seleccionar Corte para Registrar Entrega",
                options=opciones_cortes,
                index=0
            )
            
            # Extraer solo el número de corte
            corte_seleccionado = corte_seleccionado_str.split(" - ")[0]
        else:
            st.info("No hay cortes en producción para gestionar")
            corte_seleccionado = None
        
        # --- INFORMACIÓN DEL CORTE SELECCIONADO ---
        if corte_seleccionado:
            # Obtener datos del corte seleccionado de Talleres
            try:
                corte_data = None
                if "Número de Corte" in df_talleres.columns:
                    corte_filtrado = df_talleres[df_talleres["Número de Corte"].astype(str) == str(corte_seleccionado)]
                    if not corte_filtrado.empty:
                        corte_data = corte_filtrado.iloc[0]
                    else:
                        st.error(f"❌ No se encontró el corte {corte_seleccionado} en Talleres")
                        st.stop()
            except Exception as e:
                st.error(f"❌ Error al buscar el corte: {str(e)}")
                st.stop()
            
            # Obtener información del total de prendas desde la solapa Cortes
            try:
                total_prendas = 0
                if "Nro Corte" in df_cortes.columns and "Prendas" in df_cortes.columns:
                    corte_cortes = df_cortes[df_cortes["Nro Corte"].astype(str) == str(corte_seleccionado)]
                    if not corte_cortes.empty:
                        total_prendas = int(corte_cortes.iloc[0].get("Prendas", 0))
                else:
                    st.warning("No se pudo obtener el total de prendas desde la solapa Cortes")
            except Exception as e:
                st.warning(f"No se pudo obtener información de la solapa Cortes: {str(e)}")
            
            # Mostrar información del corte
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.write(f"**Artículo:** {corte_data.get('Artículo', 'N/A')}")
                st.write(f"**Taller:** {corte_data.get('Taller', 'N/A')}")
            with col_info2:
                st.write(f"**Total Prendas:** {total_prendas}")
                st.write(f"**Fecha Envío:** {corte_data.get('Fecha Envío', 'N/A')}")
            
            # --- REGISTRAR ENTREGA MEJORADO ---
            st.subheader("📤 Registrar Entrega")
            
            with st.form(key="form_entrega"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    fecha_entrega = st.date_input("Fecha de Entrega", value=date.today())
                
                with col2:
                    prendas_recibidas = st.number_input("Prendas Recibidas", 
                                                      min_value=0, 
                                                      max_value=total_prendas,
                                                      value=0,
                                                      key="prendas_recibidas_input")
                
                with col3:
                    # Campo para prendas falladas
                    prendas_falladas = st.number_input("Prendas Falladas", 
                                                     min_value=0, 
                                                     max_value=total_prendas,
                                                     value=0,
                                                     key="prendas_falladas_input",
                                                     help="Cantidad de prendas con fallas detectadas")
                
                # Campo para observaciones (más pequeño)
                observaciones = st.text_input("Observaciones", 
                                            placeholder="Observaciones sobre la entrega...",
                                            max_chars=100)
                
                # CALCULAR FALTANTE EN TIEMPO REAL - CORREGIDO
                faltante = max(0, total_prendas - prendas_recibidas - prendas_falladas)
                
                # Mostrar resumen en tiempo real
                st.markdown("---")
                st.subheader("📊 Resumen de la Entrega")
                
                col_res1, col_res2, col_res3, col_res4 = st.columns(4)
                with col_res1:
                    st.metric("📏 Total Corte", total_prendas)
                with col_res2:
                    st.metric("✅ Recibidas", prendas_recibidas)
                with col_res3:
                    st.metric("❌ Falladas", prendas_falladas)
                with col_res4:
                    st.metric("⚠️ Faltantes", faltante, delta=f"-{faltante}" if faltante > 0 else None)
                
                # Determinar estado automáticamente
                if faltante == 0 and prendas_falladas == 0:
                    estado_final = "✅ ENTREGADO"
                    color_estado = "green"
                elif faltante > 0:
                    estado_final = f"⚠️ ENTREGADO c/FALTANTES ({faltante} faltantes)"
                    color_estado = "orange"
                elif prendas_falladas > 0:
                    estado_final = f"🔧 ENTREGADO c/FALLAS ({prendas_falladas} falladas)"
                    color_estado = "red"
                
                st.markdown(f"<h4 style='color: {color_estado};'>Estado final: {estado_final}</h4>", unsafe_allow_html=True)
                
                submitted = st.form_submit_button("📝 REGISTRAR ENTREGA", type="primary")
                
                if submitted:
                    # Determinar nuevo estado para guardar
                    if faltante == 0 and prendas_falladas == 0:
                        nuevo_estado = "ENTREGADO"
                        mensaje = "✅ Entrega completada - Corte marcado como ENTREGADO"
                    elif faltante > 0:
                        nuevo_estado = "ENTREGADO c/FALTANTES"
                        mensaje = f"⚠️ Entrega parcial - {faltante} faltantes"
                    elif prendas_falladas > 0:
                        nuevo_estado = "ENTREGADO c/FALLAS"
                        mensaje = f"⚠️ Entrega con fallas - {prendas_falladas} prendas falladas"
                    
                    # Lógica para guardar en Google Sheets
                    try:
                        # 1. Actualizar Talleres
                        talleres_worksheet = client.open(SHEET_NAME).worksheet("Talleres")
                        talleres_data = talleres_worksheet.get_all_records()
                        
                        # Encontrar el índice de la fila a actualizar
                        for i, row in enumerate(talleres_data):
                            if str(row.get("Número de Corte", "")) == str(corte_seleccionado):
                                # CORREGIDO: Convertir a string para evitar error JSON
                                update_data = [
                                    ["G", str(prendas_recibidas)],  # Prendas Recibidas
                                    ["H", str(prendas_falladas)],   # Prendas Falladas
                                    ["I", nuevo_estado],            # Estado
                                    ["F", fecha_entrega.strftime("%Y-%m-%d")]  # Fecha Entrega
                                ]
                                
                                for col_letter, value in update_data:
                                    range_cell = f"{col_letter}{i+2}"
                                    talleres_worksheet.update(range_cell, [[value]])
                                break
                        
                        # 2. Registrar en Historial_Entrega
                        historial_worksheet = client.open(SHEET_NAME).worksheet("Historial_Entregas")
                        
                        # CORREGIDO: Convertir todos los valores a string
                        nueva_entrega = [
                            str(corte_seleccionado),  # Número de Corte
                            str(corte_data.get("Artículo", "")),  # Artículo
                            str(corte_data.get("Taller", "")),  # Taller
                            str(fecha_entrega.strftime("%Y-%m-%d")),  # Fecha Entrega
                            "1",  # Entrega N° 
                            str(prendas_recibidas),  # Prendas Recibidas
                            str(prendas_falladas),  # Prendas Falladas
                            str(faltante),  # Faltantes
                            str(observaciones),  # Observaciones
                            str(nuevo_estado)  # Estado
                        ]
                        
                        historial_worksheet.append_row(nueva_entrega)
                        
                        st.success(mensaje)
                        time.sleep(2)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error al guardar en Google Sheets: {str(e)}")
        
        # ==============================================
        # 📋 SEGUIMIENTO DE CORTES CON FALTANTES
        # ==============================================
        st.markdown("---")
        st.header("📋 Seguimiento de Cortes con Faltantes")
        
        try:
            # Cargar datos actualizados
            talleres_worksheet = client.open(SHEET_NAME).worksheet("Talleres")
            df_talleres_actualizado = pd.DataFrame(talleres_worksheet.get_all_records())
            
            # Filtrar cortes con faltantes
            if not df_talleres_actualizado.empty and "Estado" in df_talleres_actualizado.columns:
                cortes_faltantes = df_talleres_actualizado[df_talleres_actualizado["Estado"] == "ENTREGADO c/FALTANTES"]
            else:
                cortes_faltantes = pd.DataFrame()
        
            if not cortes_faltantes.empty:
                # Crear tabla de seguimiento
                datos_seguimiento = []
                for _, corte in cortes_faltantes.iterrows():
                    nro_corte = corte.get("Número de Corte", "")
                    articulo = corte.get("Artículo", "")
                    taller = corte.get("Taller", "")
                    fecha_entrega = corte.get("Fecha Entrega", "")
                    
                    # Obtener total de prendas
                    total_prendas_corte = 0
                    if "Nro Corte" in df_cortes.columns and "Prendas" in df_cortes.columns:
                        corte_cortes = df_cortes[df_cortes["Nro Corte"].astype(str) == str(nro_corte)]
                        if not corte_cortes.empty:
                            total_prendas_corte = int(corte_cortes.iloc[0].get("Prendas", 0))
                    
                    recibidas = int(corte.get("Prendas Recibidas", 0))
                    falladas = int(corte.get("Prendas Falladas", 0))
                    faltantes = max(0, total_prendas_corte - recibidas - falladas)
                    
                    datos_seguimiento.append({
                        "N° Corte": nro_corte,
                        "Artículo": articulo,
                        "Taller": taller,
                        "Fecha Entrega": fecha_entrega,
                        "Recibidas": recibidas,
                        "Falladas": falladas,
                        "Faltantes": faltantes
                    })
                
                df_seguimiento = pd.DataFrame(datos_seguimiento)
                
                if not df_seguimiento.empty:
                    st.dataframe(df_seguimiento, use_container_width=True)
                    
                    # Seleccionar corte para completar faltantes
                    cortes_options = [f"{row['N° Corte']} - {row['Artículo']} ({row['Faltantes']} faltantes)" 
                                     for _, row in df_seguimiento.iterrows()]
                    
                    corte_completar = st.selectbox("Seleccionar corte para completar faltantes", options=cortes_options)
                    
                    if corte_completar:
                        corte_id = corte_completar.split(" - ")[0]
                        
                        col_fecha, col_btn = st.columns([2, 1])
                        with col_fecha:
                            fecha_entrega_faltantes = st.date_input("Fecha de entrega de faltantes", value=date.today())
                        
                        with col_btn:
                            if st.button("✅ Marcar faltantes como ENTREGADOS", type="primary"):
                                try:
                                    # Actualizar estado en Google Sheets
                                    talleres_worksheet = client.open(SHEET_NAME).worksheet("Talleres")
                                    talleres_data = talleres_worksheet.get_all_records()
                                    
                                    for i, row in enumerate(talleres_data):
                                        if str(row.get("Número de Corte", "")) == str(corte_id):
                                            # Actualizar a ENTREGADO
                                            estado_range = f"I{i+2}"
                                            talleres_worksheet.update(estado_range, [["ENTREGADO"]])
                                            
                                            # Registrar en historial
                                            historial_worksheet = client.open(SHEET_NAME).worksheet("Historial_Entregas")
                                            historial_data = [
                                                str(corte_id),
                                                str(row.get("Artículo", "")),
                                                str(row.get("Taller", "")),
                                                str(fecha_entrega_faltantes.strftime("%Y-%m-%d")),
                                                "2",  # Entrega N° 2 (faltantes)
                                                str(row.get("Faltantes", 0)),  # Prendas recibidas (los faltantes)
                                                "0",  # Falladas
                                                "0",  # Faltantes (ya no hay)
                                                "Entrega de faltantes completada",
                                                "ENTREGADO"
                                            ]
                                            historial_worksheet.append_row(historial_data)
                                            break
                                    
                                    st.success(f"Corte {corte_id} marcado como ENTREGADO - Faltantes completados")
                                    time.sleep(2)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error al actualizar Google Sheets: {str(e)}")
                else:
                    st.info("No hay cortes con faltantes pendientes")
            else:
                st.info("No hay cortes con faltantes pendientes")
        
        except Exception as e:
            st.error(f"❌ Error al cargar datos de seguimiento: {str(e)}")
        
        # ==============================================
        # 🔄 SISTEMA DE DEVOLUCIONES
        # ==============================================
        st.markdown("---")
        st.header("🔄 Sistema de Devoluciones")
        
        try:
            # Cargar datos actualizados
            talleres_worksheet = client.open(SHEET_NAME).worksheet("Talleres")
            df_talleres_actualizado = pd.DataFrame(talleres_worksheet.get_all_records())
            
            # Filtrar cortes entregados que pueden tener devoluciones
            if not df_talleres_actualizado.empty and "Estado" in df_talleres_actualizado.columns:
                cortes_entregados = df_talleres_actualizado[
                    (df_talleres_actualizado["Estado"] == "ENTREGADO") | 
                    (df_talleres_actualizado["Estado"] == "ENTREGADO c/FALTANTES") |
                    (df_talleres_actualizado["Estado"] == "ENTREGADO c/FALLAS")
                ]
            else:
                cortes_entregados = pd.DataFrame()
        
            if not cortes_entregados.empty:
                # Seleccionar corte para devolución
                opciones_devolucion = []
                for _, corte in cortes_entregados.iterrows():
                    nro_corte = corte.get("Número de Corte", "Desconocido")
                    articulo = corte.get("Artículo", "Sin nombre")
                    taller = corte.get("Taller", "Sin taller")
                    opciones_devolucion.append(f"{str(nro_corte)} - {articulo} - {taller}")
                
                corte_devolucion_str = st.selectbox(
                    "Seleccionar Corte para Devolución",
                    options=opciones_devolucion
                )
                
                if corte_devolucion_str:
                    corte_devolucion_id = corte_devolucion_str.split(" - ")[0]
                    
                    # Obtener datos del corte seleccionado
                    corte_dev_data = df_talleres_actualizado[
                        df_talleres_actualizado["Número de Corte"].astype(str) == str(corte_devolucion_id)
                    ].iloc[0]
                    
                    recibidas_dev = int(corte_dev_data.get("Prendas Recibidas", 0))
                    falladas_dev = int(corte_dev_data.get("Prendas Falladas", 0))
                    
                    with st.form(key=f"devolucion_form_{corte_devolucion_id}"):
                        st.write(f"**Corte:** {corte_devolucion_id} - {corte_dev_data.get('Artículo', '')}")
                        st.write(f"**Taller:** {corte_dev_data.get('Taller', 'N/A')}")
                        st.write(f"**Prendas recibidas:** {recibidas_dev}")
                        st.write(f"**Prendas falladas:** {falladas_dev}")
                        
                        col_dev1, col_dev2 = st.columns(2)
                        
                        with col_dev1:
                            fecha_devolucion = st.date_input("Fecha de Devolución", value=date.today())
                        
                        with col_dev2:
                            prendas_devolver = st.number_input("Prendas a Devolver", 
                                                              min_value=1, 
                                                              max_value=recibidas_dev,
                                                              value=1)
                        
                        observaciones = st.text_input("Observaciones/Motivo de la devolución",
                                                    placeholder="Motivo de la devolución...",
                                                    max_chars=100)
                        
                        submitted_dev = st.form_submit_button("📦 REGISTRAR DEVOLUCIÓN", type="primary")
                        
                        if submitted_dev:
                            try:
                                # Registrar en la hoja de Devoluciones
                                devoluciones_worksheet = client.open(SHEET_NAME).worksheet("Devoluciones")
                                
                                # CORREGIDO: Convertir a string
                                nueva_devolucion = [
                                    str(corte_devolucion_id),  # Número de Corte
                                    str(corte_dev_data.get("Taller", "")),  # Taller
                                    str(fecha_devolucion.strftime("%Y-%m-%d")),  # Fecha Devolución
                                    str(prendas_devolver),  # Prendas Devueltas
                                    str(observaciones),  # Observaciones
                                    "PENDIENTE"  # Estado inicial
                                ]
                                
                                devoluciones_worksheet.append_row(nueva_devolucion)
                                
                                # Actualizar estado en Talleres
                                talleres_worksheet = client.open(SHEET_NAME).worksheet("Talleres")
                                talleres_data = talleres_worksheet.get_all_records()
                                
                                for i, row in enumerate(talleres_data):
                                    if str(row.get("Número de Corte", "")) == str(corte_devolucion_id):
                                        estado_range = f"I{i+2}"
                                        talleres_worksheet.update(estado_range, [["ARREGLANDO FALLAS"]])
                                        break
                                
                                st.success(f"✅ Devolución registrada. {prendas_devolver} prendas devueltas al taller.")
                                st.info("El corte pasará a estado 'ARREGLANDO FALLAS'")
                                time.sleep(2)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"❌ Error al guardar la devolución: {str(e)}")
            else:
                st.info("No hay cortes entregados disponibles para devolución")
        
        except Exception as e:
            st.error(f"❌ Error al cargar datos de devoluciones: {str(e)}")
        
        # ==============================================
        # 🔧 SEGUIMIENTO DE DEVOLUCIONES (CORREGIDO)
        # ==============================================
        st.markdown("---")
        st.header("🔧 Seguimiento de Devoluciones")
        
        try:
            # CORREGIDO: Mostrar todos los cortes en estado "ARREGLANDO FALLAS"
            cortes_arreglando_fallas = df_talleres[df_talleres["Estado"] == "ARREGLANDO FALLAS"]
            
            if not cortes_arreglando_fallas.empty:
                st.subheader("Cortes en Reparación (ARREGLANDO FALLAS)")
                
                for _, corte in cortes_arreglando_fallas.iterrows():
                    nro_corte = corte.get("Número de Corte", "")
                    articulo = corte.get("Artículo", "")
                    taller = corte.get("Taller", "")
                    prendas_recibidas = int(corte.get("Prendas Recibidas", 0))
                    prendas_falladas = int(corte.get("Prendas Falladas", 0))
                    
                    # Buscar información de devolución
                    devolucion_info = ""
                    if not df_devoluciones.empty:
                        devolucion = df_devoluciones[df_devoluciones["Número de Corte"] == nro_corte]
                        if not devolucion.empty:
                            dev_data = devolucion.iloc[0]
                            prendas_devueltas = dev_data.get("Prendas Devueltas", 0)
                            observaciones = dev_data.get("Observaciones", "")
                            fecha_devolucion = dev_data.get("Fecha Devolución", "")
                            devolucion_info = f" | Devueltas: {prendas_devueltas} | Fecha: {fecha_devolucion}"
                            if observaciones:
                                devolucion_info += f" | Obs: {observaciones}"
                    
                    with st.expander(f"🔧 Corte {nro_corte} - {articulo} - Taller: {taller}"):
                        st.write(f"**Prendas recibidas:** {prendas_recibidas}")
                        st.write(f"**Prendas falladas:** {prendas_falladas}")
                        if devolucion_info:
                            st.write(f"**Información devolución:** {devolucion_info}")
                        
                        with st.form(key=f"reparacion_form_{nro_corte}"):
                            col_rep1, col_rep2 = st.columns(2)
                            
                            with col_rep1:
                                fecha_reparacion = st.date_input("Fecha de reparación", value=date.today(), key=f"fecha_rep_{nro_corte}")
                            
                            with col_rep2:
                                prendas_reparadas = st.number_input("Prendas reparadas", 
                                                                  min_value=0, 
                                                                  max_value=prendas_falladas,
                                                                  value=prendas_falladas,
                                                                  key=f"reparadas_{nro_corte}")
                            
                            observaciones_reparacion = st.text_input("Observaciones de la reparación",
                                                                   placeholder="Estado de la reparación...",
                                                                   key=f"obs_rep_{nro_corte}",
                                                                   max_chars=100)
                            
                            if st.form_submit_button("✅ Marcar como Reparado", type="primary", key=f"btn_rep_{nro_corte}"):
                                try:
                                    # Actualizar estado en Talleres
                                    talleres_worksheet = client.open(SHEET_NAME).worksheet("Talleres")
                                    talleres_data = talleres_worksheet.get_all_records()
                                    
                                    for i, row in enumerate(talleres_data):
                                        if str(row.get("Número de Corte", "")) == str(nro_corte):
                                            # Actualizar estado a ENTREGADO
                                            estado_range = f"I{i+2}"
                                            talleres_worksheet.update(estado_range, [["ENTREGADO"]])
                                            
                                            # Actualizar prendas falladas si se repararon
                                            if prendas_reparadas < prendas_falladas:
                                                fallas_range = f"H{i+2}"
                                                nuevas_falladas = prendas_falladas - prendas_reparadas
                                                talleres_worksheet.update(fallas_range, [[str(nuevas_falladas)]])
                                            
                                            break
                                    
                                    # Registrar en historial
                                    historial_worksheet = client.open(SHEET_NAME).worksheet("Historial_Entregas")
                                    historial_data = [
                                        str(nro_corte),
                                        str(articulo),
                                        str(taller),
                                        str(fecha_reparacion.strftime("%Y-%m-%d")),
                                        "3",  # Entrega N° 3 (reparación)
                                        str(prendas_reparadas),  # Prendas recibidas (reparadas)
                                        "0",  # Falladas
                                        "0",  # Faltantes
                                        f"Reparación completada: {observaciones_reparacion}",
                                        "REPARADO"
                                    ]
                                    historial_worksheet.append_row(historial_data)
                                    
                                    # Actualizar estado en Devoluciones si existe
                                    if not df_devoluciones.empty:
                                        try:
                                            devoluciones_worksheet = client.open(SHEET_NAME).worksheet("Devoluciones")
                                            devoluciones_data = devoluciones_worksheet.get_all_records()
                                            
                                            for i, dev_row in enumerate(devoluciones_data):
                                                if (str(dev_row.get("Número de Corte", "")) == str(nro_corte) and 
                                                    dev_row.get("Estado") == "PENDIENTE"):
                                                    
                                                    estado_dev_range = f"F{i+2}"  # Columna F = Estado
                                                    devoluciones_worksheet.update(estado_dev_range, [["REPARADO"]])
                                                    break
                                        except:
                                            pass  # Si no existe la hoja Devoluciones, continuar
                                    
                                    st.success(f"✅ Reparación registrada para corte {nro_corte}")
                                    time.sleep(2)
                                    st.rerun()
                                    
                                except Exception as e:
                                    st.error(f"❌ Error al registrar reparación: {str(e)}")
            else:
                st.info("No hay cortes en estado 'ARREGLANDO FALLAS'")
        
        except Exception as e:
            st.error(f"❌ Error al cargar datos de seguimiento de devoluciones: {str(e)}")


















































































