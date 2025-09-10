import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date

# =====================
# CONEXIÓN A GOOGLE SHEETS
# =====================
SHEET_NAME = "textil_sistema"

@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", scope)
    client = gspread.authorize(creds)
    return client

client = init_connection()
spreadsheet = client.open(SHEET_NAME)

# =====================
# FUNCIONES DE GUARDADO
# =====================

def insert_purchase(fecha, proveedor, tipo_tela, metros_por_rollo, precio_por_metro, lineas):
    ws_compras = spreadsheet.worksheet("Compras")
    ws_detalle = spreadsheet.worksheet("Detalle_Compras")

    total_rollos = sum(int(l["rollos"]) for l in lineas)
    total_metros = total_rollos * float(metros_por_rollo)
    total_valor = total_metros * float(precio_por_metro)

    compra_id = len(ws_compras.col_values(1))  # ID simple = nro de fila
    ws_compras.append_row([
        compra_id, str(fecha), proveedor, tipo_tela, metros_por_rollo, precio_por_metro,
        total_rollos, total_metros, total_valor
    ])

    for l in lineas:
        if l["rollos"] > 0:
            metros_total = l["rollos"] * metros_por_rollo
            valor_total = metros_total * precio_por_metro
            ws_detalle.append_row([
                compra_id, tipo_tela, l["color"], l["rollos"], metros_total, valor_total
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
            if new_value < 0: new_value = 0
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

# =====================
# STREAMLIT UI
# =====================
st.set_page_config(page_title="Sistema Textil", layout="wide")

menu = st.sidebar.radio("Navegación", ["📥 Compras", "📦 Stock", "✂️ Cortes"])

# --- MÓDULO COMPRAS ---
if menu == "📥 Compras":
    st.header("Registrar compra de tela")

    fecha = st.date_input("Fecha", value=date.today())
    proveedor = st.text_input("Proveedor")
    tipo_tela = st.text_input("Tipo de tela")
    metros_por_rollo = st.number_input("Metros por rollo", min_value=1.0, step=0.5)
    precio_por_metro = st.number_input("Precio por metro", min_value=0.0, step=0.5)

    st.subheader("Colores y rollos")
    lineas = []
    for i in range(3):  # por ahora 3 filas fijas
        col1, col2 = st.columns([2,1])
        with col1:
            color = st.text_input(f"Color {i+1}")
        with col2:
            rollos = st.number_input(f"Rollos {i+1}", min_value=0, step=1)
        if color and rollos > 0:
            lineas.append({"color": color, "rollos": rollos})

    if st.button("💾 Guardar compra"):
        insert_purchase(fecha, proveedor, tipo_tela, metros_por_rollo, precio_por_metro, lineas)
        st.success("✅ Compra registrada")

# --- MÓDULO STOCK ---
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

# --- MÓDULO CORTES ---
elif menu == "✂️ Cortes":
    st.header("Registrar corte de tela")

    fecha = st.date_input("Fecha de corte", value=date.today())
    nro_corte = st.text_input("Número de corte")
    articulo = st.text_input("Artículo")

    df_stock = get_stock_resumen()
    telas = df_stock["Tipo de tela"].unique()
    tipo_tela = st.selectbox("Tela usada", telas if len(telas) else ["---"])

    colores = df_stock[df_stock["Tipo de tela"] == tipo_tela]["Color"].unique() if len(df_stock) else []
    colores_sel = st.multiselect("Colores usados", colores)

    lineas = []
    for c in colores_sel:
        rollos_usados = st.number_input(f"Rollos consumidos de {c}", min_value=0, step=1)
        if rollos_usados > 0:
            lineas.append({"color": c, "rollos": rollos_usados})

    # calcular metros totales
    ws_compras = spreadsheet.worksheet("Compras")
    compras_data = ws_compras.get_all_records()
    compras_df = pd.DataFrame(compras_data)
    if not compras_df.empty and tipo_tela in compras_df["Tipo de tela"].values:
        metros_por_rollo = compras_df[compras_df["Tipo de tela"] == tipo_tela]["Metros por rollo"].iloc[0]
    else:
        metros_por_rollo = 0

    consumo_total = sum(l["rollos"] for l in lineas) * metros_por_rollo
    prendas = st.number_input("Cantidad de prendas", min_value=1, step=1)
    consumo_x_prenda = consumo_total / prendas if prendas > 0 else 0

    st.metric("Consumo total (m)", consumo_total)
    st.metric("Consumo por prenda (m)", round(consumo_x_prenda,2))

    if st.button("💾 Guardar corte"):
        insert_corte(fecha, nro_corte, articulo, tipo_tela, lineas, consumo_total, prendas, consumo_x_prenda)
        st.success("✅ Corte registrado y stock actualizado")
