import streamlit as st
import pandas as pd
import gspread

from google.oauth2.service_account import Credentials
from supabase import create_client


# =========================================================
# CONFIGURACIÓN DE PÁGINA
# =========================================================

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
# CONFIGURACIÓN GENERAL
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


# IMPORTANTE:
# Este orden es fijo y representa las habitaciones
# de menor a mayor categoría.
#
# No se ordenarán alfabéticamente ni por precio.
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
# FUNCIONES AUXILIARES
# =========================================================

def limpiar_valor_moneda(val):
    """
    Convierte valores provenientes de Google Sheets
    a números float seguros.
    """

    if pd.isna(val) or val == "":
        return 0.0

    val_str = (
        str(val)
        .strip()
        .replace("$", "")
        .replace(" ", "")
    )

    # Ejemplo:
    # 1,250.50 → 1250.50
    if "," in val_str and "." in val_str:
        val_str = val_str.replace(",", "")

    # Ejemplo:
    # 75,50 → 75.50
    elif "," in val_str:
        val_str = val_str.replace(",", ".")

    try:
        resultado = float(val_str)

        if pd.isna(resultado):
            return 0.0

        return resultado

    except (ValueError, TypeError):
        return 0.0


# =========================================================
# CONEXIÓN SUPABASE
# =========================================================

@st.cache_resource(show_spinner=False)
def obtener_supabase():

    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["secret_key"]

    return create_client(url, key)


# =========================================================
# CONEXIÓN GOOGLE SHEETS
# =========================================================

@st.cache_resource(show_spinner=False)
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


# =========================================================
# DESCARGAR DATOS DE GOOGLE
# =========================================================

def obtener_datos_google():

    gc = obtener_google()

    url_doc = st.secrets["connections"]["gsheets"]["spreadsheet"]

    documento = gc.open_by_url(url_doc)

    # -----------------------------------------------------
    # CONFIG
    # -----------------------------------------------------

    ws_config = documento.worksheet("config")

    datos_config = ws_config.get_all_records()

    df_config = pd.DataFrame(datos_config)

    # -----------------------------------------------------
    # DIFERENCIALES
    # -----------------------------------------------------

    ws_dif = documento.worksheet("diferenciales")

    datos_dif = ws_dif.get_all_records()

    df_dif = pd.DataFrame(datos_dif)

    return df_config, df_dif


# =========================================================
# PROCESAR CONFIGURACIÓN
# =========================================================

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

    descuento = valores.get(
        "descuento",
        60.0
    )

    tc = valores.get(
        "tc",
        17.40
    )

    # Mantener la misma protección
    # que usa tu aplicación actual.
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


# =========================================================
# PROCESAR TARIFAS
# =========================================================

def procesar_tarifas(df_dif):

    if df_dif is None or df_dif.empty:
        raise Exception(
            "La pestaña 'diferenciales' está vacía."
        )

    if "mes" not in df_dif.columns:
        raise Exception(
            "No se encontró la columna 'mes' "
            "en la pestaña diferenciales."
        )

    df = df_dif.copy()

    df["mes"] = (
        df["mes"]
        .astype(str)
        .str.strip()
        .str.capitalize()
    )

    registros = []

    # Recorrer meses Enero → Diciembre
    for numero_mes, nombre_mes in enumerate(
        MESES,
        start=1
    ):

        fila_mes = df[
            df["mes"] == nombre_mes
        ]

        if fila_mes.empty:

            st.warning(
                f"No se encontró {nombre_mes} "
                f"en Google Drive."
            )

            continue

        fila = fila_mes.iloc[0]

        # Recorrer habitaciones en orden fijo
        # de menor a mayor categoría.
        for categoria in CATEGORIAS:

            if categoria not in df.columns:

                st.warning(
                    f"No existe la categoría "
                    f"'{categoria}' en Google Drive."
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
                    "amount": round(
                        float(amount),
                        2
                    ),
                }
            )

    return registros


# =========================================================
# CONECTAR CON SUPABASE
# =========================================================

try:

    supabase = obtener_supabase()

    prueba_supabase = (
        supabase
        .table("upsell_settings")
        .select("*")
        .order("year")
        .execute()
    )

    st.success(
        "✅ Supabase conectado correctamente."
    )

except Exception as e:

    st.error(
        "❌ No se pudo conectar con Supabase."
    )

    st.exception(e)

    st.stop()


# =========================================================
# CONECTAR CON GOOGLE DRIVE
# =========================================================

try:

    df_config, df_dif = obtener_datos_google()

    st.success(
        "✅ Google Drive conectado correctamente."
    )

except Exception as e:

    st.error(
        "❌ No se pudo leer Google Drive."
    )

    st.exception(e)

    st.stop()


# =========================================================
# PROCESAR DATOS
# =========================================================

try:

    config = procesar_config(
        df_config
    )

    registros = procesar_tarifas(
        df_dif
    )

except Exception as e:

    st.error(
        "❌ Error procesando los datos."
    )

    st.exception(e)

    st.stop()


# =========================================================
# CONFIGURACIÓN DETECTADA
# =========================================================

st.divider()

st.subheader(
    "Configuración detectada"
)

col1, col2 = st.columns(2)

with col1:

    st.metric(
        "Descuento actual",
        f"{config['descuento']:.2f}%"
    )

with col2:

    st.metric(
        "Tipo de cambio",
        f"${config['tc']:.2f} MXN"
    )


# =========================================================
# TARIFAS DETECTADAS
# =========================================================

st.divider()

st.subheader(
    "Tarifas detectadas para 2026"
)

st.caption(
    "Las habitaciones se muestran en orden fijo "
    "de menor a mayor categoría."
)

df_preview = pd.DataFrame(
    registros
)

if not df_preview.empty:

    # Convertir número de mes a nombre
    df_preview["Mes"] = (
        df_preview["month"]
        .apply(
            lambda numero:
            MESES[numero - 1]
        )
    )

    # Crear tabla:
    # Categorías = filas
    # Meses = columnas
    tabla = df_preview.pivot(
        index="category",
        columns="Mes",
        values="amount"
    )

    # =====================================================
    # ORDENAR HABITACIONES
    # MENOR → MAYOR CATEGORÍA
    # =====================================================

    categorias_disponibles = [
        categoria
        for categoria in CATEGORIAS
        if categoria in tabla.index
    ]

    tabla = tabla.reindex(
        categorias_disponibles
    )

    # =====================================================
    # ORDENAR MESES
    # ENERO → DICIEMBRE
    # =====================================================

    meses_disponibles = [
        mes
        for mes in MESES
        if mes in tabla.columns
    ]

    tabla = tabla[
        meses_disponibles
    ]

    # Mostrar tabla
    st.dataframe(
        tabla,
        use_container_width=True
    )

    st.caption(
        f"{len(registros)} registros "
        f"preparados para migración."
    )

else:

    st.error(
        "No se encontraron tarifas "
        "para migrar."
    )

    st.stop()


# =========================================================
# VALIDACIÓN VISUAL DE JERARQUÍA
# =========================================================

st.divider()

st.subheader(
    "Jerarquía de habitaciones"
)

st.caption(
    "Esta será la jerarquía utilizada "
    "posteriormente en el panel Revenue."
)

for indice, categoria in enumerate(
    CATEGORIAS,
    start=1
):

    st.write(
        f"{indice}. {categoria}"
    )


# =========================================================
# ADVERTENCIA TEMPORADAS ESPECIALES
# =========================================================

st.divider()

st.warning(
    "Las temporadas especiales NO serán migradas "
    "en este paso. Actualmente Google Drive utiliza "
    "una Tarifa Base para esas fechas, mientras que "
    "el nuevo sistema utilizará un Descuento Especial (%). "
    "Las configuraremos después para evitar "
    "conversiones incorrectas."
)


# =========================================================
# CONFIRMACIÓN DE MIGRACIÓN
# =========================================================

st.divider()

st.subheader(
    "Migrar a Supabase"
)

confirmar = st.checkbox(
    "He revisado las tarifas y deseo copiarlas "
    "a Supabase como tarifas 2026."
)


# =========================================================
# BOTÓN MIGRAR
# =========================================================

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

            # =================================================
            # GUARDAR CONFIGURACIÓN 2026
            # =================================================

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

            # =================================================
            # GUARDAR TARIFAS 2026
            # =================================================

            (
                supabase
                .table("upsell_rates")
                .upsert(
                    registros,
                    on_conflict=(
                        "year,month,category"
                    ),
                )
                .execute()
            )

        st.success(
            "✅ Migración completada correctamente."
        )

        st.balloons()

        st.write(
            f"Se guardaron "
            f"{len(registros)} tarifas "
            f"del año 2026."
        )

        # =================================================
        # VERIFICACIÓN DESDE SUPABASE
        # =================================================

        st.divider()

        st.subheader(
            "Verificación desde Supabase"
        )

        verificacion = (
            supabase
            .table("upsell_rates")
            .select(
                "year,month,category,amount"
            )
            .eq(
                "year",
                2026
            )
            .execute()
        )

        df_verificacion = pd.DataFrame(
            verificacion.data
        )

        if not df_verificacion.empty:

            # -------------------------------------------------
            # CREAR ORDEN DE CATEGORÍAS
            # -------------------------------------------------

            orden_categorias = {
                categoria: indice
                for indice, categoria
                in enumerate(CATEGORIAS)
            }

            # -------------------------------------------------
            # ORDENAR:
            # MES
            # +
            # CATEGORÍA MENOR → MAYOR
            # -------------------------------------------------

            df_verificacion[
                "_orden_categoria"
            ] = (
                df_verificacion[
                    "category"
                ].map(
                    orden_categorias
                )
            )

            df_verificacion = (
                df_verificacion
                .sort_values(
                    by=[
                        "month",
                        "_orden_categoria"
                    ]
                )
                .drop(
                    columns=[
                        "_orden_categoria"
                    ]
                )
            )

            st.dataframe(
                df_verificacion,
                use_container_width=True,
                hide_index=True
            )

            st.success(
                "Los datos anteriores fueron "
                "leídos directamente desde Supabase."
            )

        else:

            st.warning(
                "Supabase respondió correctamente, "
                "pero no se encontraron tarifas 2026."
            )

    except Exception as e:

        st.error(
            "❌ Ocurrió un error "
            "durante la migración."
        )

        st.exception(e)
