import streamlit as st
import rasterio
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import re


def run_retroceso():
    """
    Dashboard del PUNTO 3: área glaciar por año/década y tasa de retroceso.
    Calcula el área (km²) a partir de las máscaras binarias del punto 2 y muestra
    el gráfico de retroceso + los mapas de extensión por década.
    """
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem;
                padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    st.subheader("Retroceso glaciar - Área y tasa de retroceso")
    st.caption("Punto 3 | Área (km²) = nº píxeles glaciar × área de píxel | a partir de la clasificación binaria")

    BASE_DIR = Path(__file__).resolve().parents[2]
    CLAS_DIR = BASE_DIR / "data" / "processed" / "clasificacion"
    DECADAS = [1985, 1995, 2005, 2015, 2025]

    @st.cache_data
    def calcular_areas(dir_sensor_str):
        """Devuelve (años, areas_km2, rutas) ordenados por año para un sensor."""
        dir_sensor = Path(dir_sensor_str)
        archivos = list(dir_sensor.glob("*.tif"))
        if not archivos:
            st.error(f"No se encontraron clasificaciones en {dir_sensor}")
            st.stop()
        registros = []
        for p in archivos:
            m = re.search(r'(\d{4})\d{2}\d{2}', p.name)
            if not m:
                continue
            año = int(m.group(1))
            with rasterio.open(p) as src:
                clas = src.read(1)
                px_area_m2 = abs(src.transform.a) * abs(src.transform.e)
            area_km2 = int(np.sum(clas == 1)) * px_area_m2 / 1e6
            registros.append((año, area_km2, str(p)))
        registros.sort(key=lambda x: x[0])
        años = [r[0] for r in registros]
        areas = [r[1] for r in registros]
        rutas = {r[0]: r[2] for r in registros}
        return años, areas, rutas

    @st.cache_data
    def cargar_clasif(ruta_str):
        with rasterio.open(ruta_str) as src:
            data = src.read(1).astype(float)
        data[data == 255] = np.nan
        return data

    sensor = st.radio("Sensor", ("Landsat (1985-2026)", "Sentinel-2 (2015-2024)"),
                      horizontal=True, key="retro_sensor")
    subdir = "landsat" if sensor.startswith("Landsat") else "sentinel2"

    años, areas, rutas = calcular_areas(str(CLAS_DIR / subdir))
    area_por_año = dict(zip(años, areas))

    # --- Tasa de retroceso: ajuste lineal área vs año ---
    x = np.array(años, dtype=float)
    y = np.array(areas, dtype=float)
    pendiente, intercepto = np.polyfit(x, y, 1)
    area_ini, area_fin = areas[0], areas[-1]
    pct = 100 * (area_fin - area_ini) / area_ini if area_ini > 0 else float('nan')

    # --- Métricas ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Área {años[0]}", f"{area_ini:.2f} km²")
    c2.metric(f"Área {años[-1]}", f"{area_fin:.2f} km²")
    c3.metric("Tasa de retroceso", f"{pendiente:.4f} km²/año")
    c4.metric("Cambio total", f"{pct:+.1f} %")

    # --- Gráfico de retroceso ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=años, y=areas, mode='lines+markers',
                             name='Área glaciar', line=dict(color='#1f6fe0')))
    fig.add_trace(go.Scatter(x=años, y=(pendiente * x + intercepto), mode='lines',
                             name='Tendencia', line=dict(color='red', dash='dash')))
    # Resaltar los cortes de década sobre la serie completa
    dec_x = [d for d in DECADAS if d in area_por_año]
    dec_y = [area_por_año[d] for d in dec_x]
    if dec_x:
        fig.add_trace(go.Scatter(x=dec_x, y=dec_y, mode='markers', name='Década',
                                 marker=dict(color='orange', size=13, symbol='diamond',
                                             line=dict(color='black', width=1))))
    fig.update_layout(
        xaxis_title="Año", yaxis_title="Área glaciar (km²)",
        margin=dict(l=0, r=0, t=10, b=0), height=380,
        legend=dict(orientation='h', yanchor='bottom', y=1.0, xanchor='right', x=1)
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})

    # --- Tabla de área por década (entregable: "área frontal por década") ---
    if dec_x:
        st.markdown("#### Área glaciar por década")
        filas, prev = [], None
        for d in dec_x:
            a = area_por_año[d]
            delta = "—" if prev is None else f"{a - prev:+.2f}"
            filas.append({"Década": d, "Área (km²)": round(a, 2),
                          "Δ vs década previa (km²)": delta})
            prev = a
        st.table(pd.DataFrame(filas).set_index("Década"))

    # --- Mapas de extensión por década (entregable mínimo de la pauta) ---
    st.markdown("#### Mapas de extensión glaciar por década")
    decadas_disp = [d for d in DECADAS if d in rutas]
    if decadas_disp:
        cols = st.columns(len(decadas_disp))
        for col, d in zip(cols, decadas_disp):
            clas = cargar_clasif(rutas[d])
            mini = px.imshow(clas, color_continuous_scale=[[0.0, '#8c6d4f'], [1.0, '#1f6fe0']],
                             zmin=0, zmax=1, origin='upper', aspect='equal')
            mini.update_layout(coloraxis_showscale=False, margin=dict(l=0, r=0, t=0, b=0), height=160)
            mini.update_xaxes(visible=False); mini.update_yaxes(visible=False)
            col.markdown(f"**{d}** · {dict(zip(años, areas)).get(d, 0):.2f} km²")
            col.plotly_chart(mini, use_container_width=True, config={'displayModeBar': False})
    else:
        st.info("No hay clasificaciones en los años de década para este sensor.")

    st.caption("🔵 glaciar · 🟤 roca/suelo | Fuente: data/processed/clasificacion/")
