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
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], scope
    )
    client = gspread.authorize(creds)
    return client

client = init_connection()
spreadsheet = client.open(SHEET_NAME)

# =====================
# FUNCIONES DE GUARDADO
# =====================

def insert_purchase(fecha, proveedor, tipo_tela, total_metros, precio_por_metro, lineas):
    ws_compras = spreadsheet.worksheet("Compras")
    ws_detalle = spreadsheet.worksheet("Detalle_Compras")

    total_rollos = sum(int(l["rollos"]) for l in lineas)
    total_valor = total_metros * float(precio_por_metro)

    compra_id = len(ws_compras.col_values(1))
    ws_compras.append_row([
        compra_id, str(fecha), proveedor, tipo_tela, total_metros, precio_por_metro,
        total_rollos, total_valor
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

# =====================
# STREAMLIT UI
# =====================
st.set_page_config(page_title="Sistema Textil", layout="wide")

menu = st.sidebar.radio("Navegación", ["📥 Compras", "📦 Stock", "✂️ Cortes"])

# --- MÓDULO COMPRAS ---
if menu == "📥 Compras":
    st.header("Registrar compra de tela")

    fecha = st.date_input("Fecha", value=date.today())

    # cargar proveedores desde Google Sheets
    ws_proveedores = spreadsheet.worksheet("Proveedores")
    proveedores = [p[0] for p in ws_proveedores.get_all_values()[1:]]  # saltea encabezado
    proveedor = st.selectbox("Proveedor", proveedores)

    tipo_tela = st.text_input("Tipo de tela")
    total_metros = st.number_input("Total de metros", min_value=1.0, step=0.5)
    precio_por_metro = st.number_input("Precio por metro (USD)", min_value=0.0, step=0.5)

    st.subheader("Colores y rollos")
    lineas = []
    num_colores = st.number_input("Cantidad de colores", min_value=1, max_value=10, value=3, step=1)

    for i in range(num_colores):
        col1, col2 = st.columns([2,1])
        with col1:
            color = st.text_input(f"Color {i+1}")
        with col2:
            rollos = st.number_input(f"Rollos {i+1}", min_value=0, step=1)
        if color and rollos > 0:
            lineas.append({"color": color, "rollos": rollos})

    total_valor = total_metros * precio_por_metro
    st.metric("💵 Total compra (USD)", f"${total_valor:,.2f}")

    if st.button("💾 Guardar compra"):
        insert_purchase(fecha, proveedor, tipo_tela, total_metros, precio_por_metro, lineas)
        st.success("✅ Compra registrada")

    # Resumen de compras
    st.subheader("📊 Resumen de compras")
    ws_compras = spreadsheet.worksheet("Compras")
    compras_data = ws_compras.get_all_records()
    df_compras = pd.DataFrame(compras_data)

    if not df_compras.empty:
        df_compras["Precio por metro"] = df_compras["Precio por metro"].apply(lambda x: f"${x:,.2f}")
        df_compras["Total (USD)"] = df_compras["Total (USD)"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(df_compras, use_container_width=True)

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
        stock_color = int(df_stock[(df_stock["Tipo de tela"] == tipo_tela) & (df_stock["Color"] == c)]["Rollos"].sum())
        st.info(f"Stock disponible de {c}: {stock_color} rollos")
        rollos_usados = st.number_input(f"Rollos consumidos de {c}", min_value=0, step=1)
        if rollos_usados > 0:
            lineas.append({"color": c, "rollos": rollos_usados})

    consumo_total = st.number_input("Consumo total (m)", min_value=0.0, step=0.5)
    prendas = st.number_input("Cantidad de prendas", min_value=1, step=1)
    consumo_x_prenda = consumo_total / prendas if prendas > 0 else 0

    st.metric("Consumo por prenda (m)", round(consumo_x_prenda, 2))

    if st.button("💾 Guardar corte"):
        insert_corte(fecha, nro_corte, articulo, tipo_tela, lineas, consumo_total, prendas, consumo_x_prenda)
        st.success("✅ Corte registrado y stock actualizado")
