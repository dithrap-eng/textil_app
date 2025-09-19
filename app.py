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

        st.dataframe(df_filtrado, use_container_width=True)

        total_rollos = df_filtrado["Rollos"].sum()
        
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
    for c in colores_sel:
        stock_color = int(df_stock[(df_stock["Tipo de tela"] == tipo_tela) & (df_stock["Color"] == c)]["Rollos"].sum())
        st.write(f"Stock disponible de {c}: {stock_color} rollos")
        rollos_usados = st.number_input(f"Rollos consumidos de {c}", min_value=0, step=1, key=f"corte_{c}")
        if rollos_usados > 0:
            lineas.append({"color": c, "rollos": rollos_usados})

    consumo_total = st.number_input("Consumo total (m)", min_value=0.0, step=0.5)
    prendas = st.number_input("Cantidad de prendas", min_value=1, step=1)
    consumo_x_prenda = consumo_total / prendas if prendas > 0 else 0

    st.metric("Consumo por prenda (m)", round(consumo_x_prenda, 2))

    if st.button("💾 Guardar corte"):
        insert_corte(fecha, nro_corte, articulo, tipo_tela, lineas, consumo_total, prendas, consumo_x_prenda)
        st.success("✅ Corte registrado y stock actualizado")

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
        # Mostrar las columnas disponibles para debugging
        st.write(f"Columnas disponibles: {list(df_cortes.columns)}")
        
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
            st.write(f"**Consumo promedio:** {consumo_promedio:,.2f} m por prenda")
            
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
# TALLERES (VERSIÓN COMPLETA KANBAN)
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
    
    st.header("📋 Tablero de Producción - Sistema Kanban")
    
    # Obtener datos
    df_cortes = get_cortes_resumen()
    
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
        
        # Leer datos existentes
        try:
            datos_talleres = ws_talleres.get_all_records()
            df_talleres = pd.DataFrame(datos_talleres)
        except:
            df_talleres = pd.DataFrame()
        
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
        
        # SECCIÓN 1: ASIGNAR CORTES (TABLA EDITABLE)
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
        
      # SECCIÓN 2: TABLERO KANBAN (VERSIÓN CORREGIDA)
        st.subheader("📋 Tablero Kanban de Producción")
        
        if not df_talleres.empty:
            # CORRECCIÓN: Manejo robusto de fechas
            try:
                # Convertir fechas de manera segura
                df_talleres["Fecha Envío"] = pd.to_datetime(df_talleres["Fecha Envío"], errors='coerce')
                
                # Calcular días transcurridos con manejo de valores nulos
                df_talleres["Días Transcurridos"] = df_talleres["Fecha Envío"].apply(
                    lambda x: (date.today() - x.date()).days if pd.notnull(x) else 0
                )
            except Exception as e:
                st.error(f"Error al procesar fechas: {str(e)}")
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
                    
                    # Asegurar que los valores existan
                    articulo = corte.get('Artículo', 'Sin nombre')
                    taller = corte.get('Taller', 'Sin taller')
                    nro_corte = corte.get('Nro Corte', '')
                    prendas_recibidas = corte.get('Prendas Recibidas', 0)
                    
                    st.markdown(f'''
                    <div class="{card_class}">
                        <strong>{articulo}</strong><br>
                        <small>Taller: {taller}</small><br>
                        <small>Días: {dias}</small><br>
                        <small>Recibidas: {prendas_recibidas}</small>
                        <small>Corte: {nro_corte}</small>
                    </div>
                    ''', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                st.markdown('<div class="kanban-column">', unsafe_allow_html=True)
                st.markdown("### 🟨 Pendientes de Revisión")
                # CORRECCIÓN: Mejor filtro para estados de entregado
                pendientes_df = df_talleres[
                    df_talleres["Estado"].str.contains("ENTREGADO", na=False) & 
                    (df_talleres["Estado"] != "ENTREGADO")
                ]
                
                for idx, corte in pendientes_df.iterrows():
                    articulo = corte.get('Artículo', 'Sin nombre')
                    taller = corte.get('Taller', 'Sin taller')
                    estado = corte.get('Estado', '')
                    prendas_falladas = corte.get('Prendas Falladas', 0)
                    
                    st.markdown(f'''
                    <div class="corte-card">
                        <strong>{articulo}</strong><br>
                        <small>Taller: {taller}</small><br>
                        <small>Estado: {estado}</small><br>
                        <small>Falladas: {prendas_falladas}</small>
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
                    fecha_entrega = corte.get('Fecha Entrega', '')
                    
                    st.markdown(f'''
                    <div class="corte-card completado">
                        <strong>{articulo}</strong><br>
                        <small>Taller: {taller}</small><br>
                        <small>Entregado: {fecha_entrega}</small><br>
                        <small>✅ 100% completado</small>
                    </div>
                    ''', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        
        # SECCIÓN 3: DETALLE Y ACTUALIZACIÓN (CON ÍNDICES CORRECTOS)
        st.subheader("🔄 Detalle y Actualización de Cortes")
        
        if not df_talleres.empty:
            # Usar los nombres exactos de las columnas
            columna_nro_corte = "Número de Corte"
            
            if columna_nro_corte in df_talleres.columns:
                # Selector de corte para detalle
                cortes_disponibles = df_talleres[columna_nro_corte].dropna().unique().tolist()
                
                if cortes_disponibles:
                    corte_seleccionado = st.selectbox("Seleccionar corte para detalle", cortes_disponibles)
                    
                    if corte_seleccionado:
                        corte_info = df_talleres[df_talleres[columna_nro_corte] == corte_seleccionado].iloc[0]
                        
                        # Obtener información del corte original
                        try:
                            columna_id = "ID Corte"
                            if columna_id in df_talleres.columns:
                                id_corte = str(corte_info.get(columna_id, ""))
                                corte_original = df_cortes[df_cortes["ID"].astype(str) == id_corte].iloc[0]
                                total_prendas = int(corte_original.get('Prendas', 0))
                            else:
                                total_prendas = int(corte_info.get('Prendas Recibidas', 0))  # Valor por defecto
                        except:
                            total_prendas = 0
                        
                        # Formatear fecha de envío
                        fecha_envio = corte_info.get('Fecha Envío', '')
                        fecha_envio_str = str(fecha_envio)
                        
                        col_info1, col_info2 = st.columns(2)
                        
                        with col_info1:
                            st.info(f"**Artículo:** {corte_info.get('Artículo', '')}")
                            st.info(f"**Taller:** {corte_info.get('Taller', '')}")
                            st.info(f"**Enviado:** {fecha_envio_str}")
                        
                        with col_info2:
                            st.info(f"**Prendas totales:** {total_prendas}")
                            st.info(f"**Recibidas:** {corte_info.get('Prendas Recibidas', 0)}")
                            st.info(f"**Estado:** {corte_info.get('Estado', '')}")
                        
                        # Formulario de actualización
                        with st.form(f"form_update_detalle_{corte_seleccionado}"):
                            col_up1, col_up2 = st.columns(2)
                            
                            with col_up1:
                                nuevas_recibidas = st.number_input(
                                    "Prendas recibidas",
                                    min_value=0,
                                    max_value=total_prendas,
                                    value=int(corte_info.get('Prendas Recibidas', 0)),
                                    key=f"rec_{corte_seleccionado}"
                                )
                                
                                nuevas_falladas = st.number_input(
                                    "Prendas falladas",
                                    min_value=0,
                                    value=int(corte_info.get('Prendas Falladas', 0)),
                                    help="Cantidad de prendas que vinieron con fallas",
                                    key=f"fall_{corte_seleccionado}"
                                )
                            
                            with col_up2:
                                # Determinar estado automáticamente
                                faltante_nuevo = total_prendas - nuevas_recibidas
                                
                                if nuevas_recibidas == 0:
                                    estado_auto = "EN PRODUCCIÓN"
                                elif faltante_nuevo > 0 and nuevas_falladas == 0:
                                    estado_auto = "ENTREGADO c/FALTANTES"
                                elif nuevas_falladas > 0 and faltante_nuevo == 0:
                                    estado_auto = "ENTREGADO c/FALLAS"
                                elif nuevas_falladas > 0 and faltante_nuevo > 0:
                                    estado_auto = "ENTREGADO c/FALTAS Y FALLAS"
                                else:
                                    estado_auto = "ENTREGADO"
                                
                                st.write(f"**Estado automático:** {estado_auto}")
                                
                                # Usar fecha existente o hoy por defecto
                                fecha_entrega_existente = corte_info.get('Fecha Entrega', '')
                                fecha_default = date.today()
                                if fecha_entrega_existente and str(fecha_entrega_existente) != '0':
                                    try:
                                        fecha_default = pd.to_datetime(fecha_entrega_existente).date()
                                    except:
                                        pass
                                
                                fecha_entrega = st.date_input(
                                    "Fecha de entrega",
                                    value=fecha_default,
                                    key=f"fecha_ent_{corte_seleccionado}"
                                )
                            
                            if st.form_submit_button("💾 Actualizar Producción"):
                                if nuevas_falladas > nuevas_recibidas:
                                    st.error("❌ Las prendas falladas no pueden ser más que las recibidas")
                                else:
                                    try:
                                        # Encontrar y actualizar la fila
                                        all_data = ws_talleres.get_all_values()
                                        row_index = None
                                        
                                        # Buscar la fila por número de corte (columna B)
                                        for i, row in enumerate(all_data[1:], start=2):
                                            if len(row) > 1 and str(row[1]) == str(corte_seleccionado):  # Columna B (índice 1)
                                                row_index = i
                                                break
                                        
                                        if row_index:
                                            # CORRECCIÓN: ÍNDICES EXACTOS BASADOS EN TU GOOGLE SHEETS
                                            # A: ID Corte (1) - B: Número de Corte (2) - C: Artículo (3) - D: Taller (4)
                                            # E: Fecha Envío (5) - F: Fecha Entrega (6) - G: Prendas Recibidas (7)
                                            # H: Prendas Falladas (8) - I: Estado (9) - J: Días Transcurridos (10)
                                            
                                            ws_talleres.update_cell(row_index, 7, nuevas_recibidas)   # Columna G - Prendas Recibidas
                                            ws_talleres.update_cell(row_index, 8, nuevas_falladas)    # Columna H - Prendas Falladas
                                            ws_talleres.update_cell(row_index, 9, estado_auto)        # Columna I - Estado
                                            ws_talleres.update_cell(row_index, 6, fecha_entrega.strftime("%Y-%m-%d"))  # Columna F - Fecha Entrega
                                            
                                            st.success("✅ Producción actualizada correctamente")
                                            time.sleep(2)
                                            st.rerun()
                                        else:
                                            st.error("❌ No se encontró el registro en la planilla")
                                    
                                    except Exception as e:
                                        st.error(f"❌ Error al actualizar: {str(e)}")
                else:
                    st.info("No hay cortes disponibles para mostrar")
            else:
                st.error("No se encontró la columna 'Número de Corte'")
                st.write("Columnas disponibles:", df_talleres.columns.tolist())





































