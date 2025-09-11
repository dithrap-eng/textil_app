import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import date

# Nombre de tu Google Sheet (ajustalo si tu hoja tiene otro nombre)
SPREADSHEET_NAME = "textil_sistema"

@st.cache_resource
def init_connection():
    # Scopes necesarios
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]

    # Verificamos que las credenciales estén en secrets
    if "gcp_service_account" not in st.secrets:
        st.error("No se encontraron credenciales en Secrets. Ve a Manage app → Settings → Secrets y pegá tu cuenta de servicio bajo la clave [gcp_service_account].")
        st.stop()

    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error("Error creando las credenciales desde Secrets. Revisa el formato de tu clave en Streamlit Secrets.")
        st.exception(e)
        st.stop()

# Inicializar conexión
client = init_connection()

# Intentar abrir el spreadsheet
try:
    spreadsheet = client.open(SPREADSHEET_NAME)
except Exception as e:
    st.error(f"No se pudo abrir el Google Sheet llamado '{SPREADSHEET_NAME}'.")
    st.markdown("**Verificá:**")
    st.markdown("- Que el nombre del Google Sheet sea exactamente: `" + SPREADSHEET_NAME + "`")
    st.markdown("- Que la cuenta de servicio tenga acceso (Compartir → editor) al Google Sheet")
    st.exception(e)
    st.stop()

# ---------- funciones (igual que antes) ----------
def insert_proveedor(nombre):
    ws = spreadsheet.worksheet("Proveedores")
    ws.append_row([nombre])

def get_proveedores():
    ws = spreadsheet.worksheet("Proveedores")
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []
    return [r[0] for r in rows[1:]]

def insert_purchase(fecha, proveedor, tipo_tela, total_metros, precio_por_metro, lineas):
    ws_compras = spreadsheet.worksheet("Compras")
    ws_detalle = spreadsheet.worksheet("Detalle_Compras")

    total_rollos = sum(int(l["rollos"]) for l in lineas)
    total_valor = total_metros * float(precio_por_metro)

    compra_id = len(ws_compras.col_values(1))
    ws_compras.append_row([
        compra_id, str(fecha), proveedor, tipo_tela,
        total_metros, precio_por_metro, total_rollos, total_valor
    ])

    for l in lineas:
        if l["rollos"] > 0:
            ws_detalle.append_row([compra_id, tipo_tela, l["color"], l["rollos"]])

def get_compras_resumen():
    ws = spreadsheet.worksheet("Compras")
    data = ws.get_all_records()
    return pd.DataFrame(data)

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

    # actualizar stock en Detalle_Compras (restar rollos)
    ws_detalle_compras = spreadsheet.worksheet("Detalle_Compras")
    data = ws_detalle_compras.get_all_records()
    df = pd.DataFrame(data)

    for l in lineas:
        idx = df[(df["Tipo de tela"] == tipo_tela) & (df["Color"] == l["color"])].index
        if not idx.empty:
            row = idx[0] + 2
            new_value = int(df.loc[idx[0], "Rollos"]) - l["rollos"]
            if new_value < 0: new_value = 0
            ws_detalle_compras.update_cell(row, 4, new_value)

def get_stock_resumen():
    ws_detalle = spreadsheet.worksheet("Detalle_Compras")
    data = ws_detalle.get_all_records()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    df_stock = df.groupby(["Tipo de tela", "Color"])["Rollos"].sum().reset_index()
    return df_stock

# ---------------- UI ----------------
st.set_page_config(page_title="Sistema Textil", layout="wide")
menu = st.sidebar.radio("Navegación", ["📥 Compras", "📦 Stock", "✂️ Cortes", "🏭 Proveedores"])

# Proveedores
if menu == "🏭 Proveedores":
    st.header("Gestión de Proveedores")
    nuevo_proveedor = st.text_input("Nombre de proveedor")
    if st.button("➕ Agregar proveedor"):
        if nuevo_proveedor:
            insert_proveedor(nuevo_proveedor)
            st.success("Proveedor agregado correctamente ✅")
    proveedores = get_proveedores()
    if proveedores:
        st.subheader("Lista de proveedores")
        st.write(proveedores)

# Compras
elif menu == "📥 Compras":
    st.header("Registrar compra de tela")
    fecha = st.date_input("Fecha", value=date.today())
    proveedores = get_proveedores()
    proveedor = st.selectbox("Proveedor", proveedores if proveedores else ["---"])
    tipo_tela = st.text_input("Tipo de tela")
    total_metros = st.number_input("Total metros de la compra", min_value=1.0, step=0.5)
    precio_por_metro = st.number_input("Precio por metro (USD)", min_value=0.0, step=0.5)

    st.subheader("Colores y rollos")
    num_colores = st.number_input("Cantidad de colores", min_value=1, max_value=12, value=3, step=1)
    lineas = []
    for i in range(num_colores):
        col1, col2 = st.columns([2,1])
        with col1:
            color = st.text_input(f"Color {i+1}")
        with col2:
            rollos = st.number_input(f"Rollos {i+1}", min_value=0, step=1)
        if color and rollos > 0:
            lineas.append({"color": color, "rollos": rollos})

    total_usd = precio_por_metro * total_metros
    st.metric("TOTAL compra (USD)", round(total_usd,2))

    if st.button("💾 Guardar compra"):
        insert_purchase(fecha, proveedor, tipo_tela, total_metros, precio_por_metro, lineas)
        st.success("✅ Compra registrada")

st.subheader("Resumen de compras")
df_resumen = get_compras_resumen()
if not df_resumen.empty:
    # Formatear columnas numéricas
    df_resumen["Total metros"] = df_resumen["Total metros"].map(lambda x: f"{x:,.2f}")
    df_resumen["Precio por metro (USD)"] = df_resumen["Precio por metro (USD)"].map(lambda x: f"{x:,.2f}")
    df_resumen["Rollos totales"] = df_resumen["Rollos totales"].map(lambda x: f"{x:,}")
    df_resumen["Total USD"] = df_resumen["Total USD"].map(lambda x: f"{x:,.2f}")

    st.dataframe(df_resumen, use_container_width=True)
else:
    st.info("No hay compras registradas aún.")

# Stock
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

# Cortes
elif menu == "✂️ Cortes":
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
        stock_color = df_stock[(df_stock["Tipo de tela"] == tipo_tela) & (df_stock["Color"] == c)]["Rollos"].sum()
        st.metric(f"Stock disponible de {c}", stock_color)
        rollos_usados = st.number_input(f"Rollos consumidos de {c}", min_value=0, step=1)
        if rollos_usados > 0:
            lineas.append({"color": c, "rollos": rollos_usados})

    consumo_total = st.number_input("Consumo total (m)", min_value=0.0, step=0.5)
    prendas = st.number_input("Cantidad de prendas", min_value=1, step=1)
    consumo_x_prenda = consumo_total / prendas if prendas > 0 else 0
    st.metric("Consumo por prenda (m)", round(consumo_x_prenda,2))

    if st.button("💾 Guardar corte"):
        insert_corte(fecha, nro_corte, articulo, tipo_tela, lineas, consumo_total, prendas, consumo_x_prenda)
        st.success("✅ Corte registrado y stock actualizado")

