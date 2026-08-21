import streamlit as st
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds as transform_from_bounds
import numpy as np
import plotly.express as px
import geopandas as gpd
from pathlib import Path
import re
import sys

BASE_DIR_APP = Path(__file__).resolve().parents[2]
if str(BASE_DIR_APP) not in sys.path:
    sys.path.insert(0, str(BASE_DIR_APP))
from scripts.glacier_config import get_config  # noqa: E402

def run_ndsi_sentinel(glaciar=None):
    """
    Dashboard interactivo para visualizar el índice NDSI calculado
    a partir de imágenes Sentinel-2 procesadas del glaciar seleccionado.
    """
    glaciar = glaciar or get_config("echaurren")
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem;
                padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    # 1. TÍTULO DINÁMICO
    titulo_placeholder = st.empty()
    st.caption("Índice NDSI desde Sentinel-2 | Pasa el cursor sobre el mapa para ver valores")

    BASE_DIR = Path(__file__).resolve().parents[2]
    PROCESSED_DIR = BASE_DIR / "data" / "processed" / glaciar.slug / "sentinel2"
    DGA_VECTOR_PATH = BASE_DIR / "data" / "IPG_2022_v2" / "INV_PG_2022_v2.shp"

    @st.cache_data
    def cargar_poligono_dga(nombre_dga, crs_epsg):
        """Carga, filtra y reproyecta el shapefile de la DGA una sola vez.
        Recibe nombre_dga/crs_epsg como argumentos para que la clave de caché
        dependa del glaciar (st.cache_data no considera el closure)."""
        if not DGA_VECTOR_PATH.exists():
            return None
        inventario_dga = gpd.read_file(DGA_VECTOR_PATH)
        glaciar_vector = inventario_dga[
            inventario_dga['NOMBRE'].str.contains(nombre_dga, case=False, na=False)
        ]
        return glaciar_vector.to_crs(epsg=crs_epsg)

    @st.cache_data
    def obtener_lista_archivos(slug):
        archivos = list(PROCESSED_DIR.glob(f"{slug}_ndsi_*.tif"))
        if not archivos:
            st.error(f"No se encontraron archivos Sentinel-2 en {PROCESSED_DIR}")
            st.stop()

        def extraer_datos(nombre):
            match = re.search(r'(\d{4})(\d{2})(\d{2})', nombre)
            if match:
                año = int(match.group(1))
                fecha_completa = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                return año, fecha_completa
            return None, None

        pares = []
        for p in archivos:
            año, f_completa = extraer_datos(p.name)
            if año:
                pares.append((año, f_completa, p))
        
        pares.sort(key=lambda x: x[0])
        return pares

    @st.cache_data
    def cargar_array_ndsi(ruta_tif, escala=0.5):
        """
        Lee la matriz, la reduce por la escala y recalcula la transformación 
        cartográfica para que el polígono DGA coincida con la imagen achicada.
        """
        with rasterio.open(ruta_tif) as src:
            h_orig, w_orig = src.height, src.width
            h_new = max(1, int(h_orig * escala))
            w_new = max(1, int(w_orig * escala))
            
            data = src.read(1, out_shape=(h_new, w_new), resampling=Resampling.bilinear)
            nodata = src.nodata if src.nodata is not None else -9999
            data = np.where(data == nodata, np.nan, data)
            
            # Recalculamos el transform para alinear los vectores DGA
            nuevo_transform = transform_from_bounds(*src.bounds, w_new, h_new)
            
            return data, h_new, w_new, nuevo_transform

    dga_poly = cargar_poligono_dga(glaciar.nombre_dga, glaciar.crs_epsg)
    datos_archivos = obtener_lista_archivos(glaciar.slug)
    años             = [d[0] for d in datos_archivos]
    fechas_completas = [d[1] for d in datos_archivos]
    rutas            = [d[2] for d in datos_archivos]

    _clave_arrays = f"ndsi_arrays_sentinel_{glaciar.slug}"
    if _clave_arrays not in st.session_state:
        st.session_state[_clave_arrays] = {}
        with st.spinner("Precargando datos de Sentinel-2 (solo la primera vez)..."):
            for d in datos_archivos:
                año = d[0]
                ruta = d[2]
                arr, h, w, transf = cargar_array_ndsi(ruta, escala=0.5)
                st.session_state[_clave_arrays][año] = (arr, h, w, transf)

    col_map, col_controls = st.columns([4, 1])

    with col_controls:
        año_seleccionado = st.select_slider(
            "Selecciona el año",
            options=años,
            value=años[0],
            format_func=str,
            key="slider_sentinel"
        )
        
        idx = años.index(año_seleccionado)
        fecha_exacta = fechas_completas[idx]
        ruta         = rutas[idx]
        ndsi_data, h, w, transform = st.session_state[_clave_arrays][año_seleccionado]

        st.markdown("### Metadatos")
        st.write(f"**Sensor:** Sentinel-2")
        st.write(f"**Fecha de captura:** {fecha_exacta}")
        st.write(f"**Archivo:** `{ruta.name}`")
        st.write(f"**Dimensiones mostradas:** {w} x {h} px")
        st.markdown("**Interpretación NDSI:**")
        st.markdown("• &nbsp; > 0.4 → nieve/hielo seguro")
        st.markdown("• &nbsp; 0.1 a 0.4 → nieve parcial / sombras")
        st.markdown("• &nbsp; < 0 → sin nieve")
        st.markdown("**Vectores:**")
        st.markdown(f"• &nbsp; Silueta Oficial DGA ({glaciar.nombre_dga})")

    titulo_placeholder.subheader(
        f"Mapa de Índice de Nieve Diferencial Normalizado (NDSI) — {glaciar.nombre} ({año_seleccionado})"
    )

    with col_map:
        fig = px.imshow(
            ndsi_data,
            color_continuous_scale='RdYlBu_r', 
            zmin=-0.2, zmax=1.0,
            aspect='equal',
            origin='upper',
            labels=dict(color="NDSI")
        )
        fig.update_traces(
            hovertemplate="NDSI: %{z:.2f}<extra></extra>",
            hoverinfo="z"
        )
        
        # --- POLÍGONO DGA ---
        if dga_poly is not None and not dga_poly.empty:
            inv_transform = ~transform
            
            for geom in dga_poly.geometry:
                polygons = [geom] if geom.geom_type == 'Polygon' else geom.geoms
                
                for poly in polygons:
                    x_esp, y_esp = poly.exterior.coords.xy
                    cols, rows = [], []
                    
                    for x, y in zip(x_esp, y_esp):
                        col, row = inv_transform * (x, y)
                        cols.append(col)
                        rows.append(row)
                        
                    if (min(cols) < w and max(cols) > 0 and 
                        min(rows) < h and max(rows) > 0):
                        
                        fig.add_scatter(
                            x=cols, y=rows,
                            mode='lines',
                            line=dict(color="#000000", width=2.5),
                            name='Silueta DGA',
                            hoverinfo='skip',
                            showlegend=False
                        )
        # ----------------------------------

        fig.update_layout(
            coloraxis_colorbar=dict(
                title="NDSI", 
                thickness=18, 
                len=0.5,
                yanchor="middle",
                y=0.5,
                title_font=dict(size=14),
                tickfont=dict(size=13)
            ),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
            margin=dict(l=10, r=10, t=10, b=10),
            height=800
        )

        fig.add_annotation(
            x=w * 0.92, y=h * 0.08,
            xref="x", yref="y",
            text="▲<br><b>N</b>",
            showarrow=False,
            font=dict(size=22, color="white"), 
            align="center",
            bgcolor="rgba(0,0,0,0.6)",
            bordercolor="rgba(255,255,255,0.8)",
            borderwidth=1,
            borderpad=8
        )

        # 5. ESCALA GRÁFICA INTERACTIVA ESTANDARIZADA
        # Como process_data.py unificó todo a 30m/px, con escala=0.5 la resolución final es 60m/px.
        # Por lo tanto, 10 píxeles = 600 metros exactos, igual que en Landsat.
        tamano_barra_px = 10 
        texto_escala = "600 m" 
        
        x_start = w * 0.05
        x_end = x_start + tamano_barra_px
        y_pos = h * 0.92

        fig.add_shape(
            type="line",
            x0=x_start, y0=y_pos, x1=x_end, y1=y_pos,
            line=dict(color="white", width=6), 
            xref="x", yref="y"
        )
        fig.add_annotation(
            x=(x_start + x_end) / 2, y=y_pos - (h * 0.035),
            xref="x", yref="y",
            text=texto_escala,
            showarrow=False,
            font=dict(size=14, color="white"), 
            bgcolor="rgba(0,0,0,0.6)",
            borderpad=3
        )

        texto_metadatos = f"<b>CRS:</b> EPSG:{glaciar.crs_epsg} (WGS84 / UTM) | <b>Fuente:</b> DGA (Sentinel-2) | <b>Fecha:</b> {fecha_exacta}"
        fig.add_annotation(
            x=w * 0.5, y=h * 0.97,
            xref="x", yref="y",
            text=texto_metadatos,
            showarrow=False,
            font=dict(size=13, color="rgba(255,255,255,0.9)"), 
            align="center",
            bgcolor="rgba(0,0,0,0.7)",
            borderpad=6
        )

        st.plotly_chart(
            fig, 
            use_container_width=True, 
            config={
                "displayModeBar": True,
                "responsive": False
            }
        )

    st.caption(f"Ruta de almacenamiento local: `{PROCESSED_DIR}`")