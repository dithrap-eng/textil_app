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
# ←←← AGREGAR ESTA FUNCIÓN AQUÍ ←←←
@st.cache_data(ttl=600)  # Cache por 10 minutos
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

    compra_id = len(ws_compras.col_values(1))  # ID simple = nro de fila
    # Guardamos como números puros (sin formato)
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

    # actualizar stock: restar rollos consumidos
    ws_detalle_compras = spreadsheet.worksheet("Detalle_Compras")
    data = ws_detalle_compras.get_all_records()
    df = pd.DataFrame(data)

    for l in lineas:
        idx = df[(df["Tipo de tela"] == tipo_tela) & (df["Color"] == l["color"])].index
        if not idx.empty:
            row = idx[0] + 2  # compensar encabezado
            new_value = int(df.loc[idx[0], "Rollos"]) - l["rollos"]
            if new_value < 0:
                new_value = 0
            ws_detalle_compras.update_cell(row, 4, new_value)  # col 4 = Rollos

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
    ws_compras = spreadsheet.worksheet("Compras")
    data = ws_compras.get_all_records()
    df = pd.DataFrame(data)
    return df

def get_proveedores():
    ws = spreadsheet.worksheet("Proveedores")
    data = ws.col_values(1)[1:]  # saltear encabezado
    return data

def insert_proveedor(nombre):
    ws = spreadsheet.worksheet("Proveedores")
    ws.append_row([nombre])

# Agregar estas funciones en la sección de consultas
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
    ["📥 Compras", "📦 Stock", "✂ Cortes", "🏭 Talleres", "👥 Proveedores"]
)

# -------------------------------
# COMPRAS
# -------------------------------
if menu == "📥 Compras":
    st.header("Registrar compra de tela")

    fecha = st.date_input("Fecha", value=date.today())
    proveedores = get_proveedores()
    proveedor = st.selectbox("Proveedor", proveedores if proveedores else ["---"])
    tipo_tela = st.text_input("Tipo de tela")
    precio_por_metro = st.number_input("Precio por metro (USD)", min_value=0.0, step=0.5)
    total_metros = st.number_input("Total de metros de la compra", min_value=0.0, step=0.5)

    st.subheader("Colores y rollos")
    lineas = []
    num_colores = st.number_input("Cantidad de colores", min_value=1, max_value=10, value=3, step=1)
    for i in range(num_colores):
        col1, col2 = st.columns([2,1])
        with col1:
            color = st.text_input(f"Color {i+1}")
        with col2:
            rollos = st.number_input(f"Rollos {i+1}", min_value=0, step=1, key=f"rollos_{i}")
        if color and rollos > 0:
            lineas.append({"color": color, "rollos": rollos})

    # mostrar totales antes de confirmar
    if lineas and total_metros > 0 and precio_por_metro > 0:
        total_rollos = sum(l["rollos"] for l in lineas)
        total_valor = total_metros * precio_por_metro
        st.info(f"📦 Total rollos cargados: {total_rollos}")
        st.info(f"💲 Total $: USD {total_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    if st.button("💾 Guardar compra"):
        insert_purchase(fecha, proveedor, tipo_tela, precio_por_metro, total_metros, lineas)
        st.success("✅ Compra registrada")

    # -------------------------------
    # Resumen de compras
    # -------------------------------
    st.subheader("Resumen de compras")
    df_resumen = get_compras_resumen()

    if not df_resumen.empty:
        # Convertir directamente (ahora Sheets usa formato internacional)
        df_resumen["Total metros"] = pd.to_numeric(df_resumen["Total metros"], errors="coerce")
        df_resumen["Precio por metro (USD)"] = pd.to_numeric(df_resumen["Precio por metro (USD)"], errors="coerce")
        df_resumen["Rollos totales"] = pd.to_numeric(df_resumen["Rollos totales"], errors="coerce")
        df_resumen["Total USD"] = pd.to_numeric(df_resumen["Total USD"], errors="coerce")
        
        # Calcular precio promedio
        df_resumen["Precio promedio x rollo"] = df_resumen["Total USD"] / df_resumen["Rollos totales"]
        df_resumen["Precio promedio x rollo"] = df_resumen["Precio promedio x rollo"].fillna(0)
        
        # Función para formatear en estilo argentino (solo para visualización)
        def formato_argentino(valor, es_moneda=False):
            if pd.isna(valor) or valor == 0:
                return ""
            formatted = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"USD {formatted}" if es_moneda else formatted
        
        # Preparar datos para mostrar
        df_mostrar = df_resumen.copy()
        df_mostrar["Total metros"] = df_mostrar["Total metros"].apply(formato_argentino)
        df_mostrar["Precio por metro (USD)"] = df_mostrar["Precio por metro (USD)"].apply(lambda x: formato_argentino(x, True))
        df_mostrar["Total USD"] = df_mostrar["Total USD"].apply(lambda x: formato_argentino(x, True))
        df_mostrar["Precio promedio x rollo"] = df_mostrar["Precio promedio x rollo"].apply(lambda x: formato_argentino(x, True))
        df_mostrar["Rollos totales"] = df_mostrar["Rollos totales"].astype(int).astype(str)
        
        st.dataframe(df_mostrar, use_container_width=True)
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

    colores = df_stock[df_stock["Tipo de tela"] == tipo_tela]["Color"].unique() if len(df_stock) else []
    colores_sel = st.multiselect("Colores usados", colores)

    lineas = []
    
    # Contenedor principal para colores con mejor diseño
    with st.container():
        st.subheader("📊 Gestión de Colores y Rollos")
        
        for i, c in enumerate(colores_sel):
            # Crear un recuadro diferenciado para cada color
            with st.expander(f"🎨 **{c}**", expanded=True):
                # Dividir en columnas para mejor organización
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    stock_color = int(df_stock[(df_stock["Tipo de tela"] == tipo_tela) & 
                                              (df_stock["Color"] == c)]["Rollos"].sum())
                    
                    # Mostrar stock con indicador visual
                    if stock_color > 5:
                        st.success(f"**Stock disponible:** {stock_color} rollos")
                    elif stock_color > 2:
                        st.warning(f"**Stock disponible:** {stock_color} rollos")
                    else:
                        st.error(f"**Stock disponible:** {stock_color} rollos")
                
                with col2:
                    rollos_usados = st.number_input(
                        f"Rollos consumidos", 
                        min_value=0, 
                        max_value=stock_color,
                        step=1, 
                        key=f"corte_{c}_{i}",
                        help=f"Máximo disponible: {stock_color} rollos"
                    )
                
                # Separador visual entre colores
                if i < len(colores_sel) - 1:
                    st.markdown("---")
                
                if rollos_usados > 0:
                    lineas.append({"color": c, "rollos": rollos_usados})

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
# TALLERES (VERSIÓN COMPLETA UNIFICADA)
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
    
    # Cargar todos los datos necesarios
    df_cortes = get_cortes_resumen()
    df_historial = cargar_datos("Historial_Entregas")
    
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
        
        # Calcular alertas (más de 20 días)
        alertas = 0
        if not df_talleres.empty and "Fecha Envío" in df_talleres.columns:
            try:
                df_talleres["Fecha Envío"] = pd.to_datetime(df_talleres["Fecha Envío"], errors='coerce')
                df_talleres["Días Transcurridos"] = (date.today() - df_talleres["Fecha Envío"].dt.date).dt.days
                alertas = len(df_talleres[(df_talleres["Días Transcurridos"] > 20) & (df_talleres["Estado"] == "EN PRODUCCIÓN")])
            except:
                alertas = 0
        
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
                        taller = st.text_input(
                            f"Taller_{i}",
                            value=row['Taller'],
                            key=f"taller_{i}",
                            placeholder="Taller",
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
                        success_count = 0
                        for _, corte in cortes_a_asignar.iterrows():
                            if corte["Taller"].strip():
                                nuevo_registro = {
                                    "ID Corte": str(corte.get("ID", "")),
                                    "Nro Corte": str(corte.get("Nro Corte", "")),
                                    "Artículo": str(corte.get('Artículo', '')),
                                    "Taller": str(corte.get("Taller", "")).strip(),
                                    "Fecha Envío": corte.get("Fecha Envío", date.today().strftime("%Y-%m-%d")),
                                    "Fecha Entrega": "",
                                    "Prendas Recibidas": 0,
                                    "Prendas Falladas": 0,
                                    "Estado": "EN PRODUCCIÓN",
                                    "Días Transcurridos": 0
                                }
                                
                                try:
                                    ws_talleres.append_row(list(nuevo_registro.values()))
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
                # Filtrar entregas con faltantes o fallas
                pendientes_df = df_talleres[
                    df_talleres["Estado"].str.contains("ENTREGADO", na=False) & 
                    (df_talleres["Estado"] != "ENTREGADO")
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
                    
                    # Determinar tipo de pendiente
                    if "FALTANTES" in estado:
                        icono = "⚠️"
                        detalle = f"Faltan: {faltante} prendas"
                    elif "FALLAS" in estado:
                        icono = "❌"
                        detalle = f"Falladas: {prendas_falladas}"
                    else:
                        icono = "📦"
                        detalle = f"Recibidas: {prendas_recibidas}/{total_prendas}"
                    
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
        # 📦 SISTEMA DE ENTREGAS (ESTILO MEJORADO)
        # ==============================================
        st.markdown("---")
        st.header("📦 Sistema de Entregas")
        
        # Filtrar cortes que están EN PRODUCCIÓN
        if not df_talleres.empty and "Estado" in df_talleres.columns:
            cortes_produccion = df_talleres[df_talleres["Estado"] == "EN PRODUCCIÓN"]
        else:
            cortes_produccion = pd.DataFrame()
        
        # --- ESTILOS CSS ---
        st.markdown("""
        <style>
        /* Selectbox estilo mejorado */
        div[data-baseweb="select"] > div {
            border: 2px solid #89CFF0 !important;
            background-color: #E6F7FF !important;
            border-radius: 8px !important;
        }
        div[data-baseweb="select"] label {
            color: #0077B6 !important;
            font-weight: bold !important;
            font-size: 16px !important;
        }
        
        /* Estilo compacto similar a la captura */
        .corte-info-compact {
            background-color: #2d2d2d;
            border-radius: 10px;
            padding: 15px;
            margin: 15px 0;
            border: 1px solid #404040;
        }
        .info-row-compact {
            display: flex;
            align-items: center;
            margin: 10px 0;
            padding: 8px 12px;
        }
        .info-icon {
            margin-right: 12px;
            font-size: 18px;
            width: 24px;
            text-align: center;
        }
        .info-label-compact {
            color: #a0a0a0;
            font-weight: bold;
            font-size: 14px;
            min-width: 100px;
        }
        .info-value-compact {
            color: #ffffff;
            font-weight: 500;
            font-size: 14px;
            flex-grow: 1;
        }
        .estado-badge-compact {
            background-color: #4a8cff;
            color: white;
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 10px;
        }
        
        /* Campos del formulario */
        .prendas-input input {
            background-color: #E6F7FF !important;
            font-weight: bold !important;
            border: 2px solid #89CFF0 !important;
            color: #0077B6 !important;
        }
        .faltante-alert {
            background-color: #FFF3CD;
            color: #856404;
            padding: 12px;
            border-radius: 8px;
            border-left: 4px solid #FFC107;
            margin: 15px 0;
            font-weight: bold;
            font-size: 14px;
        }
        </style>
        """, unsafe_allow_html=True)
        
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
                        total_prendas = corte_cortes.iloc[0].get("Prendas", 0)
                else:
                    st.warning("No se pudo obtener el total de prendas desde la solapa Cortes")
            except Exception as e:
                st.warning(f"No se pudo obtener información de la solapa Cortes: {str(e)}")
            
            # Mostrar información del corte con estilo compacto
            st.markdown('<div class="corte-info-compact">', unsafe_allow_html=True)
            
            # Taller
            taller = corte_data.get("Taller", "N/A")
            st.markdown(f"""
            <div class="info-row-compact">
                <span class="info-icon">🏭</span>
                <span class="info-label-compact">Taller:</span>
                <span class="info-value-compact">{taller}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # Total de prendas
            st.markdown(f"""
            <div class="info-row-compact">
                <span class="info-icon">📏</span>
                <span class="info-label-compact">Total Prendas:</span>
                <span class="info-value-compact">{total_prendas}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # Fecha de envío (solo fecha, sin hora)
            fecha_envio = corte_data.get("Fecha Envío", "N/A")
            if isinstance(fecha_envio, str) and " " in fecha_envio:
                fecha_envio = fecha_envio.split(" ")[0]  # Tomar solo la parte de la fecha
            
            st.markdown(f"""
            <div class="info-row-compact">
                <span class="info-icon">📅</span>
                <span class="info-label-compact">Fecha Envío:</span>
                <span class="info-value-compact">{fecha_envio}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # Estado
            st.markdown(f"""
            <div class="info-row-compact">
                <span class="info-icon">📊</span>
                <span class="info-label-compact">Estado:</span>
                <span class="info-value-compact">
                    <span class="estado-badge-compact">EN PRODUCCIÓN</span>
                </span>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # --- REGISTRAR ENTREGA ---
            st.subheader("📤 Registrar Entrega")
            
            # Usar columns para alinear fecha y prendas recibidas
            col1, col2 = st.columns(2)
            
            with col1:
                fecha_entrega = st.date_input("Fecha de Entrega", value=date.today())
            
            with col2:
                st.markdown('<div class="prendas-input">', unsafe_allow_html=True)
                prendas_recibidas = st.number_input("Prendas Recibidas", 
                                                  min_value=0, 
                                                  max_value=total_prendas,
                                                  value=0,
                                                  key="prendas_recibidas")
                st.markdown('</div>', unsafe_allow_html=True)
            
            # Calcular faltante en tiempo real
            faltante = max(0, total_prendas - prendas_recibidas)
            
            # Mostrar faltante solo si hay faltantes
            if faltante > 0:
                st.markdown(f"""
                <div class="faltante-alert">
                    ⚠️ Faltan {faltante} prendas para completar el corte
                </div>
                """, unsafe_allow_html=True)
            
            # Campo para fallas (solo si el corte se completa)
            if prendas_recibidas == total_prendas:
                fallas_detectadas = st.number_input("Prendas Falladas Detectadas", 
                                                   min_value=0, 
                                                   max_value=prendas_recibidas,
                                                   value=0,
                                                   help="Cantidad de prendas con fallas detectadas")
            
            # Botón de registro
            if st.button("📝 REGISTRAR ENTREGA", use_container_width=True, type="primary"):
                # Determinar nuevo estado
                if faltante == 0:
                    nuevo_estado = "ENTREGADO"
                    mensaje = "✅ Entrega completada - Corte marcado como ENTREGADO"
                else:
                    nuevo_estado = "ENTREGADO c/FALTANTES"
                    mensaje = f"⚠️ Entrega parcial - {faltante} faltantes"
                
                # Lógica para guardar en Google Sheets
                try:
                    # 1. Actualizar Talleres
                    # Buscar la fila correspondiente en Talleres
                    talleres_worksheet = client.open(SHEET_NAME).worksheet("Talleres")
                    talleres_data = talleres_worksheet.get_all_records()
                    
                    # Encontrar el índice de la fila a actualizar
                    for i, row in enumerate(talleres_data):
                        if str(row.get("Número de Corte", "")) == str(corte_seleccionado):
                            # Actualizar los valores
                            update_range = f"G{i+2}"  # Columna G = Prendas Recibidas
                            talleres_worksheet.update(update_range, [[prendas_recibidas]])
                            
                            # Actualizar estado si es diferente
                            if row.get("Estado") != nuevo_estado:
                                estado_range = f"I{i+2}"  # Columna I = Estado
                                talleres_worksheet.update(estado_range, [[nuevo_estado]])
                            
                            # Actualizar fecha de entrega
                            fecha_range = f"F{i+2}"  # Columna F = Fecha Entrega
                            talleres_worksheet.update(fecha_range, [[fecha_entrega.strftime("%Y-%m-%d")]])
                            
                            # Actualizar prendas falladas si corresponde
                            if faltante == 0 and fallas_detectadas > 0:
                                fallas_range = f"H{i+2}"  # Columna H = Prendas Falladas
                                talleres_worksheet.update(fallas_range, [[fallas_detectadas]])
                            
                            break
                    
                    # 2. Registrar en Historial_Entrega
                    historial_worksheet = client.open(SHEET_NAME).worksheet("Historial_Entregas")
                    siguiente_fila = len(historial_worksheet.get_all_values()) + 1
                    
                    # Datos para la nueva fila
                    nueva_entrega = [
                        corte_seleccionado,  # Número de Corte
                        corte_data.get("Artículo", ""),  # Artículo
                        taller,  # Taller
                        fecha_entrega.strftime("%Y-%m-%d"),  # Fecha Entrega
                        1,  # Entrega N° (asumimos que es la primera)
                        prendas_recibidas,  # Prendas Recibidas
                        0,  # Fallado p/Oferta (0 por defecto)
                        0,  # Devolver p/Arreglar (0 por defecto)
                        faltante,  # Faltantes
                        nuevo_estado  # Estado
                    ]
                    
                    historial_worksheet.append_row(nueva_entrega)
                    
                    st.success(mensaje)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error al guardar en Google Sheets: {str(e)}")
                    st.write("Detalles del error:", str(e))
        
        # ==============================================
        # 📋 SEGUIMIENTO DE CORTES CON FALTANTES
        # ==============================================
        st.markdown("---")
        st.header("📋 Seguimiento de Cortes con Faltantes")
        
        try:
            # Cargar datos actualizados de Talleres
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
                    
                    # Obtener total de prendas desde la solapa Cortes
                    total_prendas_corte = 0
                    if "Nro Corte" in df_cortes.columns and "Prendas" in df_cortes.columns:
                        corte_cortes = df_cortes[df_cortes["Nro Corte"].astype(str) == str(nro_corte)]
                        if not corte_cortes.empty:
                            total_prendas_corte = corte_cortes.iloc[0].get("Prendas", 0)
                    
                    recibidas = corte.get("Prendas Recibidas", 0)
                    faltantes = max(0, total_prendas_corte - recibidas)
                    
                    datos_seguimiento.append({
                        "N° Corte": nro_corte,
                        "Artículo": articulo,
                        "Taller": taller,
                        "Fecha Entrega": fecha_entrega,
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
                        
                        if st.button("✅ Marcar como ENTREGADO (faltantes completados)", type="primary"):
                            try:
                                # Actualizar estado en Google Sheets
                                talleres_worksheet = client.open(SHEET_NAME).worksheet("Talleres")
                                talleres_data = talleres_worksheet.get_all_records()
                                
                                for i, row in enumerate(talleres_data):
                                    if str(row.get("Número de Corte", "")) == str(corte_id):
                                        estado_range = f"I{i+2}"  # Columna I = Estado
                                        talleres_worksheet.update(estado_range, [["ENTREGADO"]])
                                        break
                                
                                st.success(f"Corte {corte_id} marcado como ENTREGADO")
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
            # Cargar datos actualizados de Talleres
            talleres_worksheet = client.open(SHEET_NAME).worksheet("Talleres")
            df_talleres_actualizado = pd.DataFrame(talleres_worksheet.get_all_records())
            
            # Filtrar cortes entregados que pueden tener devoluciones
            if not df_talleres_actualizado.empty and "Estado" in df_talleres_actualizado.columns:
                cortes_entregados = df_talleres_actualizado[
                    (df_talleres_actualizado["Estado"] == "ENTREGADO") | 
                    (df_talleres_actualizado["Estado"] == "ENTREGADO c/FALTANTES")
                ]
            else:
                cortes_entregados = pd.DataFrame()
        
            if not cortes_entregados.empty:
                # Seleccionar corte para devolución
                opciones_devolucion = []
                for _, corte in cortes_entregados.iterrows():
                    nro_corte = corte.get("Número de Corte", "Desconocido")
                    articulo = corte.get("Artículo", "Sin nombre")
                    opciones_devolucion.append(f"{str(nro_corte)} - {articulo}")
                
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
                    
                    recibidas_dev = corte_dev_data.get("Prendas Recibidas", 0)
                    
                    with st.form(key=f"devolucion_form_{corte_devolucion_id}"):
                        st.write(f"**Corte:** {corte_devolucion_id} - {corte_dev_data.get('Artículo', '')}")
                        st.write(f"**Prendas recibidas:** {recibidas_dev}")
                        
                        col_dev1, col_dev2 = st.columns(2)
                        
                        with col_dev1:
                            fecha_devolucion = st.date_input("Fecha de Devolución", value=date.today())
                        
                        with col_dev2:
                            prendas_devolver = st.number_input("Prendas a Devolver", 
                                                              min_value=1, 
                                                              max_value=recibidas_dev,
                                                              value=1)
                        
                        observaciones = st.text_area("Observaciones/Motivo de la devolución")
                        
                        submitted_dev = st.form_submit_button("📦 REGISTRAR DEVOLUCIÓN", type="primary")
                        
                        if submitted_dev:
                            try:
                                # Registrar en la hoja de Devoluciones
                                devoluciones_worksheet = client.open(SHEET_NAME).worksheet("Devoluciones")
                                siguiente_fila = len(devoluciones_worksheet.get_all_values()) + 1
                                
                                nueva_devolucion = [
                                    corte_devolucion_id,  # Número de Corte
                                    fecha_devolucion.strftime("%Y-%m-%d"),  # Fecha Devolución
                                    prendas_devolver,  # Prendas Devueltas
                                    observaciones,  # Observaciones
                                    "ARREGLANDO FALLAS"  # Estado
                                ]
                                
                                devoluciones_worksheet.append_row(nueva_devolucion)
                                
                                # Actualizar estado en Talleres
                                talleres_worksheet = client.open(SHEET_NAME).worksheet("Talleres")
                                talleres_data = talleres_worksheet.get_all_records()
                                
                                for i, row in enumerate(talleres_data):
                                    if str(row.get("Número de Corte", "")) == str(corte_devolucion_id):
                                        estado_range = f"I{i+2}"  # Columna I = Estado
                                        talleres_worksheet.update(estado_range, [["ARREGLANDO FALLAS"]])
                                        break
                                
                                st.success(f"✅ Devolución registrada. {prendas_devolver} prendas devueltas al taller.")
                                st.info("El corte pasará a estado 'ARREGLANDO FALLAS'")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"❌ Error al guardar la devolución: {str(e)}")
            else:
                st.info("No hay cortes entregados disponibles para devolución")
        
        except Exception as e:
            st.error(f"❌ Error al cargar datos de devoluciones: {str(e)}")








































































