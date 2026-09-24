import streamlit as st
import pandas as pd
import gspread

from google.oauth2.service_account import Credentials
from supabase import create_client


st.set_page_config(
    page_title="Migración Upsells 2026",
    page_icon="🏨",
    layout="wide"
)

st.title("Migración de Upsells — Google Drive → Supabase")
st.info(
    "Esta herramienta copiará la configuración y las tarifas mensuales "
    "actuales de Google Drive a Supabase como datos del año 2026."
)


# =========================================================
# CONFIGURACIÓN
# =========================================================

MESES = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]

CATEGORIAS = [
    "Standard Two Double Beds",
    "Junior Suite",
    "Deluxe Suite",
    "Executive Suite",
    "One Bedroom Suite",
    "One Bedroom Plus",
    "One Bedroom Ocean Front",
    "Two Bedroom Suite",
    "Two Bedroom Ocean Front",
    "One Bedroom Penthouse",
    "Two Bedroom Penthouse",
    "Three Bedroom Penthouse",
]


# =========================================================
# FUNCIONES
# =========================================================

def limpiar_valor_moneda(val):
    if pd.isna(val) or val == "":
        return 0.0

    val_str = str(val).strip().replace("$", "").replace(" ", "")

    if "," in val_str and "." in val_str:
        val_str = val_str.replace(",", "")
    elif "," in val_str:
        val_str = val_str.replace(",", ".")

    try:
        res = float(val_str)
        return 0.0 if pd.isna(res) else res
    except (ValueError, TypeError):
        return 0.0


@st.cache_resource
def obtener_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["secret_key"]

    return create_client(url, key)


@st.cache_resource
def obtener_google():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds_info = st.secrets["gcp_service_account"]

    credentials = Credentials.from_service_account_info(
        creds_info,
        scopes=scope
    )

    return gspread.authorize(credentials)


def obtener_datos_google():
    gc = obtener_google()

    url_doc = st.secrets["connections"]["gsheets"]["spreadsheet"]

    documento = gc.open_by_url(url_doc)

    # CONFIG
    ws_config = documento.worksheet("config")
    datos_config = ws_config.get_all_records()
    df_config = pd.DataFrame(datos_config)

    # DIFERENCIALES
    ws_dif = documento.worksheet("diferenciales")
    datos_dif = ws_dif.get_all_records()
    df_dif = pd.DataFrame(datos_dif)

    return df_config, df_dif


def procesar_config(df_config):
    config = {
        "descuento": 60.0,
        "tc": 17.40,
    }

    if df_config is None or df_config.empty:
        return config

    valores = {}

    for _, fila in df_config.iterrows():

        parametro = str(
            fila.get("parametro", "")
        ).strip().lower()

        valor = limpiar_valor_moneda(
            fila.get("valor", 0)
        )

        valores[parametro] = valor

    descuento = valores.get("descuento", 60.0)
    tc = valores.get("tc", 17.40)

    # Conservamos la misma protección que usa tu app actual.
    while descuento > 100:
        descuento /= 100

    while tc > 100:
        tc /= 100

    if descuento <= 0:
        descuento = 60.0

    if tc <= 0:
        tc = 17.40

    config["descuento"] = float(descuento)
    config["tc"] = float(tc)

    return config


def procesar_tarifas(df_dif):
    if df_dif is None or df_dif.empty:
        raise Exception(
            "La pestaña 'diferenciales' está vacía."
        )

    if "mes" not in df_dif.columns:
        raise Exception(
            "No se encontró la columna 'mes' en diferenciales."
        )

    df = df_dif.copy()

    df["mes"] = (
        df["mes"]
        .astype(str)
        .str.strip()
        .str.capitalize()
    )

    registros = []

    for numero_mes, nombre_mes in enumerate(MESES, start=1):

        fila_mes = df[df["mes"] == nombre_mes]

        if fila_mes.empty:
            st.warning(
                f"No se encontró {nombre_mes} en Google Drive."
            )
            continue

        fila = fila_mes.iloc[0]

        for categoria in CATEGORIAS:

            if categoria not in df.columns:
                st.warning(
                    f"No existe la categoría '{categoria}' "
                    f"en la hoja de Google."
                )
                continue

            amount = limpiar_valor_moneda(
                fila[categoria]
            )

            registros.append(
                {
                    "year": 2026,
                    "month": numero_mes,
                    "category": categoria,
                    "amount": round(float(amount), 2),
                }
            )

    return registros


# =========================================================
# CONEXIONES
# =========================================================

try:

    supabase = obtener_supabase()

    # Comprobar Supabase
    prueba = (
        supabase
        .table("upsell_settings")
        .select("*")
        .order("year")
        .execute()
    )

    st.success("Supabase conectado correctamente.")

except Exception as e:

    st.error("No se pudo conectar con Supabase.")
    st.exception(e)
    st.stop()


try:

    df_config, df_dif = obtener_datos_google()

    st.success("Google Drive conectado correctamente.")

except Exception as e:

    st.error("No se pudo leer Google Drive.")
    st.exception(e)
    st.stop()


# =========================================================
# PREPARAR DATOS
# =========================================================

try:

    config = procesar_config(df_config)

    registros = procesar_tarifas(df_dif)

except Exception as e:

    st.error("Error procesando los datos.")
    st.exception(e)
    st.stop()


# =========================================================
# MOSTRAR CONFIG
# =========================================================

st.divider()

st.subheader("Configuración detectada")

col1, col2 = st.columns(2)

col1.metric(
    "Descuento actual",
    f"{config['descuento']:.2f}%"
)

col2.metric(
    "Tipo de cambio",
    f"${config['tc']:.2f} MXN"
)


# =========================================================
# MOSTRAR TARIFAS
# =========================================================

st.divider()

st.subheader("Tarifas detectadas para 2026")

df_preview = pd.DataFrame(registros)

if not df_preview.empty:

    df_preview["Mes"] = df_preview["month"].apply(
        lambda x: MESES[x - 1]
    )

    tabla = df_preview.pivot(
        index="category",
        columns="Mes",
        values="amount"
    )

    # Mantener orden de meses
    columnas_disponibles = [
        mes
        for mes in MESES
        if mes in tabla.columns
    ]

    tabla = tabla[columnas_disponibles]

    st.dataframe(
        tabla,
        use_container_width=True
    )

    st.caption(
        f"{len(registros)} registros preparados para migración."
    )

else:

    st.error("No se encontraron tarifas para migrar.")
    st.stop()


# =========================================================
# ADVERTENCIA SOBRE TEMPORADAS
# =========================================================

st.divider()

st.warning(
    "Las temporadas especiales NO serán migradas en este paso. "
    "Actualmente Google Drive guarda una Tarifa Base para esas fechas, "
    "pero el nuevo sistema utilizará un Descuento Especial (%). "
    "Las configuraremos después para evitar conversiones incorrectas."
)


# =========================================================
# CONFIRMACIÓN
# =========================================================

confirmar = st.checkbox(
    "He revisado las tarifas y deseo copiarlas a Supabase como 2026."
)

if st.button(
    "Migrar datos 2026 a Supabase",
    type="primary",
    disabled=not confirmar,
    use_container_width=True
):

    try:

        with st.spinner(
            "Migrando configuración y tarifas..."
        ):

            # ---------------------------------------------
            # CONFIGURACIÓN 2026
            # ---------------------------------------------

            (
                supabase
                .table("upsell_settings")
                .upsert(
                    {
                        "year": 2026,
                        "discount": config["descuento"],
                        "exchange_rate": config["tc"],
                    },
                    on_conflict="year",
                )
                .execute()
            )

            # ---------------------------------------------
            # TARIFAS 2026
            # ---------------------------------------------

            (
                supabase
                .table("upsell_rates")
                .upsert(
                    registros,
                    on_conflict="year,month,category",
                )
                .execute()
            )

        st.success(
            "Migración completada correctamente."
        )

        st.balloons()

        st.write(
            f"Se guardaron {len(registros)} tarifas del año 2026."
        )

        # ---------------------------------------------
        # VERIFICACIÓN
        # ---------------------------------------------

        verificacion = (
            supabase
            .table("upsell_rates")
            .select(
                "year,month,category,amount"
            )
            .eq("year", 2026)
            .execute()
        )

        st.subheader(
            "Verificación de datos en Supabase"
        )

        st.dataframe(
            verificacion.data,
            use_container_width=True
        )

    except Exception as e:

        st.error(
            "Ocurrió un error durante la migración."
        )

        st.exception(e)
