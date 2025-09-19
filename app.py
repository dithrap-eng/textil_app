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
# TALLERES (VERSIÓN MEJORADA)
# -------------------------------
elif menu == "🏭 Talleres":
    # Configuración de estilo
    st.markdown("""
        <style>
        .metric-card {
            padding: 15px;
            border-radius: 10px;
            border-left: 4px solid;
            margin-bottom: 10px;
        }
        .pending { border-left-color: #FFA726; background-color: #FFF3E0; }
        .production { border-left-color: #42A5F5; background-color: #E3F2FD; }
        .delivered { border-left-color: #66BB6A; background-color: #E8F5E9; }
        .alert { border-left-color: #EF5350; background-color: #FFEBEE; }
        .progress-bar {
            height: 20px;
            background-color: #e0e0e0;
            border-radius: 10px;
            margin: 10px 0;
        }
        .progress-fill {
            height: 100%;
            border-radius: 10px;
            background: linear-gradient(90deg, #42A5F5, #64B5F6);
        }
        .editable-table {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #e9ecef;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.header("📋 Gestión de Talleres")
    
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
        
        # HEADER CON MÉTRICAS
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
        st.subheader("📤 Asignar corte a taller")
        
        if not cortes_sin_asignar.empty:
            st.info(f"📋 **Cortes pendientes de asignar:** {len(cortes_sin_asignar)}")
            
            # Crear DataFrame para edición
            df_editable = cortes_sin_asignar.copy()
            df_editable["Taller"] = ""
            df_editable["Fecha Envío"] = date.today().strftime("%Y-%m-%d")
            df_editable["Asignar"] = False
            
            with st.form("form_asignar_tabla"):
                st.markdown('<div class="editable-table">', unsafe_allow_html=True)
                
                # Mostrar tabla editable
                columnas_mostrar = ["Nro Corte", "Artículo", "Prendas", "Tipo de tela", "Taller", "Fecha Envío", "Asignar"]
                columnas_mostrar = [col for col in columnas_mostrar if col in df_editable.columns]
                
                # Crear widgets para cada fila
                for i, row in df_editable.iterrows():
                    col1, col2, col3, col4, col5, col6 = st.columns([1, 2, 1, 2, 2, 1])
                    
                    with col1:
                        st.write(f"**{row['Nro Corte']}**")
                    with col2:
                        st.write(row['Artículo'])
                    with col3:
                        st.write(row['Prendas'])
                    with col4:
                        st.write(row['Tipo de tela'])
                    with col5:
                        taller = st.text_input(f"Taller {i}", value=row['Taller'], key=f"taller_{i}", placeholder="Nombre del taller")
                        df_editable.at[i, "Taller"] = taller
                    with col6:
                        fecha = st.date_input(f"Fecha {i}", 
                                            value=pd.to_datetime(row['Fecha Envío']).date(), 
                                            key=f"fecha_{i}")
                        df_editable.at[i, "Fecha Envío"] = fecha.strftime("%Y-%m-%d")
                        asignar = st.checkbox("Asignar", key=f"asignar_{i}")
                        df_editable.at[i, "Asignar"] = asignar
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                if st.form_submit_button("🚀 Asignar Cortes Seleccionados"):
                    cortes_a_asignar = df_editable[df_editable["Asignar"] == True]
                    
                    if not cortes_a_asignar.empty:
                        for _, corte in cortes_a_asignar.iterrows():
                            nuevo_registro = {
                                "ID Corte": str(corte.get("ID", "")),
                                "Nro Corte": str(corte.get("Nro Corte", "")),
                                "Artículo": str(corte.get('Artículo', '')),
                                "Taller": str(corte.get("Taller", "")),
                                "Fecha Envío": corte.get("Fecha Envío", date.today().strftime("%Y-%m-%d")),
                                "Fecha Entrega": "",
                                "Prendas Recibidas": 0,
                                "Prendas Falladas": 0,
                                "Estado": "EN PRODUCCIÓN",
                                "Días Transcurridos": 0
                            }
                            
                            try:
                                ws_talleres.append_row(list(nuevo_registro.values()))
                                st.success(f"✅ Corte {corte['Nro Corte']} asignado a {corte['Taller']}")
                            except Exception as e:
                                st.error(f"❌ Error al asignar corte {corte['Nro Corte']}: {str(e)}")
                        
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.warning("⚠️ Selecciona al menos un corte para asignar")
        else:
            st.success("🎉 ¡Todos los cortes han sido asignados!")
        
        # SECCIÓN 2: ESTADO DE PRODUCCIÓN (MEJORADO)
        st.subheader("🔄 Estado de producción")
        
        if not df_talleres.empty:
            # Filtrar solo cortes en producción
            df_produccion = df_talleres[df_talleres["Estado"] == "EN PRODUCCIÓN"]
            
            if not df_produccion.empty:
                st.write(f"**{len(df_produccion)} cortes en producción:**")
                
                for idx, taller_row in df_produccion.iterrows():
                    # Obtener información del corte original
                    try:
                        corte_original = df_cortes[df_cortes["ID"].astype(str) == str(taller_row.get("ID Corte"))].iloc[0]
                        total_prendas = int(corte_original.get('Prendas', 0))
                    except:
                        total_prendas = 0
                    
                    # Calcular días transcurridos
                    dias_transcurridos = 0
                    fecha_envio_str = ""
                    if taller_row.get("Fecha Envío"):
                        try:
                            fecha_envio = pd.to_datetime(taller_row.get("Fecha Envío"))
                            dias_transcurridos = (date.today() - fecha_envio.date()).days
                            fecha_envio_str = fecha_envio.strftime("%Y-%m-%d")  # Sin hora
                        except:
                            dias_transcurridos = 0
                    
                    # Barra de progreso
                    progreso = min(dias_transcurridos / 20, 1.0)
                    
                    with st.expander(f"🧵 {taller_row.get('Artículo', '')} - {taller_row.get('Taller', '')} ({dias_transcurridos} días)", expanded=True):
                        # Barra de progreso visual
                        st.markdown(f"""
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: {progreso*100}%"></div>
                            </div>
                            <div style="text-align: center; margin: -25px 0 20px 0;">
                                <strong>{dias_transcurridos}/20 días</strong>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            prendas_recibidas = int(taller_row.get('Prendas Recibidas', 0))
                            prendas_falladas = int(taller_row.get('Prendas Falladas', 0))
                            faltante = max(0, total_prendas - prendas_recibidas)
                            
                            st.write(f"**📦 Prendas recibidas:** {prendas_recibidas}/{total_prendas}")
                            st.write(f"**❌ Prendas falladas:** {prendas_falladas}")
                            st.write(f"**⚠️ Faltante:** {faltante}")
                            
                            if prendas_recibidas > 0:
                                porcentaje_falla = (prendas_falladas / prendas_recibidas) * 100
                                st.write(f"**📊 % de falla:** {porcentaje_falla:.1f}%")
                        
                        with col2:
                            st.write(f"**📅 Enviado:** {fecha_envio_str}")
                            st.write(f"**🎯 Entrega estimada:** {taller_row.get('Fecha Entrega', 'Pendiente')}")
                        
                        # Formulario de actualización
                        with st.form(f"form_update_{taller_row.get('ID Corte')}"):
                            col_up1, col_up2 = st.columns(2)
                            
                            with col_up1:
                                nuevas_recibidas = st.number_input(
                                    "Prendas recibidas",
                                    min_value=0,
                                    max_value=total_prendas,
                                    value=prendas_recibidas,
                                    key=f"rec_{idx}"
                                )
                                
                                nuevas_falladas = st.number_input(
                                    "Prendas falladas",
                                    min_value=0,
                                    max_value=nuevas_recibidas,  # Máximo las recibidas
                                    value=prendas_falladas,
                                    key=f"fall_{idx}"
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
                                
                                fecha_entrega = st.date_input(
                                    "Fecha de entrega",
                                    value=date.today(),
                                    key=f"fecha_ent_{idx}"
                                )
                            
                            if st.form_submit_button("💾 Actualizar Producción"):
                                # Actualizar registro en Google Sheets
                                try:
                                    # Encontrar la fila correcta
                                    all_data = ws_talleres.get_all_values()
                                    row_index = None
                                    
                                    for i, row in enumerate(all_data[1:], start=2):  # Saltar header
                                        if str(row[0]) == str(taller_row.get("ID Corte")):
                                            row_index = i
                                            break
                                    
                                    if row_index:
                                        # Actualizar valores
                                        ws_talleres.update_cell(row_index, 7, nuevas_recibidas)  # Prendas Recibidas
                                        ws_talleres.update_cell(row_index, 8, nuevas_falladas)   # Prendas Falladas
                                        ws_talleres.update_cell(row_index, 9, estado_auto)       # Estado
                                        ws_talleres.update_cell(row_index, 6, fecha_entrega.strftime("%Y-%m-%d"))  # Fecha Entrega
                                        
                                        st.success("✅ Producción actualizada correctamente")
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("❌ No se encontró el registro para actualizar")
                                
                                except Exception as e:
                                    st.error(f"❌ Error al actualizar: {str(e)}")
            else:
                st.info("📭 No hay cortes en producción actualmente")
        
        # SECCIÓN 3: DASHBOARD ANALÍTICO (se mantiene igual)
        # ... (el código del dashboard se mantiene como en la versión anterior)

    else:
        st.info("📭 No hay cortes registrados para gestionar talleres")
































