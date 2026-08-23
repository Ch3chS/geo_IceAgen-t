import streamlit as st
import geopandas as gpd
import pandas as pd
import plotly.graph_objects as go
import folium
from folium import GeoJson, GeoJsonTooltip
from streamlit_folium import st_folium
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from scripts.glacier_config import get_config  # noqa: E402
from scripts.validar_dga import cargar_referencia_dga  # noqa: E402

SENSORES = {"landsat": "Landsat", "sentinel2": "Sentinel-2"}
COLORES_SENSOR = {"landsat": "#e07b39", "sentinel2": "#1f6fe0"}


def _fig_diff(df_sensor, sensor):
    colores_bar = ['#d62728' if v > 0 else '#4575b4' for v in df_sensor['diff_km2']]
    fig = go.Figure(go.Bar(
        x=df_sensor['año'], y=df_sensor['diff_km2'],
        marker_color=colores_bar,
        hovertemplate="%{x}: %{y:+.4f} km²<extra></extra>"
    ))
    fig.add_hline(y=0, line_color='black', line_width=0.8)
    fig.update_layout(
        title=SENSORES[sensor],
        xaxis_title="Año", yaxis_title="Pipeline − DGA (km²)",
        margin=dict(l=0, r=0, t=30, b=0), height=280,
        showlegend=False
    )
    return fig


def run_validacion_dga(glaciar=None):
    glaciar = glaciar or get_config("echaurren")
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem; padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    st.subheader("Validación espacial contra el Inventario DGA (IPG 2022)")
    st.caption(
        f"Etapa 6 | {glaciar.nombre} | "
        "Compara el área glaciar del pipeline (NDSI+DEM) contra el "
        "único snapshot fotointerpretado del Inventario Público de Glaciares "
        "(IPG 2022) — MAE, sesgo sistemático por sensor y mapa comparativo de "
        "polígonos."
    )

    OUT_DIR = BASE_DIR / "outputs" / glaciar.slug
    AREA = OUT_DIR / "validacion_dga_area.csv"
    RESUMEN = OUT_DIR / "validacion_dga_resumen.csv"

    faltantes = [p for p in [AREA, RESUMEN] if not p.exists()]
    if faltantes:
        st.error(
            "No se encontraron los archivos de la Etapa 6. "
            "Ejecuta `scripts/validar_dga.py`.\n\n"
            + "\n".join(f"- `{p.name}`" for p in faltantes)
        )
        st.stop()

    @st.cache_data
    def cargar(path_str, mtime):
        return pd.read_csv(path_str)

    area = cargar(str(AREA), AREA.stat().st_mtime)
    resumen = cargar(str(RESUMEN), RESUMEN.stat().st_mtime)

    # ── Métricas de resumen por sensor ──────────────────────────────────────
    st.markdown("#### MAE y sesgo sistemático por sensor")
    cols = st.columns(len(resumen))
    for col, (_, fila) in zip(cols, resumen.iterrows()):
        with col:
            st.markdown(f"**{SENSORES.get(fila['sensor'], fila['sensor'])}**")
            st.metric("MAE", f"{fila['mae_km2']:.4f} km²")
            signo = "sobreestima" if fila['sesgo_medio_km2'] > 0 else "subestima"
            st.metric("Sesgo medio", f"{fila['sesgo_medio_km2']:+.4f} km²", help=signo)
            st.metric("RMSE", f"{fila['rmse_km2']:.4f} km²")
            st.caption(
                f"n={fila['n_años']} años · año más cercano a "
                f"{fila['año_dga_referencia']}: **{fila['año_mas_cercano']}** "
                f"(Δ={fila['diff_año_mas_cercano_km2']:+.4f} km²)"
            )
    st.caption(
        f"Referencia DGA ({glaciar.nombre_dga} + fragmentos, año "
        f"{int(resumen['año_dga_referencia'].iloc[0])}): "
        f"{resumen['area_dga_referencia_km2'].iloc[0]:.6f} km²."
    )

    # ── Gráfico de discrepancias por año ────────────────────────────────────
    st.markdown("#### Discrepancia (pipeline − DGA) por año")
    col_a, col_b = st.columns(2)
    for col, sensor in zip([col_a, col_b], SENSORES):
        df_sensor = area[area['sensor'] == sensor]
        if df_sensor.empty:
            continue
        with col:
            st.plotly_chart(_fig_diff(df_sensor, sensor),
                             use_container_width=True, config={'displayModeBar': False})

    # ── Mapa comparativo ─────────────────────────────────────────────────────
    st.markdown("#### Mapa comparativo: DGA vs pipeline")

    VECTOR_DIR = BASE_DIR / "data" / "processed" / glaciar.slug / "vectores"
    gpkg_disp = {
        s: VECTOR_DIR / f"glaciar_{glaciar.slug}_{s}.gpkg"
        for s in SENSORES
        if (VECTOR_DIR / f"glaciar_{glaciar.slug}_{s}.gpkg").exists()
    }

    if not gpkg_disp:
        st.warning(
            "No se encontraron GeoPackages vectorizados en "
            f"`{VECTOR_DIR}` — ejecuta `scripts/spatial_analysis.py` "
            "para generar el mapa comparativo."
        )
        return

    @st.cache_data
    def cargar_dga_ref(nombre_dga, crs_epsg):
        gdf, area_km2 = cargar_referencia_dga(nombre_dga, crs_epsg)
        return gdf, area_km2

    @st.cache_data
    def cargar_gpkg(path_str):
        return gpd.read_file(path_str)

    dga_gdf, _ = cargar_dga_ref(glaciar.nombre_dga, glaciar.crs_epsg)

    col_ctrl, col_map = st.columns([1, 3])
    with col_ctrl:
        sensor_sel = st.radio("Sensor", list(gpkg_disp.keys()),
                              format_func=lambda s: SENSORES[s], key="val_sensor")
        gdf_pipeline_todo = cargar_gpkg(str(gpkg_disp[sensor_sel]))
        años_disp = sorted(gdf_pipeline_todo['año'].unique())
        año_sel = st.select_slider("Año", options=años_disp,
                                   value=años_disp[-1], key="val_año")

    gdf_año = gdf_pipeline_todo[gdf_pipeline_todo['año'] == año_sel]

    # ── Métricas de overlap espacial (EPSG:32719, área exacta) ─────────────
    dga_union = dga_gdf.geometry.union_all()
    pipeline_union = gdf_año.geometry.union_all() if not gdf_año.empty else None

    with col_ctrl:
        if pipeline_union is not None and not pipeline_union.is_empty:
            interseccion = dga_union.intersection(pipeline_union).area / 1e6
            union_total = dga_union.union(pipeline_union).area / 1e6
            omision = (dga_union.difference(pipeline_union)).area / 1e6
            comision = (pipeline_union.difference(dga_union)).area / 1e6
            iou = interseccion / union_total if union_total > 0 else float('nan')

            st.metric("IoU", f"{iou:.3f}")
            st.metric("Omisión (solo DGA)", f"{omision:.4f} km²")
            st.metric("Comisión (solo pipeline)", f"{comision:.4f} km²")
        else:
            st.info(f"Sin polígonos del pipeline para {año_sel}.")

    with col_map:
        centroide = dga_union.centroid
        dga_4326 = dga_gdf.to_crs(epsg=4326)
        centroide_4326 = gpd.GeoSeries([centroide], crs="EPSG:32719").to_crs(epsg=4326).iloc[0]

        m = folium.Map(location=[centroide_4326.y, centroide_4326.x],
                       zoom_start=14, tiles="CartoDB positron")

        GeoJson(
            dga_4326[['NOMBRE', 'AREA_KM2', 'geometry']].__geo_interface__,
            style_function=lambda f: {
                'fillColor': '#2ca02c', 'color': '#2ca02c',
                'weight': 2, 'fillOpacity': 0.35,
            },
            tooltip=GeoJsonTooltip(fields=['NOMBRE', 'AREA_KM2'],
                                   aliases=['Nombre', 'Área DGA (km²)']),
            name="Inventario DGA (2022)"
        ).add_to(m)

        if not gdf_año.empty:
            gdf_año_4326 = gdf_año.to_crs(epsg=4326)
            GeoJson(
                gdf_año_4326[['año', 'area_km2', 'geometry']].__geo_interface__,
                style_function=lambda f: {
                    'fillColor': '#7c3aed', 'color': '#7c3aed',
                    'weight': 2, 'fillOpacity': 0.35,
                },
                tooltip=GeoJsonTooltip(fields=['año', 'area_km2'],
                                       aliases=['Año', 'Área pipeline (km²)']),
                name=f"Pipeline {sensor_sel} {año_sel}"
            ).add_to(m)

        folium.LayerControl().add_to(m)
        st_folium(m, use_container_width=True, height=520)

    st.caption(
        "🟩 Inventario DGA (fijo, 2022) · 🟪 Polígono del pipeline (año/sensor "
        "seleccionado) · el solape visual es la intersección real, no una "
        "aproximación."
    )

    # ── Tabla completa ────────────────────────────────────────────────────
    with st.expander("Ver tabla completa (todos los años y sensores)"):
        tabla = area.rename(columns={
            'año': 'Año', 'sensor': 'Sensor',
            'area_pipeline_km2': 'Área pipeline (km²)',
            'area_dga_km2': 'Área DGA (km²)',
            'diff_km2': 'Diferencia (km²)',
            'abs_diff_km2': 'Diferencia abs. (km²)',
            'diff_pct': 'Diferencia (%)',
        }).copy()
        tabla['Sensor'] = tabla['Sensor'].map(SENSORES)
        for c in ['Área pipeline (km²)', 'Área DGA (km²)', 'Diferencia (km²)',
                  'Diferencia abs. (km²)']:
            tabla[c] = tabla[c].round(4)
        st.dataframe(tabla, use_container_width=True, hide_index=True)

    # ── Notas y limitaciones ─────────────────────────────────────────────────
    st.markdown("#### Notas y limitaciones")
    st.markdown(f"""
    - **El DGA es un único snapshot** (fotointerpretación, año 2022), no una
      serie temporal — esta validación mide qué tan lejos está *cada año* del
      pipeline de esa única referencia fija, no una comparación año-a-año real.
    - **Referencia DGA = suma de las sub-features del inventario para
      `{glaciar.nombre_dga}`** (algunas clasificadas `GLACIARETE`, la categoría
      morfológica más pequeña/marginal del inventario): el pipeline no
      distingue fragmentos del mismo cuerpo de hielo, así que sumarlos es la
      comparación más justa.
    - **Sesgo dependiente del sensor**: Landsat (30 m) suele sobreestimar
      más que Sentinel-2 (10–20 m) — consistente con píxeles mixtos de nieve
      estacional a 30 m clasificados como glaciar (NDSI≥0.4 sobre 3 000 m
      s.n.m.), no solo hielo perenne. La magnitud exacta del sesgo se reporta
      por sensor en las métricas de arriba.
    - **El área NDSI mide nieve+hielo del ~26 de enero, no glaciar perenne**:
      misma limitación ya documentada en la pestaña "Correlación DGA" — un
      año muy nevado infla el área NDSI sin que el glaciar realmente haya
      crecido. El IoU del mapa comparativo es más informativo que el MAE de
      área sola porque muestra si el pipeline al menos ubica el hielo en el
      lugar correcto, más allá de la magnitud total.
    - **Incluso el propio DGA es ambiguo aquí**: `GLACIARETE` es la categoría
      con el límite más difuso entre hielo perenne y nieve estacional incluso
      en la fotointerpretación oficial — el "ground truth" no es perfecto.
    """)
