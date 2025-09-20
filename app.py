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
        # 📦 SECCIÓN 3: SISTEMA DE ENTREGAS PARCIALES
        # ==============================================
        st.markdown("---")
        st.subheader("📦 Sistema de Entregas Parciales")
        
        # Filtrar cortes que NO estén completos (no "ENTREGADO")
        if not df_talleres.empty and "Estado" in df_talleres.columns:
            cortes_pendientes = df_talleres[df_talleres["Estado"] != "ENTREGADO"]
        else:
            cortes_pendientes = pd.DataFrame()
        
        # --- SELECCIÓN SIMPLE CON DESPLEGABLE ---
        if not cortes_pendientes.empty:
            # Crear lista de cortes para el dropdown
            opciones_cortes = []
            for _, corte in cortes_pendientes.iterrows():
                # Obtener el número de corte correctamente
                nro_corte = corte.get("Número de Corte", "Desconocido")
                articulo = corte.get("Artículo", "Sin nombre")
                # Convertir a string para evitar problemas
                opciones_cortes.append(f"{str(nro_corte)} - {articulo}")
            
            # Aplicar estilo al selectbox
            st.markdown("""
            <style>
            .corte-select label {
                color: #007bff !important;
                font-weight: bold !important;
                font-size: 1.1rem !important;
            }
            .stSelectbox > div > div {
                border: 2px solid #007bff !important;
                border-radius: 5px !important;
            }
            </style>
            """, unsafe_allow_html=True)
            
            st.markdown('<div class="corte-select">', unsafe_allow_html=True)
            corte_seleccionado_str = st.selectbox(
                "Seleccionar Corte para Gestionar Entregas",
                options=opciones_cortes,
                index=0
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Extraer solo el número de corte del string seleccionado
            corte_seleccionado = corte_seleccionado_str.split(" - ")[0]
        else:
            st.info("No hay cortes pendientes para gestionar")
            corte_seleccionado = None
        
        # --- GESTIÓN DE ENTREGA PARCIAL ---
        if corte_seleccionado:
            # Obtener datos del corte seleccionado de Talleres
            try:
                # Buscar en Talleres
                corte_data = None
                if "Número de Corte" in df_talleres.columns:
                    # Filtrar el dataframe para encontrar el corte
                    corte_filtrado = df_talleres[df_talleres["Número de Corte"].astype(str) == str(corte_seleccionado)]
                    if not corte_filtrado.empty:
                        corte_data = corte_filtrado.iloc[0]
                    else:
                        st.error(f"❌ No se encontró el corte {corte_seleccionado} en Talleres")
                        st.stop()
                else:
                    st.error("❌ No se encuentra la columna 'Número de Corte' en Talleres")
                    st.write("Columnas disponibles en Talleres:", df_talleres.columns.tolist())
                    st.stop()
            except Exception as e:
                st.error(f"❌ Error al buscar el corte: {str(e)}")
                st.stop()
            
            # Obtener información del corte original de la solapa Cortes
            try:
                corte_info = None
                if "Nro Corte" in df_cortes.columns:
                    # Filtrar el dataframe para encontrar el corte
                    corte_filtrado_cortes = df_cortes[df_cortes["Nro Corte"].astype(str) == str(corte_seleccionado)]
                    if not corte_filtrado_cortes.empty:
                        corte_info = corte_filtrado_cortes.iloc[0]
            except Exception as e:
                st.warning(f"⚠️ No se pudo obtener información adicional del corte: {str(e)}")
                corte_info = None
                
            # Aplicar CSS personalizado para esta sección
            st.markdown("""
            <style>
            .compact-metric .stMetric {
                margin-bottom: 0.5rem;
            }
            .compact-metric .stMetric label {
                font-size: 0.9rem !important;
                color: #a0a0a0 !important;
            }
            .compact-metric .stMetric value {
                font-size: 0.9rem !important;
            }
            .estado-badge {
                display: inline-block;
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 0.85rem;
                font-weight: 500;
            }
            .estado-entregado {
                background-color: #28a745;
                color: white;
            }
            .estado-entregado-fallas {
                background-color: #ffc107;
                color: #333;
            }
            .estado-pendiente {
                background-color: #ffc107;
                color: #333;
            }
            .estado-produccion {
                background-color: #4a8cff;
                color: white;
            }
            .prendas-recibidas input {
                background-color: #e6f7ff !important;
                font-weight: bold !important;
                border: 2px solid #007bff !important;
            }
            .btn-registrar {
                background-color: #28a745 !important;
                color: white !important;
                font-weight: bold !important;
                border: none !important;
                padding: 10px 20px !important;
                border-radius: 5px !important;
            }
            .btn-registrar:hover {
                background-color: #218838 !important;
            }
            .resumen-entrega {
                background-color: #f8f9fa;
                border-radius: 5px;
                padding: 10px;
                margin: 10px 0;
                border-left: 4px solid #007bff;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Mostrar información del corte
            st.subheader(f"📋 Información del Corte: {corte_seleccionado}")
            
            col_info1, col_info2, col_info3 = st.columns(3)
            
            with col_info1:
                st.markdown('<div class="compact-metric">', unsafe_allow_html=True)
                st.metric("📋 Artículo", corte_data.get("Artículo", "N/A") if corte_data is not None else "N/A")
                st.metric("🏭 Taller", corte_data.get("Taller", "N/A") if corte_data is not None else "N/A")
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col_info2:
                # Usar Prendas de Cortes si está disponible, sino de Talleres
                if corte_info is not None:
                    total_prendas_val = corte_info.get("Prendas", 0)
                elif corte_data is not None:
                    total_prendas_val = corte_data.get("Prendas", 0)
                else:
                    total_prendas_val = 0
                    
                st.markdown('<div class="compact-metric">', unsafe_allow_html=True)
                st.metric("📏 Total Prendas", total_prendas_val)
                
                recibidas_actual = corte_data.get("Prendas Recibidas", 0) if corte_data is not None else 0
                st.metric("✅ Recibidas", recibidas_actual)
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col_info3:
                st.markdown('<div class="compact-metric">', unsafe_allow_html=True)
                
                # Determinar estado actual
                estado_actual = corte_data.get("Estado", "") if corte_data is not None else ""
                falladas_actual = corte_data.get("Prendas Falladas", 0) if corte_data is not None else 0
                
                if recibidas_actual >= total_prendas_val:
                    if falladas_actual > 0:
                        estado_class = "estado-entregado-fallas"
                        emoji = "🟡"
                        estado = "ENTREGADO c/FALLAS"
                    else:
                        estado_class = "estado-entregado"
                        emoji = "🟢"
                        estado = "ENTREGADO"
                elif recibidas_actual > 0:
                    estado_class = "estado-produccion"
                    emoji = "🔵"
                    estado = "EN PRODUCCIÓN"
                else:
                    estado_class = "estado-pendiente"
                    emoji = "🟡"
                    estado = estado_actual if estado_actual else "PENDIENTE"
                
                st.markdown(f"""
                <div style="margin-bottom: 0.5rem;">
                    <div style="font-size: 0.9rem; color: #a0a0a0; margin-bottom: 0.2rem;">📊 Estado</div>
                    <span class="estado-badge {estado_class}">{emoji} {estado}</span>
                </div>
                """, unsafe_allow_html=True)
                
                st.metric("❌ Falladas", falladas_actual)
                st.markdown('</div>', unsafe_allow_html=True)
            
            # --- REGISTRAR NUEVA ENTREGA ---
            st.markdown("---")
            st.subheader("📤 Registrar Nueva Entrega")
            
            with st.form(key=f"nueva_entrega_form_{corte_seleccionado}"):
                col_ent1, col_ent2 = st.columns(2)
                
                with col_ent1:
                    # Número de entrega primero
                    nro_entrega = 1  # Por defecto, podrías calcularlo basado en el historial
                    st.info(f"**Entrega N°:** {nro_entrega}")
                    fecha_entrega = st.date_input("Fecha de Entrega", value=date.today())
                
                with col_ent2:
                    st.markdown('<div class="prendas-recibidas">', unsafe_allow_html=True)
                    prendas_recibidas = st.number_input("Prendas Recibidas ✅", min_value=0, value=0, 
                                                      key="prendas_recibidas_input")
                    st.markdown('</div>', unsafe_allow_html=True)
                
                col_ent3, col_ent4 = st.columns(2)
                
                with col_ent3:
                    falladas_oferta = st.number_input("Fallado p/Oferta ❌", min_value=0, value=0,
                                                   key="falladas_oferta_input")
                
                with col_ent4:
                    devolver_arreglar = st.number_input("Devolver p/Arreglar 🔄", min_value=0, value=0,
                                                      key="devolver_arreglar_input")
                
                # --- RESUMEN EN TIEMPO REAL ---
                # Calcular valores en tiempo real
                total_entrega_actual = prendas_recibidas + falladas_oferta + devolver_arreglar
                nuevas_recibidas = recibidas_actual + prendas_recibidas
                faltantes = max(0, total_prendas_val - (recibidas_actual + total_entrega_actual))
                
                # Mostrar resumen compacto
                st.markdown(f"""
                <div class="resumen-entrega">
                    <h4>🧮 Resumen de la Entrega</h4>
                    <p><strong>Total de esta entrega:</strong> {total_entrega_actual} prendas</p>
                    <p><strong>Nuevo total recibido:</strong> {nuevas_recibidas} / {total_prendas_val}</p>
                    <p><strong>Faltantes después de esta entrega:</strong> {faltantes}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # Botón de registro destacado
                submitted = st.form_submit_button("📝 REGISTRAR ENTREGA", 
                                                 use_container_width=True,
                                                 type="primary")
                
                if submitted:
                    st.success("✅ Entrega registrada exitosamente")
                    # Aquí iría la lógica para guardar en Google Sheets
                    # (necesitarás implementar la conexión con tu API de Google Sheets)
            
            # --- HISTORIAL DE ENTREGAS ---
            st.markdown("---")
            st.subheader("📋 Historial de Entregas")
            
            # Intenta cargar el historial para este corte
            try:
                historial_corte = pd.DataFrame()
                if not df_historial.empty and "Número de Corte" in df_historial.columns:
                    historial_corte = df_historial[df_historial["Número de Corte"].astype(str) == str(corte_seleccionado)]
                
                if not historial_corte.empty:
                    columnas_mostrar = ["Fecha Entrega", "Entrega N°", "Prendas Recibidas", 
                                      "Fallado p/Oferta", "Devolver p/Arreglar", "Faltantes", "Estado"]
                    
                    # Filtrar columnas existentes
                    columnas_existentes = [col for col in columnas_mostrar if col in historial_corte.columns]
                    
                    st.dataframe(
                        historial_corte[columnas_existentes].sort_values("Fecha Entrega", ascending=False),
                        use_container_width=True,
                        height=300
                    )
                else:
                    st.info("No hay entregas registradas para este corte")
            except Exception as e:
                st.error(f"Error al cargar el historial: {str(e)}")






































































