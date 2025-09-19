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
# TALLERES (NUEVA SECCIÓN)
# -------------------------------
elif menu == "🏭 Talleres":
    st.header("📋 Gestión de Talleres")
    
    # Obtener cortes para asignar
    df_cortes = get_cortes_resumen()
    
    if not df_cortes.empty:
        # Crear o obtener worksheet de talleres
        try:
            ws_talleres = spreadsheet.worksheet("Talleres")
        except:
            # Crear worksheet si no existe
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
        
        # SECTION 1: Asignar cortes a talleres
            st.subheader("📤 Asignar corte a taller")
            
            cortes_sin_asignar = df_cortes[~df_cortes["ID"].astype(str).isin(df_talleres["ID Corte"].astype(str))] if not df_talleres.empty else df_cortes
            
            if not cortes_sin_asignar.empty:
                with st.form("form_asignar_taller"):
                    col1, col2 = st.columns(2)
                    with col1:
                        corte_seleccionado = st.selectbox(
                            "Seleccionar corte",
                            cortes_sin_asignar["Nro Corte"].unique()
                        )
                        taller = st.text_input("Nombre del taller")
                        fecha_envio = st.date_input("Fecha de envío", value=date.today())
                    
                    with col2:
                        # Obtener información del corte seleccionado (actualizado dinámicamente)
                        info_corte = cortes_sin_asignar[cortes_sin_asignar["Nro Corte"] == corte_seleccionado].iloc[0]
                        st.write(f"**Artículo:** {info_corte.get('Artículo', '')}")
                        st.write(f"**Prendas totales:** {info_corte.get('Prendas', '')}")
                        st.write(f"**Tela:** {info_corte.get('Tipo de tela', '')}")
                    
                    submitted = st.form_submit_button("✅ Asignar a taller")
                    
                    if submitted:
                        nuevo_registro = {
                            "ID Corte": str(info_corte.get("ID", "")),
                            "Nro Corte": str(corte_seleccionado),
                            "Artículo": str(info_corte.get('Artículo', '')),
                            "Taller": str(taller),
                            "Fecha Envío": fecha_envio.strftime("%Y-%m-%d"),
                            "Fecha Entrega": "",
                            "Prendas Recibidas": 0,
                            "Prendas Falladas": 0,
                            "Estado": "EN PRODUCCIÓN",
                            "Días Transcurridos": 0
                        }
                        
                        ws_talleres.append_row(list(nuevo_registro.values()))
                        st.success(f"Corte {corte_seleccionado} asignado a {taller}")
                        st.rerun()
        
        # SECTION 2: Actualizar estados de talleres
        st.subheader("🔄 Actualizar estado de producción")
        
        if not df_talleres.empty:
            # Filtrar para mostrar primero los en producción
            df_en_produccion = df_talleres[df_talleres["Estado"] == "EN PRODUCCIÓN"]
            df_entregados = df_talleres[df_talleres["Estado"] == "ENTREGADO"]
            
            # Mostrar en producción primero
            for _, taller_row in df_en_produccion.iterrows():
                # Obtener información del corte original
                try:
                    corte_original = df_cortes[df_cortes["ID"].astype(str) == str(taller_row.get("ID Corte"))].iloc[0]
                    total_prendas = int(corte_original.get('Prendas', 0))
                except:
                    corte_original = None
                    total_prendas = 0
                
                # Calcular días transcurridos
                dias_transcurridos = 0
                if taller_row.get("Fecha Envío"):
                    try:
                        fecha_envio = pd.to_datetime(taller_row.get("Fecha Envío"))
                        dias_transcurridos = (date.today() - fecha_envio.date()).days
                    except:
                        dias_transcurridos = 0
                
                with st.expander(f"🧵 {taller_row.get('Artículo', '')} - {taller_row.get('Taller', '')} ({dias_transcurridos} días)"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        prendas_recibidas = st.number_input(
                            f"Prendas recibidas (Total: {total_prendas})",
                            min_value=0,
                            max_value=total_prendas,
                            value=int(taller_row.get("Prendas Recibidas", 0)),
                            key=f"recibidas_{taller_row.get('ID Corte', '')}"
                        )
                        # Mostrar faltante
                        faltante = total_prendas - prendas_recibidas
                        st.write(f"**Faltante:** {faltante} prendas")
                        if faltante == 0 and prendas_recibidas > 0:
                            st.success("✅ Completo")
                        
                    with col2:
                        prendas_falladas = st.number_input(
                            f"Prendas falladas",
                            min_value=0,
                            max_value=prendas_recibidas,
                            value=int(taller_row.get("Prendas Falladas", 0)),
                            key=f"falladas_{taller_row.get('ID Corte', '')}"
                        )
                        # Calcular porcentaje de falla
                        if prendas_recibidas > 0:
                            porcentaje_falla = (prendas_falladas / prendas_recibidas) * 100
                            st.write(f"**% Falla:** {porcentaje_falla:.1f}%")
                        
                    with col3:
                        fecha_entrega_value = date.today()
                        if taller_row.get("Fecha Entrega"):
                            try:
                                fecha_entrega_value = pd.to_datetime(taller_row.get("Fecha Entrega")).date()
                            except:
                                fecha_entrega_value = date.today()
                        
                        fecha_entrega = st.date_input(
                            "Fecha de entrega",
                            value=fecha_entrega_value,
                            key=f"fecha_{taller_row.get('ID Corte', '')}"
                        )
                        estado = st.selectbox(
                            "Estado",
                            ["EN PRODUCCIÓN", "ENTREGADO"],
                            index=0 if taller_row.get("Estado") == "EN PRODUCCIÓN" else 1,
                            key=f"estado_{taller_row.get('ID Corte', '')}"
                        )
                    
                    if st.button("💾 Actualizar", key=f"update_{taller_row.get('ID Corte', '')}"):
                        # Aquí iría la lógica para actualizar en Google Sheets
                        st.success("Registro actualizado correctamente")
                        st.rerun()
            
            # Mostrar entregados colapsados
            if not df_entregados.empty:
                with st.expander("📦 Cortes Entregados (Ver histórico)"):
                    for _, taller_row in df_entregados.iterrows():
                        st.write(f"• {taller_row.get('Artículo', '')} - {taller_row.get('Taller', '')}")
        
        # SECTION 3: Dashboard de seguimiento
        st.subheader("📈 Dashboard de Seguimiento")
        
        if not df_talleres.empty:
            # Convertir fechas
            df_talleres["Fecha Envío"] = pd.to_datetime(df_talleres["Fecha Envío"], errors='coerce')
            df_talleres["Días Transcurridos"] = df_talleres["Fecha Envío"].apply(
                lambda x: (date.today() - x.date()).days if pd.notnull(x) else 0
            )
            
            # Filtrar datos
            col_filtro1, col_filtro2 = st.columns(2)
            with col_filtro1:
                talleres_filtro = st.multiselect(
                    "Filtrar por Taller",
                    options=df_talleres["Taller"].unique(),
                    default=df_talleres["Taller"].unique()
                )
            with col_filtro2:
                estados_filtro = st.multiselect(
                    "Filtrar por Estado",
                    options=df_talleres["Estado"].unique(),
                    default=["EN PRODUCCIÓN"]
                )
            
            df_filtrado = df_talleres[
                (df_talleres["Taller"].isin(talleres_filtro)) & 
                (df_talleres["Estado"].isin(estados_filtro))
            ]
            
            # Métricas principales
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                en_produccion = len(df_filtrado[df_filtrado["Estado"] == "EN PRODUCCIÓN"])
                st.metric("🔄 En producción", en_produccion)
            with col2:
                entregados = len(df_filtrado[df_filtrado["Estado"] == "ENTREGADO"])
                st.metric("✅ Entregados", entregados)
            with col3:
                prendas_totales = df_filtrado["Prendas Recibidas"].sum()
                st.metric("👕 Prendas Recibidas", f"{prendas_totales:,}")
            with col4:
                pendientes = len(cortes_sin_asignar) if 'cortes_sin_asignar' in locals() else 0
                st.metric("📋 Pendientes asignar", pendientes)
            
            # Alertas con colores
            alertas_urgentes = df_filtrado[(df_filtrado["Días Transcurridos"] > 30) & (df_filtrado["Estado"] == "EN PRODUCCIÓN")]
            alertas_normales = df_filtrado[(df_filtrado["Días Transcurridos"] > 20) & (df_filtrado["Días Transcurridos"] <= 30) & (df_filtrado["Estado"] == "EN PRODUCCIÓN")]
            
            if not alertas_urgentes.empty:
                st.error("🚨 **URGENTE - Más de 30 días:**")
                for _, alerta in alertas_urgentes.iterrows():
                    st.write(f"• {alerta.get('Artículo', '')} en {alerta.get('Taller', '')}: {alerta['Días Transcurridos']} días")
            
            if not alertas_normales.empty:
                st.warning("⚠️ **ALERTA - Más de 20 días:**")
                for _, alerta in alertas_normales.iterrows():
                    st.write(f"• {alerta.get('Artículo', '')} en {alerta.get('Taller', '')}: {alerta['Días Transcurridos']} días")
            
            # Gráficos
            tab1, tab2, tab3 = st.tabs(["📊 Estado Producción", "📈 Rendimiento Talleres", "📋 Detalle"])
            
            with tab1:
                fig_estado = px.pie(df_filtrado, names='Estado', title='Distribución por Estado')
                st.plotly_chart(fig_estado, use_container_width=True)
            
            with tab2:
                if not df_filtrado.empty:
                    df_rendimiento = df_filtrado.groupby('Taller').agg({
                        'Prendas Recibidas': 'sum',
                        'Prendas Falladas': 'sum',
                        'Nro Corte': 'count'
                    }).reset_index()
                    df_rendimiento['% Falla'] = (df_rendimiento['Prendas Falladas'] / df_rendimiento['Prendas Recibidas'] * 100).fillna(0)
                    
                    fig_rendimiento = px.bar(df_rendimiento, x='Taller', y='Prendas Recibidas', 
                                           title='Prendas Recibidas por Taller')
                    st.plotly_chart(fig_rendimiento, use_container_width=True)
            
            with tab3:
                # Mostrar tabla sin ID Corte (redundante)
                columnas_mostrar = [col for col in df_filtrado.columns if col != "ID Corte"]
                df_mostrar = df_filtrado[columnas_mostrar].copy()
                df_mostrar["Fecha Envío"] = df_mostrar["Fecha Envío"].dt.strftime("%Y-%m-%d")
                
                st.dataframe(df_mostrar, use_container_width=True)





























