import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# -------------------------------
# 1. Conectar con Google Sheets
# -------------------------------
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

client = gspread.authorize(creds)

# Cambia por el nombre real de tu Google Sheet
SPREADSHEET_NAME = "textil_sistema"
try:
    sheet_stock = client.open(SPREADSHEET_NAME).worksheet("Stock")
    sheet_cortes = client.open(SPREADSHEET_NAME).worksheet("Cortes")
except Exception as e:
    st.error("❌ No se pudo conectar con Google Sheets")
    st.stop()

# -------------------------------
# 2. Funciones auxiliares
# -------------------------------
def cargar_stock():
    datos = sheet_stock.get_all_records()
    return pd.DataFrame(datos)

def cargar_cortes():
    datos = sheet_cortes.get_all_records()
    return pd.DataFrame(datos)

def registrar_corte(fecha, numero, articulo, tela, color, rollos, consumo, prendas):
    # Insertar fila en la hoja "Cortes"
    sheet_cortes.append_row([fecha, numero, articulo, tela, color, rollos, consumo, prendas])
    
    # Descontar del stock
    stock = sheet_stock.get_all_records()
    for i, fila in enumerate(stock, start=2):  # empieza en 2 porque la fila 1 son los encabezados
        if fila["Tela"] == tela and fila["Color"] == color:
            nuevo_stock = int(fila["Rollos"]) - int(rollos)
            sheet_stock.update_cell(i, 3, nuevo_stock)  # col 3 = Rollos
            break

# -------------------------------
# 3. Interfaz con Streamlit
# -------------------------------
st.title("📊 Sistema Textil - Gestión de Stock y Cortes")

menu = st.sidebar.selectbox("Menú", ["Ver Stock", "Registrar Corte", "Ver Cortes"])

# Ver stock
if menu == "Ver Stock":
    st.subheader("📦 Stock de Telas")
    df = cargar_stock()
    st.dataframe(df)

# Registrar corte
elif menu == "Registrar Corte":
    st.subheader("✂️ Registrar Corte")

    fecha = st.date_input("Fecha de corte")
    numero = st.text_input("Número de corte")
    articulo = st.text_input("Artículo")

    stock_df = cargar_stock()
    tela = st.selectbox("Tela usada", stock_df["Tela"].unique())
    colores_disponibles = stock_df[stock_df["Tela"] == tela]["Color"].unique()
    color = st.selectbox("Color", colores_disponibles)

    rollos = st.number_input("Cantidad de rollos", min_value=1, step=1)
    consumo = st.number_input("Consumo total (metros)", min_value=0.0, step=0.1)
    prendas = st.number_input("Cantidad de prendas", min_value=1, step=1)

    if st.button("Registrar"):
        registrar_corte(str(fecha), numero, articulo, tela, color, rollos, consumo, prendas)
        st.success("✅ Corte registrado y stock actualizado")

# Ver cortes
elif menu == "Ver Cortes":
    st.subheader("📑 Registro de Cortes")
    df = cargar_cortes()
    st.dataframe(df)
