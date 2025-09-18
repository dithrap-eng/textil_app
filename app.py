import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import date

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

# =====================
# INTERFAZ STREAMLIT
# =====================
st.set_page_config(page_title="Sistema Textil", layout="wide")

menu = st.sidebar.radio(
    "Navegación",
    ["📥 Compras", "📦 Stock", "✂ Cortes", "🏭 Proveedores"]
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
# Resumen de compras (versión corregida)
# -------------------------------
st.subheader("Resumen de compras")
df_resumen = get_compras_resumen()

if not df_resumen.empty:
    # Asegurarnos de que tenemos las columnas necesarias
    required_cols = ["Total metros", "Precio por metro (USD)", "Rollos totales", "Total USD"]
    for col in required_cols:
        if col not in df_resumen.columns:
            st.error(f"Falta la columna: {col}")
            break
    
    # Convertir a numérico
    df_resumen["Total metros"] = pd.to_numeric(df_resumen["Total metros"], errors="coerce")
    df_resumen["Precio por metro (USD)"] = pd.to_numeric(df_resumen["Precio por metro (USD)"], errors="coerce")
    df_resumen["Rollos totales"] = pd.to_numeric(df_resumen["Rollos totales"], errors="coerce")
    df_resumen["Total USD"] = pd.to_numeric(df_resumen["Total USD"], errors="coerce")
    
    # Calcular precio promedio por rollo (si no existe o necesita recalculo)
    if "Precio promedio x rollo" not in df_resumen.columns:
        df_resumen["Precio promedio x rollo"] = df_resumen["Total USD"] / df_resumen["Rollos totales"]
    else:
        df_resumen["Precio promedio x rollo"] = pd.to_numeric(
            df_resumen["Precio promedio x rollo"], errors="coerce"
        )
        # Recalcular si hay valores faltantes
        mask = df_resumen["Precio promedio x rollo"].isna()
        df_resumen.loc[mask, "Precio promedio x rollo"] = (
            df_resumen.loc[mask, "Total USD"] / df_resumen.loc[mask, "Rollos totales"]
        )
    
    # Crear una copia para mostrar con formato
    df_mostrar = df_resumen.copy()
    
    # Aplicar formato a las columnas numéricas
    df_mostrar["Total metros"] = df_mostrar["Total metros"].apply(
        lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(x) else ""
    )
    df_mostrar["Precio por metro (USD)"] = df_mostrar["Precio por metro (USD)"].apply(
        lambda x: f"USD {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(x) else ""
    )
    df_mostrar["Total USD"] = df_mostrar["Total USD"].apply(
        lambda x: f"USD {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(x) else ""
    )
    df_mostrar["Precio promedio x rollo"] = df_mostrar["Precio promedio x rollo"].apply(
        lambda x: f"USD {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(x) else ""
    )
    df_mostrar["Rollos totales"] = df_mostrar["Rollos totales"].apply(
        lambda x: f"{x:,.0f}".replace(",", ".") if pd.notna(x) else ""
    )
    
    # 🔎 Mostrar tabla
    st.dataframe(df_mostrar, use_container_width=True)
    
    # Mostrar también los datos numéricos sin formato para debugging
    with st.expander("Ver datos numéricos sin formato (solo para debugging)"):
        st.dataframe(df_resumen)
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
        st.subheader("Totales de la selección")
        st.write(f"📦 Total de rollos: {total_rollos}")

        df_compras = get_compras_resumen()
        if not df_compras.empty and "Precio promedio x rollo" in df_compras.columns:
            df_compras["Precio promedio x rollo"] = pd.to_numeric(df_compras["Precio promedio x rollo"], errors="coerce")
            precio_promedio_global = df_compras["Precio promedio x rollo"].mean()
            total_valorizado = total_rollos * precio_promedio_global
            st.write(f"💲 Valor estimado (rollos × precio promedio): USD {total_valorizado:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

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




