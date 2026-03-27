# ===============================
# IMPORTS PRINCIPALES
# ===============================
# Librerías para seguridad, API, base de datos, mapas y utilidades

from cryptography.fernet import Fernet   # 🔐 Encriptación de tokens
import json                              # 📦 Manejo de JSON
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import cx_Oracle                         # 🗄️ Conexión Oracle
import pandas as pd                      # 📊 Procesamiento de datos
import folium                            # 🗺️ Mapas
import math
from folium.plugins import HeatMap, MarkerCluster
import os
from dotenv import load_dotenv
import base64
import uuid
print("🔥🔥🔥 API_PANEL CORRIENDO 🔥🔥🔥")

# ===============================
# CARGAR CALLES
# ===============================


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ruta_geo = os.path.join(
    BASE_DIR,
    "zonas_ejes_para_webmap_smr",
    "ejes_ide_24022026.geojson"
)

with open(ruta_geo, "r", encoding="utf-8") as f:
    geo_calles = json.load(f)



# ===============================
# CARGAR ZONAS
# ===============================

ruta_zonas = os.path.join(
    BASE_DIR,
    "zonas_ejes_para_webmap_smr",
    "zonas_11.geojson"
)

with open(ruta_zonas, "r", encoding="utf-8") as f:
    geo_zonas = json.load(f)

print("✅ Zonas cargadas:", len(geo_zonas["features"]))

# ===============================
# 🔥 PREPARAR GEOJSON (OBLIGATORIO)
# ===============================
geo_zonas_str = json.dumps(geo_zonas)
geo_calles_str = json.dumps(geo_calles)


# ===============================
# CONTROL DE SESIONES (CRÍTICO)
# ===============================

sesiones = {}             # 🔐 SID → token
usuarios_activos = {}     # 👤 IP → lista de SID activos
sids_usados = set()       # 🚫 SIDs abiertos (evita duplicar pestañas)

MAX_SESIONES = 3          # 🔒 Máximo paneles abiertos por usuario

# ===============================
# CARGAR VARIABLES
# ===============================

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
fernet = Fernet(SECRET_KEY)

# ===============================
# INICIALIZAR API
# ===============================

app = FastAPI()

#from fastapi.middleware.gzip import GZipMiddleware 

#app.add_middleware(GZipMiddleware, minimum_size=1000)

# ===============================
# FUNCION NORMALIZAR CODCOMP 🔥
# ===============================

def normalizar_cod(c):
    return str(c).strip().replace(" ", "").lstrip("0")

# =======================================================
# CONFIGURACIÓN BASE DE DATOS
# =======================================================

ORACLE_USER = os.getenv("ORACLE_USER1")
ORACLE_PASS = os.getenv("ORACLE_PASS1")
ORACLE_DSN  = os.getenv("ORACLE_DSN1")

print("Usuario Oracle:", ORACLE_USER)
print("DSN Oracle:", ORACLE_DSN)

try:
    conn = cx_Oracle.connect(ORACLE_USER, ORACLE_PASS, ORACLE_DSN)
    print("✅ Conexión Oracle exitosa")
    conn.close()
except Exception as e:
    print("❌ Error conexión Oracle:", e)



# ===============================
# FUNCIONES TOKEN
# ===============================

def desencriptar_token(token):

    try:

        datos = fernet.decrypt(token.encode())
        parametros = json.loads(datos.decode())

        return parametros

    except:
        return None


def generar_token(encuesta, usuario, correlativo=None, modalidad=None):

    datos = {
        "encuesta": encuesta,
        "usuario": usuario,
        "correlativo": correlativo,
        "modalidad": modalidad
    }

    token = fernet.encrypt(json.dumps(datos).encode())

    return token.decode()


import base64
from fastapi.responses import RedirectResponse
import uuid

@app.get("/login_panel")
def login_panel(request: Request, token: str):

    try:
        decoded = base64.b64decode(token).decode()
        parts = decoded.split("|")

        encuesta = parts[0]
        usuario = parts[1]
        correlativo = parts[2] if len(parts) > 2 else None

    except:
        return {"error": "token inválido"}

    ip = request.client.host
    clave = ip   # 🔥 CONTROL GLOBAL POR USUARIO/NAVEGADOR

    # crear registro usuario
    if clave not in usuarios_activos:
        usuarios_activos[clave] = []

    # limpiar sesiones inexistentes
    usuarios_activos[clave] = [
        s for s in usuarios_activos[clave] if s in sesiones
    ]

     
    # 🔥 LIMPIAR SESIONES ROTAS (CLAVE)
    usuarios_activos[clave] = [
        s for s in usuarios_activos[clave]
        if s in sesiones and s not in sids_usados
    ]

     
    # 🔒 límite máximo
    if len(usuarios_activos[clave]) >= 3:

        return HTMLResponse(
            f"""
            <h3>Límite de sesiones alcanzado</h3>
             YA  tiene 3 paneles abiertos.<br>
            Cierre uno antes de abrir otro.
            """
        )

    # crear nueva sesión
    token_seguro = generar_token(encuesta, usuario, correlativo)

    sid = str(uuid.uuid4())

    sesiones[sid] = token_seguro
    usuarios_activos[clave].append(sid)

    print("SID creado:", sid)
    print("Sesiones activas:", usuarios_activos)

    return RedirectResponse(url=f"/panel?sid={sid}", status_code=302)


#@app.get("/cerrar_panel")
@app.api_route("/cerrar_panel", methods=["GET", "POST"])


                
def cerrar_panel(sid: str):

                    if sid in sesiones:

                        token = sesiones.pop(sid)

                        datos = desencriptar_token(token)

                        if datos:
                            usuario = datos.get("usuario")

                            for clave in usuarios_activos:
                                if sid in usuarios_activos[clave]:
                                    usuarios_activos[clave].remove(sid)

                    # 🔥 AGREGAR ESTO (CLAVE)
                    # 🔥 limpiar si quedó colgado
                    
                    if sid in sids_usados:
                        print("⚠ SID colgado en panel, lo libero:", sid)
                        sids_usados.discard(sid)

                    sids_usados.add(sid)

    # ===============================
    # ENDPOINT PRINCIPAL PANEL
    # ===============================


@app.get("/panel", response_class=HTMLResponse)
def panel(request: Request, sid: str = Query(...)):

    coords_log_por_caso = {}

    # ===============================
    # VALIDAR SIDd
    # ===============================

    if sid not in sesiones:
        return HTMLResponse("⚠ Sesión inválida")

    # 🔒 EVITAR MISMO SID EN 2 PESTAÑAS
    if sid in sids_usados:
        return HTMLResponse("⚠ Esta sesión ya está abierta en otra pestaña")

    sids_usados.add(sid)

    # ===============================
    # DESENCRIPTAR TOKEN
    # ===============================

    token = sesiones[sid]

    datos = desencriptar_token(token)

    if not datos:
        return HTMLResponse("Token inválido")

    usuario = datos.get("usuario")
    usuario = usuario.strip().upper() if usuario else None
    clave = usuario   # 🔥 CONTROL POR USUARIO REAL

    # ===============================
    #  CONEXIÓN ORACLE 
    # ===============================
    conn = cx_Oracle.connect(ORACLE_USER, ORACLE_PASS, ORACLE_DSN)


    # 👉 YA NO USAMOS usuario+ip
    ip = request.client.host
    clave = ip   # 🔥 CONTROL GLOBAL

    encuesta = datos.get("encuesta")
    correlativo = datos.get("correlativo")
    modalidad = datos.get("modalidad")

    print("Encuesta:", encuesta)
    print("Usuario:", usuario)
    print("Correlativo:", correlativo)


    # ===============================
    # MENSAJES HTML
    # ===============================

    mensaje_error = "" 

    cursor = conn.cursor()

    cursor.arraysize = 500

    # ===============================
    # DETECTAR SCHEMA   
    # ===============================

    schema = None

    # buscar en ECH
    cursor.execute("""
        SELECT 1
        FROM ECHPROD.DOMICILIOS
        WHERE TRIM(CFGENCUESTA) = :cfg
        AND ROWNUM = 1
    """, {"cfg": encuesta})

    row = cursor.fetchone()

    if row:
        schema = "ECHPROD"
    else:
        # buscar en SMR
        cursor.execute("""
            SELECT 1
            FROM SMRPROD.DOMICILIOS
            WHERE TRIM(CFGENCUESTA) = :cfg
            AND ROWNUM = 1
        """, {"cfg": encuesta})

        row = cursor.fetchone()

        if row:
            schema = "SMRPROD"

    print("Schema detectado:", schema)


# ===============================
# TRAE CONGLOMERADOS DEL ENCUESTADOR
# ===============================

    usuario = usuario.strip().upper()

    query_cong = f"""
        SELECT 
            TO_CHAR(TO_NUMBER(DOMDEPARTAMENTO)) ||
            LPAD(TRIM(DOMSECCION),2,'0') ||
            LPAD(TRIM(DOMSEGMENTO),3,'0') ||
            LPAD(TRIM(DOMZONA),3,'0') AS CODCOMP
        FROM {schema}.DOMICILIOS
        WHERE TRIM(UPPER(DOMUSRENCUESTADOR)) = :usuario
        AND TRIM(CFGENCUESTA) = :cfg   
    """
    df_cong = pd.read_sql(
        query_cong,
        conn,
        params={
            "usuario": usuario,
            "cfg": encuesta   # 
        }
    )

    print("Usuario limpio:", usuario)
    print("Filas query_cong:", len(df_cong))
    print(df_cong.head())
  
    

    # ===============================
    # VALIDAR ENCUESTA
    # ===============================

    cursor.execute(f"""
    SELECT COUNT(*)
    FROM {schema}.DOMICILIOS
    WHERE RTRIM(CFGENCUESTA) = :encuesta
    """, {"encuesta": encuesta})
     
    row = cursor.fetchone()
    total_encuesta = row[0] if row else 0

    if total_encuesta == 0:

        mensaje_error += f"""
        <div style="
            position: fixed;
            top: 90px;
            left: 50%; 
            transform: translateX(-50%);
            background:#ffe6e6;
            padding:10px 20px;
            border:1px solid red;
            border-radius:8px;
            z-index:9999;
            font-size:14px;
            font-weight:bold;">
            ⚠ Encuesta <b>{encuesta}</b> no existe
        </div>
        """

    # ===============================
    # NOMBRE USUARIO
    # ===============================
    
    cursor.execute(f"""
        SELECT INEUSRNOMBRE
        FROM {schema}.INEUSUARIOS
        WHERE TRIM(INEUSRUSUARIO) = :usuario
    """, {"usuario": usuario})

    row_nombre = cursor.fetchone()
    nombre = row_nombre[0] if row_nombre else usuario



    # ===============================
    # CONSULTA DOMICILIOS DEL USUARIO
    # ===============================

    sql = f"""
    SELECT
        d.DOMCORRELATIVO,
        d.DOMUBICACION,
        d.DOMNOMCALLE,
        d.DOMNROPUERTA,
        d.DOMDEPARTAMENTO,
        d.DOMLOCALIDAD,
        d.DOMESTRATO,
        d.DOMMODALIDAD,      
        d.DOMESTADO,
        d.DOMCONGLOMERADO
        
    FROM {schema}.DOMICILIOS d
    WHERE TRIM(d.CFGENCUESTA) = :cfg
    AND TRIM(UPPER(d.DOMUSRENCUESTADOR)) = :usuario
    AND d.DOMUBICACION IS NOT NULL
    """

    params = {
        "cfg": encuesta,
        "usuario": usuario
    }

    # si viene correlativo agregamos filtro
    if correlativo:
        sql += " AND TRIM(d.DOMCORRELATIVO) = :correlativo"
        params["correlativo"] = correlativo

    cursor.execute(sql, params)

    rows = cursor.fetchall()

    print("Filas encontradas:", len(rows))

    # ===============================
    # VALIDAR USUARIO
    # ===============================

    if len(rows) == 0:

        mensaje_error += f"""
        <div style="
            position: fixed;
            top: 130px;
            left: 50%;
            transform: translateX(-50%);
            background:#fff3cd;
            padding:10px 20px;
            border:1px solid orange;
            border-radius:8px;
            z-index:9999;
            font-size:14px;">
            ⚠ Usuario <b>{usuario}</b> no tiene domicilios en esta encuesta
        </div>
        """
    print("Encuesta:", encuesta)
    print("Usuario:", usuario)
    print("Correlativo:", correlativo)

    df_dom = pd.DataFrame(rows, columns=[col[0] for col in cursor.description])


    
# ===============================
# 📊 CAUSALES PARA GRÁFICO 
# ===============================

    query_causales = f"""
    SELECT
        d.DOMCAUSA,
        CASE 
            WHEN d.DOMCAUSA = 1 THEN 'Realizada'
            WHEN c.CAUDESCRIPCION IS NOT NULL THEN c.CAUDESCRIPCION
            ELSE 'Causal ' || d.DOMCAUSA
        END AS DESCRIPCION,
        COUNT(*) AS CANTIDAD
    FROM {schema}.DOMICILIOS d
    LEFT JOIN {schema}.CAUSAS c 
        ON c.CAUCODIGO = d.DOMCAUSA
        AND (
            TRIM(UPPER(c.CFGENCUESTA)) = TRIM(UPPER(:encuesta))
            OR TRIM(UPPER(c.CFGENCUESTA)) = TRIM(UPPER(d.CFGENCUESTA))
        )
    WHERE TRIM(d.CFGENCUESTA) = :encuesta
    AND TRIM(UPPER(d.DOMUSRENCUESTADOR)) = :usuario
    GROUP BY 
        d.DOMCAUSA,
        CASE 
            WHEN d.DOMCAUSA = 1 THEN 'Realizada'
            WHEN c.CAUDESCRIPCION IS NOT NULL THEN c.CAUDESCRIPCION
            ELSE 'Causal ' || d.DOMCAUSA
        END
    ORDER BY CANTIDAD DESC
    """
    # 🔥 EJECUTAR QUERY (IMPORTANTE: params)
    df_causales = pd.read_sql(
        query_causales,
        conn,
        params={
            "encuesta": encuesta,
            "usuario": usuario.upper().strip()
        }
    )

    # 🔥 LIMPIAR COLUMNAS (CLAVE CON ORACLE)
    df_causales.columns = df_causales.columns.str.strip().str.upper()

    # 🔥 DEBUG (opcional)
    print("COLUMNAS CAUSALES:", df_causales.columns)

    # ===============================
    # 🔥 PREPARAR JSON PARA JS
    # ===============================

    import json

    labels = df_causales["DESCRIPCION"].tolist()
    values = df_causales["CANTIDAD"].tolist()

    causales_json = json.dumps({
        "labels": labels,
        "values": values
    })

    # ===============================
    # 🔥 EJEMPLO PARA HTML / JS
    # ===============================

    html_grafico = f"""
    <script>
    var dataCausales = {causales_json};

    console.log("Causales:", dataCausales);

    // Ejemplo básico
    var labels = dataCausales.labels;
    var values = dataCausales.values;
    </script>
    """


    # ===============================
    # CODCOMP DESDE DOMICILIOS
    # ===============================
    

    df_dom["codcomp"] = (
        df_dom["DOMCORRELATIVO"]
        .fillna("")              # 🔥 CLAVE
        .astype(str)
        .str.strip()
        .str[:10]
        .apply(normalizar_cod)
    )
    
    codigos_validos = set(
    df_cong["CODCOMP"].apply(normalizar_cod)
        )

    print("Zonas únicas:", len(codigos_validos))
    print("CODIGOS ENCUESTADOR:", list(codigos_validos)[:10])


        # ===============================
        # ZONAS POR MODALIDAD
        # ===============================

    df_presencial = df_dom[df_dom["DOMMODALIDAD"] == "P"]
    df_telefonico = df_dom[df_dom["DOMMODALIDAD"] == "T"]

    zonas_presencial = set(df_presencial["codcomp"].apply(normalizar_cod))
    zonas_telefonico = set(df_telefonico["codcomp"].apply(normalizar_cod))



    # ===============================
# FILTRAR GEOJSON (SEGURO)
# ===============================

    geo_zonas_filtrado = {
        "type": "FeatureCollection",
        "features": []
    }

    for f in geo_zonas.get("features", []):

        props = f.get("properties") or {}

        cod = props.get("codcomp") or props.get("CODCOMP") or ""
        #cod = str(cod).strip().replace(" ", "")
        cod = normalizar_cod(cod)

        # 🔥 validar codcomp
        if not cod:
            continue

        if cod not in codigos_validos:
            continue

        geom = f.get("geometry")
        if not geom:
            continue

        geo_zonas_filtrado["features"].append({
            "type": "Feature",
            "properties": {
                "codcomp": cod   # 🔥 SIEMPRE presente
            },
            "geometry": geom
        })

    print("TOTAL ZONAS FILTRADAS:", len(geo_zonas_filtrado["features"]))
    geo_zonas_str = json.dumps(geo_zonas_filtrado)


    # ===============================
    # ZONAS CARGA (LIMPIO)
    # ===============================

    #zonas_carga = (
     #   df_cong["CODCOMP"]
      #  .astype(str)
       # .str.strip()
        #.str.replace(" ", "")
        #.value_counts()
        #.to_dict()
    #)

    zonas_carga = (
        df_cong["CODCOMP"]
        .apply(normalizar_cod)
        .value_counts()
        .to_dict()
    )


    # ===============================
    # DEBUG
    # ===============================

    print("EJEMPLO MATCH:")
    for f in geo_zonas_filtrado["features"][:5]:
        cod = normalizar_cod(f.get("properties", {}).get("codcomp", ""))
        print("geo:", cod, "carga:", zonas_carga.get(cod, 0))

    print("ZONAS_CARGA:", list(zonas_carga.items())[:10])


        # ===============================
        # 🔴 CODCOMP EN DOMICILIOS PERO NO EN GEOJSON
        # ===============================

    codcomp_geojson = set(
        normalizar_cod(f.get("properties", {}).get("codcomp", ""))
        for f in geo_zonas["features"]
    )

    codcomp_domicilios = set(zonas_carga.keys())

    codcomp_sin_geo = codcomp_domicilios - codcomp_geojson

    print("🔴 CODCOMP SIN GEOJSON:", list(codcomp_sin_geo)[:20])
    print("TOTAL SIN GEOJSON:", len(codcomp_sin_geo))


    # ===============================
    # COLOR ZONAS (FUERA DEL FOR 🔥)
    # ===============================

    #def color_zona(carga):
     #   if carga == 0:
      #      return "#cccccc"
       # elif carga < 10:
        #    return "green"
        #elif carga < 30:
         #   return "orange"
        #else:
         #   return "red"
     
    def color_zona(carga):
            if carga > 0:
                return "green"   # 🔥 TODAS verdes
            else:
                return "#cccccc"  # sin datos en gris

    # ===============================
    # CORRELATIVOS
    # ===============================

    correlativos = df_dom["DOMCORRELATIVO"].unique().tolist()


    # ===============================
    # FILTRO POR CORRELATIVO
    # ===============================

    if correlativo and correlativo.upper() != "TODO":
        df_dom["DOMCORRELATIVO"] = df_dom["DOMCORRELATIVO"].astype(str).str.strip()
        correlativo = correlativo.strip()
        df_dom = df_dom[df_dom["DOMCORRELATIVO"] == correlativo]


    # ===============================
    # FILTRO POR MODALIDAD
    # ===============================

    if modalidad in ("P", "T"):
        df_dom = df_dom[df_dom["DOMMODALIDAD"] == modalidad]
   
    # ===============================
    # LOG
    # ===============================

    usuario = usuario.strip().upper()
    encuesta = encuesta.strip().upper()

    print("Encuesta:", encuesta)
    print("Usuario:", usuario)

    # -------------------------------
    # Diagnóstico: total logs usuario
    # -------------------------------
    cursor.execute(f"""
    SELECT
        DOMCORRELATIVO,
        LOGTIPO,
        LOGFECHAHORA,
        LOGACCION,
        LOGUBICACION
    FROM {schema}.LOG
    WHERE RTRIM(CFGENCUESTA) = :cfg
    AND (
            RTRIM(LOGDOMUSUARIO) = :usuario
        OR RTRIM(LOGUSRUSUARIO) = :usuario
    )
    AND LOGUBICACION IS NOT NULL
    ORDER BY LOGFECHAHORA
    """, {
        "cfg": encuesta,
        "usuario": usuario
    })

    rows_log = cursor.fetchall()

    df_log = pd.DataFrame(rows_log, columns=[col[0] for col in cursor.description])
    df_log["LOGFECHAHORA"] = pd.to_datetime(df_log["LOGFECHAHORA"], errors="coerce")
    df_log = df_log.dropna(subset=["LOGFECHAHORA"])

    print("Filas LOG:", len(df_log))

    coords_log_por_caso = {}

    if not df_log.empty:

        # limpiar strings rápido
        for col in df_log.select_dtypes(include="object"):
            df_log[col] = df_log[col].str.strip()

        # convertir fecha
        df_log["LOGFECHAHORA"] = pd.to_datetime(df_log["LOGFECHAHORA"], errors="coerce")

        df_log["DOMCORRELATIVO"] = df_log["DOMCORRELATIVO"].astype(str).str.strip()


     # ===============================
        # LIMPIAR COORDENADAS GPS
        # ===============================

        coords_log_por_caso = {}

    if not df_log.empty:

        df_log["LOGUBICACION"] = df_log["LOGUBICACION"].astype(str)

        df_log = df_log[df_log["LOGUBICACION"].str.contains(",", na=False)]

        if not df_log.empty:

            coords = df_log["LOGUBICACION"].str.split(",", expand=True)

            if coords.shape[1] >= 2:

                df_log["LAT_LOG"] = pd.to_numeric(coords[0], errors="coerce")
                df_log["LON_LOG"] = pd.to_numeric(coords[1], errors="coerce")

                df_log = df_log.dropna(subset=["LAT_LOG","LON_LOG"])

                if not df_log.empty:

                    df_log["DOMCORRELATIVO"] = df_log["DOMCORRELATIVO"].astype(str).str.strip()

                    #coords_log_por_caso = (
                     #   df_log
                      #  .groupby("DOMCORRELATIVO")[["LAT_LOG","LON_LOG"]]
                       # .apply(lambda x: x.values.tolist())
                        #.to_dict()
                    #)

                    coords_log_por_caso = (
                        df_log
                        .groupby("DOMCORRELATIVO")
                        .apply(lambda g: g.apply(lambda r: {
                            "lat": r["LAT_LOG"],
                            "lon": r["LON_LOG"],
                            "tipo": r["LOGTIPO"]
                        }, axis=1).tolist())
                        .to_dict()
                    )


            # COORDENADAS POR CASO
            # ===============================

        else:
            print("⚠️ No se encontraron logs con GPS para este usuario")




                    
        # ===============================
        # OBTENER VERSION OFICIAL METADATA
        # ===============================

    cursor.execute(f"""
            SELECT VERSIONID, VERSIONFECHA
            FROM {schema}.VERSIONES           
            WHERE CFGENCUESTA = :cfg
            AND VERSIONMETADATOS = 1
            AND VERSIONESTADO = 'A'
            ORDER BY VERSIONFECHA DESC
        """, {"cfg": encuesta})

    row_version = cursor.fetchone()

    if row_version:
            VERSION_OFICIAL = row_version[0].strip()
            FECHA_VERSION_OFICIAL = pd.to_datetime(row_version[1])
    else:
                VERSION_OFICIAL = None
                FECHA_VERSION_OFICIAL = None

        # ===============================
        # FILTRO LOG POR CORRELATIVO
        # ===============================

    if correlativo and correlativo.upper() != "TODO":
            df_log["DOMCORRELATIVO"] = df_log["DOMCORRELATIVO"].astype(str).str.strip()
            df_log = df_log[
                (df_log["DOMCORRELATIVO"] == correlativo) |
                (df_log["DOMCORRELATIVO"].isna())
            ]

    conn.close()

    # ===============================
    # FILTRO LOG SEGÚN MODALIDAD
    # ===============================

    if modalidad in ("P", "T") and not df_dom.empty:

        correlativos_validos = df_dom["DOMCORRELATIVO"].unique()

        df_log = df_log[
            (df_log["DOMCORRELATIVO"].isin(correlativos_validos)) |
            (df_log["DOMCORRELATIVO"].isna())
        ]

    # ===============================
    # VALIDACIÓN DOMICILIOS
    # ===============================

        if df_dom.empty:
            mensaje_error += """
            <div style="
                position: fixed;
                top: 120px;
                left: 50%;
                transform: translateX(-50%);
                background:#ffe6e6;
                padding:12px 20px;
                border:1px solid red;
                border-radius:8px;
                z-index:9999;
                font-size:14px;
                font-weight:bold;">
                ⚠ No hay domicilios para este usuario
            </div>
    """

     # ===============================
    # LIMPIEZA DOMICILIOS SEGURA
    # ===============================

    if df_dom.empty:
        mensaje_error = "⚠ No hay domicilios para este usuario"

    else:

        df_dom = df_dom[df_dom["DOMUBICACION"].str.contains(",", na=False)]

        if df_dom.empty:
            mensaje_error = "⚠ Los domicilios no tienen coordenadas válidas"

        else:

            coords = df_dom["DOMUBICACION"].str.split(",", expand=True)

            if coords.shape[1] == 2:

                df_dom["LAT"] = pd.to_numeric(coords[0].str.strip(), errors="coerce")
                df_dom["LON"] = pd.to_numeric(coords[1].str.strip(), errors="coerce")

                df_dom = df_dom.dropna(subset=["LAT","LON"])
                codigos_con_puntos = set(df_dom["codcomp"])


                print("ZONAS CON COORDENADAS:", len(codigos_con_puntos))

            else:
                mensaje_error = "⚠ Error en formato de coordenadas"

        # ===============================
    # 🔥 ZONAS SOLO CON COORDENADAS
    # ===============================

    df_dom["codcomp"] = (
    df_dom["DOMCONGLOMERADO"]
    .fillna("")              # 🔥 CLAVE
    .astype(str)
    .str.split("-")
    .str[0]
    .str.strip()
    .str.replace(" ", "")
)

    codigos_con_puntos = set(df_dom["codcomp"])

    print("ZONAS CON COORDENADAS:", len(codigos_con_puntos))



       # ===============================
    # MAPA VACÍO SI NO HAY DATOS
    # ===============================

    if df_dom.empty:

        mapa = folium.Map(
            location=[-34.90, -56.16],  # Montevideo
            zoom_start=6
        )


    # ===============================
    # LIMPIEZA LOG SEGURA
    # ===============================

    heat_data = []

    if not df_log.empty:

        df_log["LOGUBICACION"] = df_log["LOGUBICACION"].astype(str)

        df_log = df_log[df_log["LOGUBICACION"].str.contains(",", na=False)]

        coords = df_log["LOGUBICACION"].str.split(",", expand=True)

        if coords.shape[1] >= 2:

            df_log["LAT_LOG"] = pd.to_numeric(coords[0].str.strip(), errors="coerce")
            df_log["LON_LOG"] = pd.to_numeric(coords[1].str.strip(), errors="coerce")

            df_log = df_log.dropna(subset=["LAT_LOG","LON_LOG"])

            heat_data = df_log[["LAT_LOG","LON_LOG"]].values.tolist()

        else:
            print("⚠ LOGUBICACION con formato inválido")

        # ===============================
        # NORMALIZAR CORRELATIVOS
        # ===============================

        df_dom["DOMCORRELATIVO"] = df_dom["DOMCORRELATIVO"].astype(str).str.strip()
        df_log["DOMCORRELATIVO"] = df_log["DOMCORRELATIVO"].astype(str).str.strip()

        # ===============================
        #  AGRUPAR LOG POR HOGAR
        # ===============================

        log_por_hogar = {
            k: v.sort_values("LOGFECHAHORA")
            for k, v in df_log.groupby("DOMCORRELATIVO") 
        }
     
        # ===============================
        # ÚLTIMA VERSION ENVIADA POR HOGAR
        # ===============================

    df_env = df_log[df_log["LOGTIPO"] == "ENV"].copy()

    df_env["VERSION_METADATA"] = df_env["LOGACCION"].str.extract(r"\((.*?)\)")
    df_env = df_env.sort_values("LOGFECHAHORA")

    ultimo_env_por_hogar = (
        df_env
        .dropna(subset=["VERSION_METADATA"])
        .groupby("DOMCORRELATIVO")
        .last()
    )

        # ===============================
        #  AGRUPAR LOG POR HOGAR
        # ===============================

    log_por_hogar = {
        k: v.sort_values("LOGFECHAHORA")
        for k, v in df_log.groupby("DOMCORRELATIVO")
    }

        # ===============================
        #  DETECTAR VERSIONES USADAS EN LOG
        # ===============================

    df_env = df_log[df_log["LOGTIPO"] == "ENV"].copy()

    # Extraer versión entre paréntesis
    df_env["VERSION_METADATA"] = df_env["LOGACCION"].str.extract(r"\((.*?)\)")

    # Obtener última versión usada por cada domicilio
    version_por_hogar = (
        df_env
        .dropna(subset=["VERSION_METADATA"])
        .sort_values("LOGFECHAHORA")
        .groupby("DOMCORRELATIVO")["VERSION_METADATA"]
        .last()
        .to_dict()
    )


    # ===============================
    # MÉTRICAS DE ACTIVIDAD
    # ===============================

    from datetime import datetime, timedelta

    ahora = datetime.now()
    hoy = ahora.date()
    hace_7_dias = ahora - timedelta(days=7)

    # Actividad últimos 7 días
    actividad_7_dias = df_log[df_log["LOGFECHAHORA"] >= hace_7_dias]

    total_eventos_7_dias = len(actividad_7_dias)
    hogares_7_dias = actividad_7_dias["DOMCORRELATIVO"].nunique()

    # Hogares trabajados hoy
    actividad_hoy = df_log[
        df_log["LOGFECHAHORA"].dt.date == hoy
    ]

    hogares_hoy = actividad_hoy["DOMCORRELATIVO"].nunique()
    eventos_hoy = len(actividad_hoy)

    # ===============================
    # CONTADORES
    # ===============================

    cant_presenciales = len(df_dom[df_dom["DOMMODALIDAD"] == "P"])
    cant_telefonicos = len(df_dom[df_dom["DOMMODALIDAD"] == "T"])
    total = len(df_dom)
        
    cant_presenciales = len(df_dom[df_dom["DOMMODALIDAD"] == "P"])
    cant_telefonicos = len(df_dom[df_dom["DOMMODALIDAD"] == "T"])
    total = len(df_dom)

    # ===============================
    # DICCIONARIO DE ESTADOS
    # ===============================

    nombres_estados = {
        "SA": "Sin Asignar",
        "DI": "Para Distribuir",
        "AE": "Asignada a Encuestador/a",
        "PU": "Publicada",
        "DE": "Descargada",
        "NO": "Notificada",
        "PE": "Pendiente",
        "IN": "Incompleta",
        "CR": "Criticada",
        "PD": "Para Devolver",
        "EC": "Enviada",
        "ED": "Devuelta",
        "RE": "Recibida",
        "RD": "Recibida Devuelta",
        "SU": "Para supervisar",
        "PC": "Para codificar",
        "PT": "Para criticar",
        "CP": "En crítica (Pendiente)",
        "CN": "En crítica (Consulta)",
        "CO": "Criticada Oficina",
        "AA": "Archivada con Alertas",
        "AT": "Archivada Crítica",
        "NA": "No Aceptada / Descartada",
        "JU": "En Jurídica"
    }

    # ===============================
    # DESGLOSE POR ESTADO
    # ===============================

    conteo_estados = df_dom["DOMESTADO"].value_counts()

    estados_html = " | ".join(
        [
            f"{estado} - {nombres_estados.get(estado, 'Desconocido')}: {cantidad}"
            for estado, cantidad in conteo_estados.items()
        ]
    )

    # ===============================
    # HEATMAP POR MODALIDAD
    # ===============================

    heat_presencial = []
    heat_telefonico = []

    if not df_log.empty:

        df_log_modal = df_log.merge(
            df_dom[["DOMCORRELATIVO", "DOMMODALIDAD"]],
            on="DOMCORRELATIVO",
            how="left"
        )

        heat_presencial = df_log_modal[
            df_log_modal["DOMMODALIDAD"] == "P"
        ][["LAT_LOG","LON_LOG"]].values.tolist()

        heat_telefonico = df_log_modal[
            df_log_modal["DOMMODALIDAD"] == "T"
        ][["LAT_LOG","LON_LOG"]].values.tolist()


    # ===============================
    # CENTRO DEL MAPA SEGURO
    # ===============================

    if df_dom.empty or "LAT" not in df_dom.columns or df_dom["LAT"].isna().all():
        centro = [-34.9011, -56.1645]
    else:
        centro = [df_dom["LAT"].mean(), df_dom["LON"].mean()]

    mapa = folium.Map(
    location=centro,
    zoom_start=10,
    tiles="OpenStreetMap",
    control_scale=True
)

    # ===============================
    # 🛣️ CAPA CALLES PRO
    # ===============================

    fg_calles = folium.FeatureGroup(
        name="🛣️ Ejes IDE",
        show=False
    )

    folium.GeoJson(
        geo_calles,
        style_function=lambda f: {
            "color": "#4a90e2",
            "weight": 2.5,
            "opacity": 0.7
        },
        highlight_function=lambda f: {
            "color": "#00ffff",
            "weight": 6,
            "opacity": 1

        },
        tooltip=folium.GeoJsonTooltip(
            fields=["nombre"],  # o "NOMBRE"
            aliases=["Calle IDE:"],
            sticky=True
        )
    ).add_to(fg_calles)

    fg_calles.add_to(mapa)


    mapa.get_root().html.add_child(folium.Element("""
    <script>

    map.on('zoomend', function() {

        let zoom = map.getZoom();

        document.querySelectorAll('.leaflet-marker-icon').forEach(el => {

            if (zoom < 15){
                el.style.display = "none";
            } else {
                el.style.display = "block";
            }

        });

    });

    </script>
    """))






    # ===============================
    # CONTROLES TIPO GIS
    # ===============================
    from folium.plugins import Fullscreen, MeasureControl, Draw, MousePosition

    # 🔲 Pantalla completa
    Fullscreen(position="topleft").add_to(mapa)

    # 📏 Medir distancia
    MeasureControl(
        position="topleft",
        primary_length_unit="kilometers"
    ).add_to(mapa)

    # ✏️ Dibujar zonas
    Draw(position="topleft").add_to(mapa)

    # 📍 Coordenadas del mouse (abajo)
    MousePosition(position="bottomleft").add_to(mapa)

    # ===============================
    # 🧭 BRÚJULA
    # ===============================
    from folium.plugins import FloatImage
    from folium.plugins import Geocoder

    Geocoder(
        position="topleft",
        collapsed=True,
        add_marker=True,
        placeholder="Buscar dirección...",
    ).add_to(mapa)

        

    
    from folium.plugins import MiniMap

    MiniMap(
        position="bottomleft",
        toggle_display=True,
        minimized=False
    ).add_to(mapa)


    # ===============================
    # CAPAS EXTRA
    # ===============================

    # 🏙️ Mapa Claro
    folium.TileLayer(
        "CartoDB positron",
        name="🏙️ Mapa Claro",
        overlay=False,
        show=False,
        control=True
    ).add_to(mapa)

    # 🌙 Modo Oscuro
    folium.TileLayer(
        "CartoDB dark_matter",
        name="🌙 Modo Oscuro",
        overlay=False,
        show=False,
        control=True
    ).add_to(mapa)

    # 🛰️ Satélite
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="🛰️ Satélite",
        overlay=False,
        control=True,
        show=False
         
    ).add_to(mapa)


    folium.TileLayer(
        tiles="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Labels",
        name="🛰️🌍 Etiquetas",
        overlay=True,   # 🔥 CAMBIAR ESTO
        control=True,
        show=False      # 🔥 OPCIONAL: no cargar por defecto
    ).add_to(mapa)

  

    # ===============================
    # 🗺️ TODAS LAS ZONAS (ROJO = SIN DATOS)
    # ===============================

    #fg_zonas_total = folium.FeatureGroup(
     #   name="🗺️ Todas las zonas",
      #  show=False
    #)

    def estilo_zonas_total(f):
        cod = str(f.get("properties", {}).get("codcomp", "")).strip().replace(" ", "")

        # 🔴 zona SIN domicilios
        if cod not in codcomp_domicilios:
            return {
                "fillColor": "red",
                "color": "red",
                "weight": 2,
                "fillOpacity": 0.6,
            }

        # 🟣 zona normal
        return {
            "fillColor": "#6D0F75",
            "color": "#2E003E",
            "weight": 1,
            "fillOpacity": 0.2,
        }

    #folium.GeoJson(
     #   geo_zonas,
      #  style_function=estilo_zonas_total
    #).add_to(fg_zonas_total)


    #fg_zonas_total.add_to(mapa)
    folium.GeoJson(geo_zonas_filtrado)

    # ===============================
    # 🟢 ZONAS DEL ENCUESTADOR (FIX FINAL)
    # ===============================
        
    print("TOTAL GEO ORIGINAL:", len(geo_zonas["features"]))
    print("TOTAL GEO FILTRADO:", len(geo_zonas_filtrado["features"]))

    # 🔥 LIMPIAR FEATURES INVALIDAS
    features_limpias = [
        f for f in geo_zonas_filtrado["features"]
        if f.get("properties") 
        and f["properties"].get("codcomp")
    ]

    print("TOTAL ZONAS LIMPIAS:", len(features_limpias))

    geo_final = {
        "type": "FeatureCollection",
        "features": features_limpias
    }

    # ===============================
    # 🔥 CAPAS POR MODALIDAD
    # ===============================

    fg_zonas_presencial = folium.FeatureGroup(
        name="🟢 Zonas Presencial",
        show=False
    )

    fg_zonas_telefonico = folium.FeatureGroup(
        name="🔵 Zonas Telefónica",
        show=False
    )

    # 🔥 SOLO SI HAY DATOS
    if geo_final["features"]:

        # 🟢 PRESENCIAL
        folium.GeoJson(
            geo_final,
            style_function=lambda f: {
                "fillColor": "green" if normalizar_cod(f["properties"]["codcomp"]) in zonas_presencial else "#cccccc",
                "color": "black",
                "weight": 1,
                "fillOpacity": 0.6,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["codcomp"],
                aliases=["Zona codcomp:"]
            )
        ).add_to(fg_zonas_presencial)

        # 🔵 TELEFÓNICO
        folium.GeoJson(
            geo_final,
            style_function=lambda f: {
                "fillColor": "blue" if normalizar_cod(f["properties"]["codcomp"]) in zonas_telefonico else "#cccccc",
                "color": "black",
                "weight": 1,
                "fillOpacity": 0.6,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["codcomp"],
                aliases=["Zona codcomp:"]
            )
        ).add_to(fg_zonas_telefonico)

    else:
        print("⚠️ No hay zonas válidas para mostrar")

    # 🔥 AGREGAR AL MAPA
    fg_zonas_presencial.add_to(mapa)
    fg_zonas_telefonico.add_to(mapa)


    # ===============================
    # 🔥 CONTROL DE CAPAS (JS)
    # ===============================
    mapa.get_root().html.add_child(folium.Element("""
    <script>

    function controlarCapasCriticas() {

        let labels = document.querySelectorAll('.leaflet-control-layers-overlays label');

        labels.forEach(label => {
            let input = label.querySelector('input');

            if (!input) return;

            input.onchange = function() {

                let capas = [];

                document.querySelectorAll('.leaflet-control-layers-overlays label').forEach(l => {
                    let txt = l.innerText.trim();
                    let inp = l.querySelector('input');

                    capas.push({nombre: txt, input: inp});
                });

                let todasZonas = capas.find(c => c.nombre.includes("Todas las zonas"));
                let ejes = capas.find(c => c.nombre.includes("Ejes"));

                let texto = label.innerText.trim();

                // 🔥 ACTIVAR TODAS LAS ZONAS
                if (texto.includes("Todas las zonas") && this.checked) {

                    if (ejes && ejes.input.checked) {
                        ejes.input.click();
                    }

                    if (ejes) {
                        ejes.input.disabled = true;
                    }
                }

                // 🔥 DESACTIVAR TODAS LAS ZONAS
                if (texto.includes("Todas las zonas") && !this.checked) {

                    if (ejes) {
                        ejes.input.disabled = false;
                    }
                }

                // 🔥 ACTIVAR EJES
                if (texto.includes("Ejes") && this.checked) {

                    if (todasZonas && todasZonas.input.checked) {
                        todasZonas.input.click();
                    }

                    if (todasZonas) {
                        todasZonas.input.disabled = true;
                    }
                }

                // 🔥 DESACTIVAR EJES
                if (texto.includes("Ejes") && !this.checked) {

                    if (todasZonas) {
                        todasZonas.input.disabled = false;
                    }
                }

            };
        });
    }

    // esperar carga leaflet
    setTimeout(function(){
        controlarCapasCriticas();
    }, 1500);

    </script>
    """))
    
    # ===============================
    # HEATMAP SOLO DEL CASO BUSCADO
    # ===============================

    print("DEBUG correlativo:", correlativo)
    print("DEBUG df_log vacío:", df_log.empty)
    print("DEBUG total logs:", len(df_log))       
    heat_caso = []

    if correlativo and not df_log.empty:

        correlativo = str(correlativo).strip()

        df_log["DOMCORRELATIVO"] = df_log["DOMCORRELATIVO"].astype(str).str.strip()

        df_caso = df_log[
            df_log["DOMCORRELATIVO"] == correlativo
        ]

        print("🔥 puntos GPS del caso:", len(df_caso))

        if not df_caso.empty:

            heat_caso = df_caso[["LAT_LOG","LON_LOG"]].values.tolist()
            print("🔥 heat_caso:", len(heat_caso)) 


    # ===============================
    # HEATMAP SEPARADO
    # ===============================

    fg_heat_presencial = folium.FeatureGroup(
    name="🔥 Mapa Calor Presenciales",
    show=True
    )
    fg_heat_presencial._name = "heat_presencial"


    fg_heat_telefonico = folium.FeatureGroup(
    name="🔥 Mapa Calor Telefónicas",
    show=True
    )
    fg_heat_telefonico._name = "heat_telefonico"


    fg_heat_caso = folium.FeatureGroup(
        name="🎯 Mapa Calor del Caso",
        show=False
    )
    fg_heat_caso._name = "heat_caso"



    if heat_presencial:
        HeatMap(
            heat_presencial,
            radius=18,
            blur=25,
            min_opacity=0.3
        ).add_to(fg_heat_presencial)

    if heat_telefonico:
        HeatMap(
            heat_telefonico,
            radius=18,
            blur=25,
            min_opacity=0.3
        ).add_to(fg_heat_telefonico)


    if heat_caso:

        # 🔥 mapa de calor
        HeatMap(
                    heat_caso,
                    radius=90,
                    blur=45,
                    min_opacity=0.6,
                    max_zoom=17,
                    gradient={
                        0.2: 'blue',
                        0.4: 'lime',
                        0.6: 'yellow',
                        0.8: 'orange',
                        1: 'red'
                    }
                ).add_to(fg_heat_caso)

            # 📍 puntos GPS reales del encuestador
        #for lat, lon in heat_caso:
         #       folium.CircleMarker(
          #          location=[lat, lon],
           #         radius=4,
            #        color="yellow", 
             #       fill=True,
              #      fill_color="yellow",
               #     fill_opacity=0.9
                #).add_to(fg_heat_caso)


    fg_heat_presencial.add_to(mapa)
    fg_heat_telefonico.add_to(mapa)
    fg_heat_caso.add_to(mapa)
    
    # ===============================
    # CAPAS POR MODALIDAD
    # ===============================

    fg_presencial = folium.FeatureGroup(
        name=f"🏠 Presenciales ({cant_presenciales})",
        show=not correlativo
    )

    fg_telefonico = folium.FeatureGroup(
        name=f"📱 Telefónicas ({cant_telefonicos})",
        show=not correlativo
    )

    cluster_presencial = MarkerCluster(
        spiderfyOnMaxZoom=True,
        showCoverageOnHover=False,
        zoomToBoundsOnClick=True,
        maxClusterRadius=40,
        spiderfyDistanceMultiplier=2.5
    ).add_to(fg_presencial)

    cluster_telefonico = MarkerCluster(
        spiderfyOnMaxZoom=True,
        showCoverageOnHover=False,
        zoomToBoundsOnClick=True,
        maxClusterRadius=40,
        spiderfyDistanceMultiplier=2.5
    ).add_to(fg_telefonico)

    # ===============================
    # PREPARACIÓN
    # ===============================

    import math
    from collections import defaultdict

    coords_por_hogar = {}
    desactualizados = []

    # ===============================
    # AGRUPAR POR COORDENADAS
    # ===============================

    grupos = defaultdict(list)

    for _, row in df_dom.iterrows():
        key = (row["LAT"], row["LON"])
        grupos[key].append(row)

    # ===============================
    # RECORRER GRUPOS
    # ===============================

    for key, lista in grupos.items():

        for i, row in enumerate(lista):

            estado = row["DOMESTADO"]
            hogar = str(row["DOMCORRELATIVO"])

            modalidad = "Presencial" if row["DOMMODALIDAD"] == "P" else "Telefónica"

            if modalidad == "Presencial":
                color = "green"
                emoji = "🏠"
                destino = cluster_presencial
            else:
                color = "blue"
                emoji = "☎️"
                destino = cluster_telefonico

            # ===============================
            # VERSIONES
            # ===============================
            registro_env = (
                ultimo_env_por_hogar.loc[hogar]
                if hogar in ultimo_env_por_hogar.index
                else None
            )

            version_usada = None
            fecha_envio = None

            if registro_env is not None:
                version_usada = registro_env["VERSION_METADATA"]
                fecha_envio = registro_env["LOGFECHAHORA"]

            version_correcta = True

            if (
                VERSION_OFICIAL
                and FECHA_VERSION_OFICIAL is not None
                and version_usada
                and fecha_envio is not None
            ):
                version_limpia = version_usada.split("-")[-1].strip()

                if (
                    fecha_envio > FECHA_VERSION_OFICIAL
                    and version_limpia != VERSION_OFICIAL.strip()
                ):
                    version_correcta = False

            if not version_correcta:
                desactualizados.append({
                    "hogar": hogar,
                    "usada": version_usada,
                    "oficial": VERSION_OFICIAL
                })

            # ===============================
            # HISTORIAL
            # ===============================
            eventos = log_por_hogar.get(hogar)

            historial = """
            <details>
                <summary><b>📜 Historial</b></summary>
                <div style="
                    max-height:180px;
                    overflow-y:auto;
                    margin-top:6px;
                    padding:6px;
                    border:1px solid #ddd;
                    border-radius:6px;
                    background:#f8f9fa;
                    font-size:12px;
                ">
            """

            if eventos is not None and not eventos.empty:
                for _, ev in eventos.iterrows():
                    historial += f"{ev['LOGFECHAHORA']} - {ev['LOGTIPO']} - {ev['LOGACCION']}<br>"
            else:
                historial += "Sin registros"

            historial += "</div></details>"

            # ===============================
            # SEPARACIÓN SI DUPLICADOS
            # ===============================
            if len(lista) > 1:
                angle = (i * 30) % 360
                radius = 0.00005
            else:
                angle = 0
                radius = 0

            lat = row["LAT"] + radius * math.cos(math.radians(angle))
            lon = row["LON"] + radius * math.sin(math.radians(angle))

            coords_por_hogar[hogar] = {
                "lat": row["LAT"],
                "lon": row["LON"]
            }

            # ===============================
            # POPUP COMPLETO
            # ===============================
            popup_html = f"""
            <div style="font-size:13px; width:340px">
                <b>🏠 Domicilio:</b> {hogar}<br>
                <b>📍 Dirección:</b> {row['DOMNOMCALLE']} {row['DOMNROPUERTA']}<br>
                <b>🗺️ Departamento:</b> {row['DOMDEPARTAMENTO']}<br>
                <b>🏙️ Localidad:</b> {row['DOMLOCALIDAD']}<br> 
                <b>🏷️ Estrato:</b> {row['DOMESTRATO']}<br>
                <b>📌 Modalidad:</b> {modalidad}<br>
                <b>📊 Estado:</b> {estado}<br>
                <b>🧩 Metadata:</b> {version_usada if version_usada else 'Sin registro'}<br>
                <b>📌 Oficial:</b> {VERSION_OFICIAL if VERSION_OFICIAL else 'No definida'}<br>
                {'<span style="color:red;font-weight:bold;">⚠ Versión desactualizada</span><br>' if not version_correcta else ''}
                <hr>
                {historial}
            </div>
            """

            # ===============================
            # MARKER (UNO SOLO)
            # ===============================
            folium.Marker(
                location=[lat, lon],
                popup=popup_html,
                tooltip=f"{modalidad} - {hogar}",
                icon=folium.DivIcon(html=f"""
                    <div class="marker-estado marker-estado-{estado}">
                        <span>{emoji}</span>
                        <span style="
                            font-size:10px;
                            font-weight:bold;
                            color:#fff;
                            background:{color};
                            padding:3px 8px;
                            border-radius:8px;">
                            {hogar}
                        </span>
                    </div>
                """)
            ).add_to(destino)
            # ===============================
            # 🔥 GUARDAR MARCADORES PARA JS
            # ===============================
            script_marker = f"""
            if (!window.marcadoresCluster) {{
                window.marcadoresCluster = [];
            }}

            window.marcadoresCluster.push({{
                correlativo: "{hogar}",
                lat: {lat},
                lon: {lon}
            }});
            """

            mapa.get_root().html.add_child(
                folium.Element(f"<script>{script_marker}</script>")
            )
                    
                
        
        
    # ===============================
    # AGREGAR CAPAS AL MAPA (FUERA DEL FOR)
    # ===============================

    fg_presencial.add_to(mapa)
    fg_telefonico.add_to(mapa)

    folium.LayerControl(
        position="topright",
        collapsed=False
    ).add_to(mapa)
    
    # ===============================
    # TITULO SUPERIOR
    # ===============================

    titulo_html = f"""
            <h3 style="text-align:center; margin-top:10px;">
            📍 Panel Territorial — {usuario} - {nombre}<br>
            🏠 Presenciales: {cant_presenciales} |
            ☎️ Telefónicas: {cant_telefonicos} |
            📊 Total: {total}
            <br>
            </h3>
    """

    mapa.get_root().html.add_child(folium.Element(f"""
    <div style="
        position: fixed;
        top: 10px;
        left: 50%;
        transform: translateX(-50%);
        background: white;
        padding: 12px 25px;
        border-radius: 10px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 9999;
        text-align:center;
        font-size:14px;
    ">
        📍 <b>Panel Territorial — {usuario} - {nombre}</b><br>
        🏠 Presenciales: <b>{cant_presenciales}</b> |
        ☎️ Telefónicas: <b>{cant_telefonicos}</b> |
        📊 Total: <b>{total}</b>
    </div>
    """))

    mapa.get_root().html.add_child(folium.Element("""
    <style>

    .leaflet-container {
        margin-bottom: 90px;
    }

    /*  FILA ACTIVA */
   .estado-activo {
    background: linear-gradient(135deg,#ffc107,#ffca2c) !important;
    color: black !important;
    font-weight: bold;
    }

    /* Texto blanco dentro de la fila */
    .estado-activo td {
        color: white !important;
    }

    /* Hover suave */
    #panelEstados tbody tr {
        cursor: pointer;
        transition: all 0.2s ease;
    }

    #panelEstados tbody tr:hover {
        background: #e9ecef;
    }

    </style>
"""))


    # ===============================
    # BUSCADOR MOVIBLE (SIN F-STRING)
    # ===============================

    coords_json = json.dumps(coords_por_hogar)
    logs_json = json.dumps(coords_log_por_caso)
    mostrar_buscador = not correlativo
    map_name = mapa.get_name()

    buscador_html = """
    <div id="buscadorMovible" style="
        display: """ + ("flex" if mostrar_buscador else "none") + """;
        position: fixed;
        bottom: 500px;
        right: 20px;
        z-index:9999;
        align-items:center;
        gap:10px;
    ">

        <div style="
            display:flex;
            align-items:center;
            gap:6px;
            background:white;
            padding:10px;
            border-radius:12px;
            box-shadow:0 4px 12px rgba(0,0,0,0.3);
        ">

            <input id="buscarHogar" type="text"
                placeholder="Buscar correlativo..."
                style="
                    padding:6px;
                    width:220px;
                    border:1px solid #ccc;
                    border-radius:6px;
                    outline:none;
            ">

            <button onclick="buscarHogar()" style="
                padding:6px 12px;
                border:none;
                background:#0d6efd;
                color:white;
                border-radius:6px;
                cursor:pointer;">
                Buscar
            </button>

        </div>
    </div>

    <script>

    var hogares = """ + coords_json + """;
    var logsCasos = """ + logs_json + """;

    var circuloBusqueda = null;
    var heatCaso = null;

        function buscarHogar() {

        var input = document.getElementById("buscarHogar");
        var valor = input.value.trim();
        valor = valor.replace(/\s+/g, "");

        var mapa = Object.values(window).find(obj => obj instanceof L.Map);

        if (!mapa) {
            alert("Mapa no cargado aún");
            return;
        }

        // ===============================
        // LIMPIAR BUSQUEDA
        // ===============================
        if (valor === "") {

            if (circuloBusqueda) {
                mapa.removeLayer(circuloBusqueda);
                circuloBusqueda = null;
            }

            if (heatCaso) {
                mapa.removeLayer(heatCaso);
                heatCaso = null;
            }

            return;
        }

        // ===============================
        // BUSCAR CORRELATIVO
        // ===============================
        if (hogares[valor]) {

            var lat = hogares[valor].lat;
            var lon = hogares[valor].lon;

            mapa.setView([lat, lon], 18);

            // ===============================
            // 🔥 RESALTAR + ABRIR CLUSTER
            // ===============================
            mapa.eachLayer(function(layer) {

                if (layer instanceof L.MarkerClusterGroup) {

                    let target = null;

                    layer.getLayers().forEach(function(m) {

                        let el = m.getElement();
                        if (!el) return;

                        let texto = el.innerText || "";

                        // 🔥 BUSCAR POR CORRELATIVO
                        if (texto.includes(valor)) {

                            target = m;

                            el.style.opacity = "1";
                            el.style.transform = "scale(1.5)";
                            el.style.zIndex = 9999;

                        } else {

                            el.style.opacity = "0.2";
                            el.style.transform = "scale(1)";
                        }

                    });

                    // 🔥 ABRIR CLUSTER + DIBUJAR CÍRCULO BIEN
                    if (target) {
                        layer.zoomToShowLayer(target, function() {

                            target.openPopup();

                            let ll = target.getLatLng();

                            // 🔥 BORRAR CÍRCULO ANTERIOR
                            if (circuloBusqueda) {
                                mapa.removeLayer(circuloBusqueda);
                            }

                            // 🔥 CREAR CÍRCULO BIEN POSICIONADO
                            circuloBusqueda = L.circleMarker([ll.lat, ll.lng], {
                                radius: 18,
                                color: "red",
                                fillColor: "yellow",
                                fillOpacity: 0.9
                            }).addTo(mapa);

                            // 🔥 PARPADEO
                            let visible = true;

                            let intervalo = setInterval(() => {

                                if (visible) {
                                    mapa.removeLayer(circuloBusqueda);
                                } else {
                                    circuloBusqueda.addTo(mapa);
                                }

                                visible = !visible;

                            }, 400);

                            setTimeout(() => {
                                clearInterval(intervalo);
                                circuloBusqueda.addTo(mapa);
                            }, 5000);

                        });
                    }
                }

            });

            console.log("correlativo:", valor);
            console.log("logs:", logsCasos[valor]);

            // ===============================
            // LIMPIAR HEATMAP
            // ===============================
            if (heatCaso) {
                mapa.removeLayer(heatCaso);
                heatCaso = null;
            }

        } else {

            alert("Correlativo no encontrado");
        }
    }
    // ===============================
    // EVENTOS
    // ===============================

    document.addEventListener("DOMContentLoaded", function() {

        var input = document.getElementById("buscarHogar");

        if (input) {
            input.addEventListener("keypress", function(e) {
                if (e.key === "Enter") {
                    buscarHogar();
                }
            });
        }

        var dragElement = document.getElementById("buscadorMovible");

        var offsetX = 0;
        var offsetY = 0;
        var isDragging = false;

        dragElement.addEventListener("mousedown", function(e) {

            if (e.target.tagName === "INPUT" || e.target.tagName === "BUTTON") {
                return;
            }

            isDragging = true;
            offsetX = e.clientX - dragElement.offsetLeft;
            offsetY = e.clientY - dragElement.offsetTop;
        });

        document.addEventListener("mousemove", function(e) {
            if (isDragging) {
                dragElement.style.left = (e.clientX - offsetX) + "px";
                dragElement.style.top = (e.clientY - offsetY) + "px";
                dragElement.style.right = "auto";
            }
        });

        document.addEventListener("mouseup", function() {
            isDragging = false;
        });

    });

    // ===============================
    // ACTIVAR HEATMAP CON CAPA 🔥
    // ===============================

    document.addEventListener("DOMContentLoaded", function() {

        var mapa = Object.values(window).find(obj => obj instanceof L.Map);

        if (!mapa) return;

        mapa.on('overlayadd', function(e) {

            console.log("Capa activada:", e.name);

            if (e.name === "🎯 Mapa Calor del Caso") {

                var input = document.getElementById("buscarHogar");
                var valor = input.value.trim();
                valor = valor.replace(/\s+/g, "");

                if (!valor) return;

                // limpiar anterior
                if (heatCaso) {
                    mapa.removeLayer(heatCaso);
                    heatCaso = null;
                }

                // 🔥 USAR logsCasos 
                if (logsCasos[valor] && logsCasos[valor].length > 0) {

                    var puntos = [];

                    for (var i = 0; i < logsCasos[valor].length; i++) {
                        var p = logsCasos[valor][i];

                        if (p.lat != null && p.lon != null) {
                            puntos.push([p.lat, p.lon]);
                        }
                    }

                    if (puntos.length > 0) {

                        heatCaso = L.heatLayer(puntos, {
                            radius: 12,
                            blur: 8,
                            maxZoom: 18,
                            minOpacity: 0.5,
                            gradient: {
                                0.2: 'blue',
                                0.4: 'lime',
                                0.6: 'yellow',
                                0.8: 'orange',
                                1.0: 'red'
                            }
                        }).addTo(mapa);

                        // ===============================
                  
                
                    }
                }
            }
        });

        mapa.on('overlayremove', function(e) {

            if (e.name === "🎯 Mapa Calor del Caso") {

                if (heatCaso) {
                    mapa.removeLayer(heatCaso);
                    heatCaso = null;
                }
            }
        });

    });

    </script>
    """

    mapa.get_root().html.add_child(folium.Element(buscador_html))

# ===============================
# PANEL ESTADOS + ACTIVIDAD
# ===============================

    conteo_estados = df_dom["DOMESTADO"].value_counts()

    filas_estados = ""
    panel_html = ""

    for estado, cantidad in conteo_estados.items():

        nombre = nombres_estados.get(estado, "Desconocido")
        porcentaje = round((cantidad / total) * 100, 1)

        filas_estados += f"""
        <tr>
            <td style='padding:6px; cursor:pointer; color:#0d6efd; font-weight:bold;'
                onclick="filtrarEstado('{estado}')">
                {estado}
            </td>
            <td style='padding:6px;'>{nombre}</td>
            <td style='padding:6px; text-align:center; font-weight:bold;'>{cantidad}</td>
            <td style='padding:6px; text-align:center;'>{porcentaje}%</td>
        </tr>
        """

        panel_html = f"""
    <div style="
        position: fixed;
        bottom: 110px;
        right: 20px;
        z-index: 9999;
        display:flex;
        gap:8px;
    ">
        <button onclick="toggleCausales()" style="
            padding:8px 14px;
            background:#6f42c1;
            color:white;
            border:none;
            border-radius:8px;
            cursor:pointer;">
            📊 Causales
        </button>    
    

        <button onclick="toggleEstados()" style="
            padding:8px 14px;
            background:#0d6efd;
            color:white;
            border:none;
            border-radius:8px;
            cursor:pointer;">
            📊 Estados
        </button>

        <button onclick="toggleActividad()" style="
            padding:8px 14px;
            background:#198754;
            color:white;
            border:none;
            border-radius:8px;
            cursor:pointer;">
            📈 Actividad
        </button>

        <button onclick="toggleMetadata()" style="
            padding:8px 14px;
            background:#dc3545;
            color:white;
            border:none;
            border-radius:8px;
            cursor:pointer;">
            🧩 Metadata
        </button>

    </div>

    <!-- PANEL ESTADOS -->
    <div id="panelEstados" style="
        display:block;
        position: fixed;
        bottom: 160px;
        right: 20px;
        background:white;
        padding:15px;
        border-radius:10px;
        box-shadow:0 4px 12px rgba(0,0,0,0.3);
        max-height:300px;
        overflow-y:auto;
        min-width:420px;
        z-index:9999;">
        
        <div style="font-weight:bold; margin-bottom:8px; text-align:center;">
            📊 Desglose por Estado
        </div>

        <table style="border-collapse: collapse; font-size:13px; width:100%;">
            <thead>
                <tr style="background:#0d6efd; color:white;">
                    <th style='padding:6px;'>Código</th>
                    <th style='padding:6px;'>Estado</th>
                    <th style='padding:6px;'>Cantidad</th>
                    <th style='padding:6px;'>%</th>
                </tr>
            </thead>
            <tbody>
                {filas_estados}
            </tbody>
        </table>
    </div>
    
        <!-- PANEL CAUSALES -->
        <div id="panelCausales" style="
            display:none;
            position: fixed;
            bottom: 160px;
            right: 20px;
            background:white;
            padding:15px;
            border-radius:10px;
            box-shadow:0 4px 12px rgba(0,0,0,0.3);

            width:900px;              /* 🔥 MÁS ANCHO */
            height:500px;             /* 🔥 MÁS ALTO */

            max-height:80vh;          /* 🔥 adaptable pantalla */
            overflow:auto;            /* 🔥 SCROLL en vez de cortar */

            z-index:9999;
        ">

        <div style="font-weight:bold; margin-bottom:10px; text-align:center;">
            📊 Desglose por Causales
        </div>

        <div style="width:100%; overflow-x:auto;">
    <canvas id="graficoCausales" style="min-width:1200px; height:400px;"></canvas>
        </div>

    </div>


     
    <!-- PANEL ACTIVIDAD -->
    <div id="panelActividad" style="
        display:none;
        position: fixed;
        bottom: 160px;
        right: 20px;
        background:white;
        padding:15px;
        border-radius:10px;
        box-shadow:0 4px 12px rgba(0,0,0,0.3);
        min-width:260px;
        z-index:9999;">
        
        <div style="font-weight:bold; margin-bottom:10px; text-align:center;">
            📈 Actividad Reciente
        </div>

        📅 Últimos 7 días:<br>
        • Eventos: <b>{total_eventos_7_dias}</b><br>
        • Hogares: <b>{hogares_7_dias}</b>

        <hr style="margin:8px 0;">

        📍 Hoy:<br>
        • Eventos: <b>{eventos_hoy}</b><br>
        • Hogares: <b>{hogares_hoy}</b>
    </div>

    <!-- PANEL METADATA -->
    <div id="panelMetadata" style="
        display:none;
        position: fixed;
        bottom: 160px;
        right: 20px;
        background:white;
        padding:15px;
        border-radius:10px;
        box-shadow:0 4px 12px rgba(0,0,0,0.3);
        max-height:300px;
        overflow-y:auto;
        min-width:420px;
        z-index:9999;">

        <div style="font-weight:bold; margin-bottom:10px; text-align:center;">
            🧩 Versiones Desactualizadas ({len(desactualizados)})
        </div>

        {"<br>".join([
            f"<b>{d['hogar']}</b><br>Usada: {d['usada']}<br>Oficial: {d['oficial']}<hr>"
            for d in desactualizados
        ]) if desactualizados else "<div style='text-align:center;color:green;font-weight:bold;'>✔ Todos actualizados</div>"}

    </div>


<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<script>

function toggleCausales() {{

    document.getElementById("panelEstados").style.display = "none";
    document.getElementById("panelActividad").style.display = "none";
    document.getElementById("panelMetadata").style.display = "none";

    const panel = document.getElementById("panelCausales");
    const abrir = panel.style.display === "none";
    panel.style.display = abrir ? "block" : "none";

    if (abrir) {{

        var canvas = document.getElementById("graficoCausales");

        if (!canvas) {{
            console.log("NO EXISTE canvas");
            return;
        }}

        if (window.miGrafico) {{
            window.miGrafico.destroy();
        }}

        var dataCausales = {causales_json};

        let labels = dataCausales.labels;
        let valores = dataCausales.values;

        // ===============================
        // 🔥 FILTRAR + ORDENAR
        // ===============================
        let combinado = labels.map((l, i) => ({{
            label: l,
            valor: valores[i]
        }}));

        combinado = combinado.filter(x => x.valor > 0);
        combinado.sort((a, b) => b.valor - a.valor);

        labels = combinado.map(x => x.label);
        valores = combinado.map(x => x.valor);

        // ===============================
        // ✂️ CORTAR TEXTO LARGO
        // ===============================
        labels = labels.map(l => {{
            if (l.length > 30) {{
                return l.substring(0, 30) + '...';
            }}
            return l;
        }});

        // ===============================
        // 🎨 COLORES AUTOMÁTICOS
        // ===============================
        let colores = labels.map((_, i) => {{
            let hue = (i * 35) % 360;
            return `hsl(${{hue}}, 60%, 60%)`;
        }});

        // ===============================
        // 📊 GRAFICO
        // ===============================
        window.miGrafico = new Chart(canvas, {{
            type: 'bar',
            data: {{
                labels: labels,
                datasets: [{{
                    label: 'Cantidad',
                    data: valores,
                    backgroundColor: colores,
                    borderColor: "#333",
                    borderWidth: 1,
                    barThickness: 18,
                    categoryPercentage: 0.7,
                    barPercentage: 0.8
                }}]
            }},
            options: {{
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,

                layout: {{
                    padding: {{
                        left: 30
                    }}
                }},

                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                return "Cantidad: " + context.raw;
                            }}
                        }}
                    }}
                }},

                scales: {{
                    x: {{
                        beginAtZero: true
                    }},
                    y: {{
                        ticks: {{
                            autoSkip: false,
                            font: {{
                                size: 11,
                                weight: 'bold'
                            }}
                        }}
                    }}
                }}
            }},

            // ===============================
            // 🔥 VALORES EN LAS BARRAS
            // ===============================
            plugins: [{{
                id: 'labels',
                afterDatasetsDraw(chart) {{

                    const ctx = chart.ctx;

                    chart.data.datasets.forEach((dataset, i) => {{
                        const meta = chart.getDatasetMeta(i);

                        meta.data.forEach((bar, index) => {{

                            let value = dataset.data[index];

                            ctx.fillStyle = '#000';
                            ctx.font = 'bold 11px sans-serif';
                            ctx.textAlign = 'left';

                            ctx.fillText(value, bar.x + 5, bar.y + 4);
                        }});
                    }});
                }}
            }}]

        }});
    }}
}}

let estadosActivos = new Set();

function toggleEstados() {{
    document.getElementById("panelActividad").style.display = "none";
    document.getElementById("panelMetadata").style.display = "none";
    const est = document.getElementById("panelEstados");
    est.style.display = est.style.display === "none" ? "block" : "none";
}}

function toggleActividad() {{
    document.getElementById("panelEstados").style.display = "none";
    document.getElementById("panelMetadata").style.display = "none";
    const act = document.getElementById("panelActividad");
    act.style.display = act.style.display === "none" ? "block" : "none";
}}

function toggleMetadata() {{
    document.getElementById("panelEstados").style.display = "none";
    document.getElementById("panelActividad").style.display = "none";
    const meta = document.getElementById("panelMetadata");
    meta.style.display = meta.style.display === "none" ? "block" : "none";
}}

function filtrarEstado(estado) {{

    const filas = document.querySelectorAll("#panelEstados tbody tr");

    // Agregar o quitar del set
    if (estadosActivos.has(estado)) {{
        estadosActivos.delete(estado);
    }} else {{
        estadosActivos.add(estado);
    }}

    // Limpiar selección visual
    filas.forEach(tr => tr.classList.remove("estado-activo"));

    // Volver a marcar los seleccionados
    filas.forEach(tr => {{
        const codigo = tr.children[0].innerText.trim();
        if (estadosActivos.has(codigo)) {{
            tr.classList.add("estado-activo");
        }}
    }});

    aplicarFiltroEstado();
}}

function aplicarFiltroEstado() {{

    const markers = document.querySelectorAll(".marker-estado");

    markers.forEach(el => {{

        // Si no hay filtros → mostrar todos
        if (estadosActivos.size === 0) {{
            el.parentElement.style.display = "block";
            return;
        }}

     

        let visible = false;

        estadosActivos.forEach(estado => {{
            if (el.classList.contains("marker-estado-" + estado)) {{
                visible = true;
            }}
        }});

        el.parentElement.style.display = visible ? "block" : "none";
    }});
}}

</script>
"""
    mapa.get_root().html.add_child(folium.Element(panel_html))

    # ===============================
    # REFERENCIAS INFERIORES
    # ===============================

    referencias_html = f"""
    <div style="
        display: {'flex' if mostrar_buscador else 'none'};
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background: #0d6efd;
        color: white;
        border-top: 2px solid #084298;
        padding: 14px 25px;
        font-size: 13px;
        z-index: 9999;
        box-shadow: 0 -2px 6px rgba(0,0,0,0.2);
    ">
        <div style="text-align:center;font-weight:bold;font-size:14px;margin-bottom:6px;">
            REFERENCIAS
        </div>

        <div style="display:flex;justify-content:center;gap:30px;flex-wrap:wrap;">
            <div>🏠 <b>Presencial</b> — Encuesta en territorio</div>
            <div>☎️ <b>Telefónica</b> — Encuesta por teléfono</div>
            <div>🔥 <b>Mapa de calor</b> — Concentración de actividad</div>
            <div>🔴 <b>Resaltado</b> — Hogar buscado</div>
        </div>
    </div>
    """

    mapa.get_root().html.add_child(folium.Element(referencias_html))

    mapa.get_root().html.add_child(folium.Element("""
    <style>
    .leaflet-container {
        margin-bottom: 90px;
    }
    </style>
    """))


    loading_html = """
    <div id="loadingPanel" style="
        position:fixed;
        top:0;
        left:0;
        width:100%;
        height:300%;
        max-height:300px;
        overflow:hidden;
        background:white;
        z-index:99999;
        display:flex;
        justify-content:center;
        align-items:center;
        flex-direction:column;
    ">

    <h3 style="color:#0d6efd; margin-bottom:20px;">
    Cargando mapa territorial...
    </h3>

    <div style="
        width:320px;
        height:22px;
        border:1px solid #ccc;
        border-radius:6px;
        overflow:hidden;
    ">

    <div id="progressBar" style="
        width:0%;
        height:100%;
        background:#0d6efd;
    "></div>

    </div>

    <div id="progressText" style="margin-top:10px;font-weight:bold;">
    0 %
    </div>

    </div>

    <script>

    let progreso = 0;

    let intervalo = setInterval(function(){

        progreso += Math.random()*10;

        if(progreso >= 100){
            progreso = 100;
            clearInterval(intervalo);
        }

        document.getElementById("progressBar").style.width = progreso + "%";
        document.getElementById("progressText").innerHTML = Math.floor(progreso) + " %";

    },300);

    document.addEventListener("DOMContentLoaded", function(){

        let map = document.querySelector(".leaflet-container");

        if(map){

            setTimeout(function(){

                document.getElementById("progressBar").style.width="100%";
                document.getElementById("progressText").innerHTML="100 %";

                document.getElementById("loadingPanel").style.display="none";

            },600);

        }

    });


    </script>
    """
 

        # ===============================
    # MOSTRAR MENSAJES EN EL MAPA
    # ===============================
    # ===============================
# MOSTRAR MENSAJES EN EL MAPA
# ===============================
    if mensaje_error:

        mapa.get_root().html.add_child(
            folium.Element(f"""
            <div style="
                position: fixed;
                top: 80px;
                left: 50%;
                transform: translateX(-50%);
                background:#ffe6e6;
                padding:12px 22px;
                border:1px solid red;
                border-radius:8px;
                z-index:9999;
                font-size:14px;
                font-weight:bold;
                box-shadow:0 4px 10px rgba(0,0,0,0.25);
                text-align:center;
            ">
                {mensaje_error}
            </div>
            """)
        )

    mapa.get_root().html.add_child(folium.Element(loading_html))

    html = mapa.get_root().render()

    html += f"""
    <script>
    function cerrarSesion() {{
        navigator.sendBeacon("/cerrar_panel?sid={sid}");
    }}

    window.addEventListener("beforeunload", cerrarSesion);
    window.addEventListener("pagehide", cerrarSesion);
    </script>
    """

    html = html.replace("__SID__", sid)

    return HTMLResponse(content=html)