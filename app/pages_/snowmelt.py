import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path

ESTACIONES = {
    "05703006": "Estero Glaciar Echaurren Norte",
    "05704002": "Río Maipo en San Alfonso",
}

VARIABLES_SIM = {
    "melt_djf_mm":         "Derretimiento simulado (mm w.e., suma DJF)",
    "runoff_djf_mm":       "Escorrentía simulada (mm w.e., suma DJF)",
    "routed_djf_mm":       "Escorrentía ruteada (mm w.e., suma DJF)",
}

# Variables adicionales que snowmelt-rs también correlaciona (ver
# correlacion_snowmelt_dga.csv) pero que no son la escorrentía/derretimiento
# principal — se muestran en la tabla de resultados aunque no estén en el
# selector de gráficos.
VARIABLES_TABLA = {
    **VARIABLES_SIM,
    "snowfall_djf_mm":     "Nevada simulada (mm, suma DJF)",
    "rain_djf_mm":         "Lluvia simulada (mm, suma DJF)",
    "sublimation_djf_mm":  "Sublimación simulada (mm, suma DJF)",
}


def _fig_scatter(joined, var):
    sim  = joined[var]
    caud = joined["caudal_djf_m3s"]
    pend, inter = np.polyfit(sim, caud, 1)
    xline = np.linspace(sim.min(), sim.max(), 50)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sim, y=caud, mode='markers', name='Años',
        marker=dict(size=10, color='#7c3aed',
                    line=dict(color='black', width=0.6)),
        text=[f"{a}" for a in joined['año']], hovertemplate=
        "%{text} · sim=%{x:.1f} mm · caudal=%{y:.4f} m³/s<extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=xline, y=pend * xline + inter, mode='lines',
        name='Regresión lineal',
        line=dict(color='#d62728', dash='dash')
    ))
    fig.update_layout(
        xaxis_title=VARIABLES_SIM[var],
        yaxis_title="Caudal estival DJF (m³/s)",
        margin=dict(l=0, r=0, t=10, b=0), height=420,
        legend=dict(orientation='h', yanchor='bottom', y=1.0,
                    xanchor='right', x=1)
    )
    return fig


def _fig_serie(joined, var):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=joined['año'], y=joined[var], mode='lines+markers',
        name='Simulado (snowmelt-rs)', line=dict(color='#7c3aed'),
        hovertemplate="%{x}: %{y:.1f} mm<extra>Simulado</extra>",
        yaxis='y1'
    ))
    fig.add_trace(go.Scatter(
        x=joined['año'], y=joined['caudal_djf_m3s'], mode='lines+markers',
        name='Caudal DJF observado', line=dict(color='#d62728'),
        hovertemplate="%{x}: %{y:.4f} m³/s<extra>Caudal</extra>",
        yaxis='y2'
    ))
    fig.update_layout(
        xaxis_title="Año",
        yaxis=dict(title=VARIABLES_SIM[var], color='#7c3aed'),
        yaxis2=dict(title="Caudal estival DJF (m³/s)", color='#d62728',
                    overlaying='y', side='right'),
        margin=dict(l=0, r=0, t=10, b=0), height=380,
        legend=dict(orientation='h', yanchor='bottom', y=1.0,
                    xanchor='right', x=1)
    )
    return fig


def run_snowmelt():
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem; padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    st.subheader("Balance físico de derretimiento (snowmelt-rs)")
    st.caption(
        "Etapa 5b | Segunda línea de evidencia independiente: simula el balance "
        "de masa nival/glaciar sobre el DEM con un modelo físico (snowmelt-rs) "
        "y compara el aporte de deshielo con el caudal estival (DJF) de la DGA."
    )

    BASE_DIR = Path(__file__).resolve().parents[2]
    OUT_DIR  = BASE_DIR / "outputs"

    DJF     = OUT_DIR / "snowmelt_djf.csv"
    CAUDAL  = OUT_DIR / "caudal_dga_djf_snowmelt.csv"
    CORR    = OUT_DIR / "correlacion_snowmelt_dga.csv"
    RESUMEN = OUT_DIR / "snowmelt_resumen.csv"

    faltantes = [p for p in [DJF, CAUDAL, CORR, RESUMEN] if not p.exists()]
    if faltantes:
        st.error(
            "No se encontraron los archivos de la Etapa 5b. "
            "Compila `snowmelt-cli` y ejecuta `scripts/run_snowmelt.py`.\n\n"
            + "\n".join(f"- `{p.name}`" for p in faltantes)
        )
        st.stop()

    @st.cache_data
    def cargar(path_str, mtime):
        return pd.read_csv(path_str)

    @st.cache_data
    def cargar_estacion(path_str, mtime):
        return pd.read_csv(path_str, dtype={"codigo_estacion": str})

    djf     = cargar(str(DJF), DJF.stat().st_mtime)
    caudal  = cargar_estacion(str(CAUDAL), CAUDAL.stat().st_mtime)
    corr    = cargar_estacion(str(CORR),   CORR.stat().st_mtime)
    resumen = cargar(str(RESUMEN), RESUMEN.stat().st_mtime).iloc[0]

    # ── Resumen del modelo físico ───────────────────────────────────────────
    st.markdown("#### Resumen del balance de masa simulado")
    c1, c2, c3 = st.columns(3)
    c1.metric("ELA estimada",
               f"{resumen['ela_m']:.0f} m" if pd.notna(resumen['ela_m']) else "N/D")
    c2.metric("Balance de masa medio", f"{resumen['balance_medio_mm_we']:.0f} mm w.e.")
    c3.metric("SWE medio final", f"{resumen['swe_medio_final_mm']:.0f} mm")
    if pd.isna(resumen['ela_m']):
        st.caption(
            "ELA sin cruce de balance: todo el dominio (DEM del glaciar) gana o "
            "pierde masa de forma homogénea en el periodo simulado, sin una "
            "banda de elevación donde el balance cambie de signo."
        )
    st.caption(
        f"Parámetros: z_ref={resumen['z_ref_m']:.0f} m (elevación ERA5 del punto de "
        f"forzante) · lapse rate={resumen['lapse_rate']} °C/m · "
        f"ruteo k={resumen['route_k_dias']:.0f} días · balance de energía completo."
    )

    # ── Selector de estación y variable ─────────────────────────────────────
    col_a, col_b = st.columns(2)
    with col_a:
        estacion = st.selectbox(
            "Estación DGA", list(ESTACIONES.keys()),
            format_func=lambda c: f"{c} — {ESTACIONES[c]}",
            key="snowmelt_estacion"
        )
    with col_b:
        variable = st.selectbox(
            "Variable simulada", list(VARIABLES_SIM.keys()),
            format_func=lambda v: VARIABLES_SIM[v],
            key="snowmelt_variable"
        )

    sub_corr = corr[(corr["codigo_estacion"] == estacion)
                    & (corr["variable"] == variable)]
    if sub_corr.empty:
        st.info("Sin resultados de correlación para esta combinación.")
        st.stop()
    fila = sub_corr.iloc[0]

    joined = djf.merge(
        caudal[caudal["codigo_estacion"] == estacion],
        on="año", how="inner"
    ).dropna(subset=["caudal_djf_m3s"]).sort_values("año")

    def fmt_p(p):
        if p == 0 or abs(p) < 1e-6:
            return f"{p:.2e}" if p != 0 else "<1e-6"
        if abs(p) < 0.001:
            return f"{p:.2e}"
        return f"{p:.4f}"

    st.markdown("#### Resultados de la correlación de Pearson")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("N años", f"{fila['n']}")
    c2.metric("r (Pearson)", f"{fila['r']:.4f}")
    c3.metric("p-valor", fmt_p(fila['p_valor']))
    c4.metric("r detrended", f"{fila['r_detrended']:.4f}")
    c5.metric("p detrended", fmt_p(fila['p_detrended']))

    st.markdown("#### Simulado vs caudal observado")
    st.plotly_chart(_fig_scatter(joined, variable),
                     use_container_width=True, config={'displayModeBar': True})

    st.markdown("#### Serie temporal de doble eje")
    st.plotly_chart(_fig_serie(joined, variable),
                     use_container_width=True, config={'displayModeBar': True})

    st.markdown("#### Resultados por variable")
    col_map = {
        "variable": "Variable", "n": "N", "año_inicio": "Desde", "año_fin": "Hasta",
        "r": "r", "p_valor": "p", "r_detrended": "r detrended", "p_detrended": "p detrended",
    }
    tabla = corr[corr["codigo_estacion"] == estacion][list(col_map)].copy()
    tabla["variable"] = tabla["variable"].map(VARIABLES_TABLA)
    for col in ["p_valor", "p_detrended"]:
        tabla[col] = tabla[col].apply(fmt_p)
    st.dataframe(tabla.rename(columns=col_map), use_container_width=True, hide_index=True)

    st.markdown("#### Notas y limitaciones")
    st.markdown("""
    - **Esto complementa, no reemplaza**, la correlación NDSI↔caudal de la
      pestaña "Correlación DGA": son dos líneas de evidencia independientes
      (una estadística sobre el área satelital, otra física sobre el balance
      de masa simulado) que deberían apuntar en la misma dirección si el
      retroceso es real.
    - **Desajuste de escala**: el DEM de entrada cubre solo la extensión del
      glaciar (~9 km², el mismo AOI de la clasificación NDSI+DEM), no toda la
      cuenca del Río Yeso que efectivamente drena a las estaciones DGA. La
      variable `routed_djf_mm` (profundidad, mm) **no es comparable en
      magnitud absoluta** con el caudal DGA (m³/s de una cuenca mucho mayor)
      — la comparación válida es de **forma/anomalías interanuales**, no de
      magnitud, por eso se reporta como correlación y no como validación de
      caudal absoluto.
    - **Forzante**: temperatura y precipitación de un único punto (ERA5 vía
      Open-Meteo, centroide del AOI) extrapolado a cada celda por gradiente
      vertical fijo (lapse rate), sin estación local de validación ni
      downscaling topográfico. El propio `snowmelt-rs` documenta que el
      forzante sinóptico de punto único es su principal cuello de botella de
      precisión, no el detalle del terreno.
    - **r detrended** es la lectura más honesta: controla que ambas series
      tiendan a decrecer juntas por retroceso + sequía a lo largo de las
      décadas, igual que en la correlación NDSI↔caudal.
    """)
