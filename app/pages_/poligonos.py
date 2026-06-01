import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from folium import GeoJson, GeoJsonTooltip, GeoJsonPopup
from streamlit_folium import st_folium
from pathlib import Path
import branca.colormap as cm
import numpy as np


def run_poligonos():
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem; padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    st.subheader("Polígonos glaciares — Extensión y variación")
    st.caption(
        "Etapa 3 | Polígonos vectoriales generados a partir de las máscaras NDSI "
        "con filtro FABDEM ≥ 3 000 m s.n.m. | "
        "Color: Δ área acumulado respecto al año base del sensor"
    )

    BASE_DIR   = Path(__file__).resolve().parents[2]
    VECTOR_DIR = BASE_DIR / "data" / "processed" / "vectores"
    OUT_DIR    = BASE_DIR / "outputs"

    # ── Verificar archivos ───────────────────────────────────────────────────
    gpkg_ls = VECTOR_DIR / "glaciar_echaurren_landsat.gpkg"
    gpkg_s2 = VECTOR_DIR / "glaciar_echaurren_sentinel2.gpkg"

    disponibles = {
        "Landsat":    gpkg_ls if gpkg_ls.exists() else None,
        "Sentinel-2": gpkg_s2 if gpkg_s2.exists() else None,
    }
    if all(v is None for v in disponibles.values()):
        st.error(
            "No se encontraron GeoPackages. "
            "Ejecuta primero `scripts/analyze_glacier.py`."
        )
        st.stop()

    # ── Controles ────────────────────────────────────────────────────────────
    col_ctrl, col_info = st.columns([1, 2])

    with col_ctrl:
        sensor_disp = [k for k, v in disponibles.items() if v is not None]
        sensor_sel  = st.radio("Sensor", sensor_disp, key="poly_sensor")
        gpkg_path   = disponibles[sensor_sel]

    @st.cache_data
    def cargar_gpkg(path_str):
        gdf = gpd.read_file(path_str)
        # Reproyectar a WGS84 para Folium
        return gdf.to_crs(epsg=4326)

    gdf = cargar_gpkg(str(gpkg_path))

    # Cargar serie temporal para obtener delta acumulado por año
    serie_path = OUT_DIR / f"serie_temporal_{sensor_sel.lower().replace('-', '')}.csv"
    if not serie_path.exists():
        # Intentar nombre alternativo
        serie_path = OUT_DIR / f"serie_temporal_{'landsat' if sensor_sel == 'Landsat' else 'sentinel2'}.csv"

    delta_por_año = {}
    if serie_path.exists():
        serie = pd.read_csv(serie_path)
        delta_por_año = dict(zip(serie['año'].astype(int),
                                 serie['delta_km2']))

    # Añadir delta al GDF
    gdf['delta_km2'] = gdf['año'].map(delta_por_año).fillna(0)

    with col_ctrl:
        años_disp   = sorted(gdf['año'].unique())
        rango_años  = st.select_slider(
            "Rango de años",
            options=años_disp,
            value=(años_disp[0], años_disp[-1]),
            key="poly_años"
        )
        mostrar_base = st.selectbox(
            "Fondo del mapa",
            ["CartoDB Positron", "Esri Satellite", "OpenStreetMap"],
            key="poly_fondo"
        )

    tiles_map = {
        "CartoDB Positron": "CartoDB positron",
        "Esri Satellite":   "https://server.arcgisonline.com/ArcGIS/rest/services/"
                            "World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "OpenStreetMap":    "OpenStreetMap",
    }
    tiles_attr = {
        "CartoDB Positron": "© CartoDB",
        "Esri Satellite":   "© Esri",
        "OpenStreetMap":    "© OpenStreetMap contributors",
    }

    # Filtrar por rango de años
    gdf_fil = gdf[
        (gdf['año'] >= rango_años[0]) & (gdf['año'] <= rango_años[1])
    ].copy()

    with col_info:
        c1, c2, c3 = st.columns(3)
        c1.metric("Polígonos visibles", len(gdf_fil))
        c2.metric("Años cubiertos",
                  len(gdf_fil['año'].unique()))
        c3.metric("Área total visible",
                  f"{gdf_fil['area_km2'].sum():.4f} km²")

    if gdf_fil.empty:
        st.warning("Sin polígonos en el rango seleccionado.")
        return

    # ── Paleta divergente RdBu centrada en 0 ────────────────────────────────
    vmax = max(abs(gdf_fil['delta_km2'].min()),
               abs(gdf_fil['delta_km2'].max()))
    vmax = vmax if vmax > 0 else 1.0

    colormap = cm.LinearColormap(
        colors=['#d73027', '#f46d43', '#fdae61', '#ffffff',
                '#abd9e9', '#74add1', '#4575b4'],
        vmin=-vmax, vmax=vmax,
        caption=f"Δ área acumulado (km²) respecto al año base"
    )

    def estilo(feature):
        delta = feature['properties'].get('delta_km2', 0) or 0
        return {
            'fillColor':   colormap(delta),
            'color':       'white',
            'weight':      0.8,
            'fillOpacity': 0.75,
        }

    # ── Construir mapa Folium ────────────────────────────────────────────────
    centroide = gdf_fil.geometry.unary_union.centroid
    tiles     = tiles_map[mostrar_base]
    attr      = tiles_attr[mostrar_base]

    if mostrar_base == "CartoDB Positron":
        m = folium.Map(location=[centroide.y, centroide.x],
                       zoom_start=13, tiles=tiles)
    else:
        m = folium.Map(location=[centroide.y, centroide.x],
                       zoom_start=13, tiles=tiles, attr=attr)

    GeoJson(
        gdf_fil.__geo_interface__,
        style_function=estilo,
        tooltip=GeoJsonTooltip(
            fields=['año', 'sensor', 'area_km2', 'delta_km2'],
            aliases=['Año', 'Sensor', 'Área (km²)', 'Δ acumulado (km²)'],
            localize=True,
            sticky=False,
        ),
        popup=GeoJsonPopup(
            fields=['año', 'sensor', 'area_km2', 'delta_km2'],
            aliases=['Año', 'Sensor', 'Área (km²)', 'Δ acumulado (km²)'],
        ),
        name="Polígonos glaciares"
    ).add_to(m)

    colormap.add_to(m)
    folium.LayerControl().add_to(m)

    st_folium(m, use_container_width=True, height=580)

    # ── Tabla resumen por año ────────────────────────────────────────────────
    with st.expander("Ver tabla de área por año"):
        resumen = (
            gdf_fil.groupby('año')
            .agg(
                n_poligonos=('area_km2', 'count'),
                area_total_km2=('area_km2', 'sum'),
                delta_km2=('delta_km2', 'first'),
            )
            .reset_index()
            .rename(columns={
                'año':            'Año',
                'n_poligonos':    'N polígonos',
                'area_total_km2': 'Área total (km²)',
                'delta_km2':      'Δ acumulado (km²)',
            })
        )
        resumen['Área total (km²)']   = resumen['Área total (km²)'].round(4)
        resumen['Δ acumulado (km²)']  = resumen['Δ acumulado (km²)'].round(4)
        st.dataframe(resumen, use_container_width=True, hide_index=True)

    st.caption(
        "🔴 retroceso · ⚪ sin cambio · 🔵 avance | "
        f"Fuente: {gpkg_path.name}"
    )