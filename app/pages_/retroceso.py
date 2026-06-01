import streamlit as st
import rasterio
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import re

DECADAS = [(1985, 1994), (1995, 2004), (2005, 2014), (2015, 2025)]


def run_retroceso():
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem; padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    st.subheader("Retroceso glaciar — Área y tasa de retroceso")
    st.caption("Etapa 4 | Filtro altitudinal FABDEM ≥ 3 000 m s.n.m.")

    BASE_DIR   = Path(__file__).resolve().parents[2]
    OUT_DIR    = BASE_DIR / "outputs"
    CLAS_DIR   = BASE_DIR / "data" / "processed" / "clasificacion"

    SERIE_LS   = OUT_DIR / "serie_temporal_landsat.csv"
    SERIE_S2   = OUT_DIR / "serie_temporal_sentinel2.csv"
    DECADAS_LS = OUT_DIR / "analisis_decadas_landsat.csv"
    DECADAS_S2 = OUT_DIR / "analisis_decadas_sentinel2.csv"

    faltantes = [p for p in [SERIE_LS, SERIE_S2] if not p.exists()]
    if faltantes:
        st.error(
            "No se encontraron los CSVs de series temporales. "
            "Ejecuta primero `scripts/analyze_glacier.py`.\n\n"
            + "\n".join(f"- `{p.name}`" for p in faltantes)
        )
        st.stop()

    @st.cache_data
    def cargar(path_str):
        return pd.read_csv(path_str)

    ls     = cargar(str(SERIE_LS))
    s2     = cargar(str(SERIE_S2))
    dec_ls = cargar(str(DECADAS_LS)) if DECADAS_LS.exists() else pd.DataFrame()
    dec_s2 = cargar(str(DECADAS_S2)) if DECADAS_S2.exists() else pd.DataFrame()

    # ── Selector de vista ────────────────────────────────────────────────────
    vista = st.radio(
        "Sensor", ("Landsat", "Sentinel-2", "Ambos"),
        horizontal=True, key="retro_vista"
    )

    # ============================================================
    # VISTA SENSOR ÚNICO
    # ============================================================
    if vista in ("Landsat", "Sentinel-2"):
        df     = ls.copy()     if vista == "Landsat" else s2.copy()
        color  = '#e07b39'     if vista == "Landsat" else '#1f6fe0'
        dec_df = dec_ls        if vista == "Landsat" else dec_s2
        año_ini = int(df['año'].iloc[0])
        año_fin = int(df['año'].iloc[-1])

        st.markdown("#### Serie temporal de área glaciar")
        st.caption(f"{vista} ({año_ini}–{año_fin})")

        x = np.array(df['año'],           dtype=float)
        y = np.array(df['area_total_km2'], dtype=float)

        # Métricas
        pend_val = np.polyfit(x, y, 1)[0] if len(x) >= 2 else float('nan')
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"Área {año_ini}",
                  f"{df['area_total_km2'].iloc[0]:.4f} km²")
        c2.metric(f"Área {año_fin}",
                  f"{df['area_total_km2'].iloc[-1]:.4f} km²")
        c3.metric("Tasa (regresión)", f"{pend_val:+.5f} km²/año")
        c4.metric("Cambio acumulado", f"{df['pct_cambio'].iloc[-1]:+.1f} %")

        # ── Gráfico 1: área glaciar ──────────────────────────────
        fig_area = go.Figure()
        fig_area.add_trace(go.Scatter(
            x=df['año'], y=df['area_total_km2'],
            mode='lines+markers', name='Área glaciar',
            line=dict(color=color),
            hovertemplate="%{x}: %{y:.4f} km²<extra></extra>"
        ))
        if len(x) >= 2:
            pend, inter = np.polyfit(x, y, 1)
            fig_area.add_trace(go.Scatter(
                x=df['año'], y=(pend * x + inter).tolist(),
                mode='lines', name='Tendencia',
                line=dict(color=color, dash='dash', width=1),
                hoverinfo='skip'
            ))
        if not dec_df.empty:
            dec_años = [int(d.split('-')[0]) for d in dec_df['decada']]
            fig_area.add_trace(go.Scatter(
                x=dec_años, y=dec_df['mediana_km2'].tolist(),
                mode='markers', name='Mediana década',
                marker=dict(color=color, size=13, symbol='diamond',
                            line=dict(color='black', width=1)),
                hovertemplate="%{x}s: mediana=%{y:.4f} km²<extra></extra>"
            ))
        fig_area.update_layout(
            xaxis_title="Año", yaxis_title="Área glaciar (km²)",
            margin=dict(l=0, r=0, t=10, b=0), height=360,
            legend=dict(orientation='h', yanchor='bottom', y=1.0,
                        xanchor='right', x=1)
        )
        st.plotly_chart(fig_area, use_container_width=True,
                        config={'displayModeBar': True})

        # ── Gráfico 2: delta acumulado (barras rojo/azul) ────────
        st.markdown("#### Delta acumulado respecto al año base")
        st.caption("Rojo = retroceso · Azul = avance")

        colores_bar = ['#d62728' if v < 0 else '#4575b4'
                       for v in df['delta_km2']]
        fig_delta = go.Figure(go.Bar(
            x=df['año'], y=df['delta_km2'],
            marker_color=colores_bar,
            hovertemplate="%{x}: Δ=%{y:+.4f} km²<extra></extra>"
        ))
        fig_delta.add_hline(y=0, line_color='black', line_width=0.8)
        fig_delta.update_layout(
            xaxis_title="Año", yaxis_title="Δ área glaciar (km²)",
            margin=dict(l=0, r=0, t=10, b=0), height=280,
            showlegend=False
        )
        st.plotly_chart(fig_delta, use_container_width=True,
                        config={'displayModeBar': False})

    # ============================================================
    # VISTA AMBOS
    # ============================================================
    else:
        st.markdown("#### Serie temporal de área glaciar")
        st.caption(
            "Landsat (1985–2026) y Sentinel-2 (2016–2024) como series independientes. "
            "El solapamiento 2016–2024 permite comparar ambos sensores directamente."
        )

        x_ls = np.array(ls['año'], dtype=float)
        y_ls = np.array(ls['area_total_km2'], dtype=float)
        x_s2 = np.array(s2['año'], dtype=float)
        y_s2 = np.array(s2['area_total_km2'], dtype=float)

        # ── Gráfico 1: área glaciar ambos sensores ───────────────
        fig_area = go.Figure()

        fig_area.add_trace(go.Scatter(
            x=ls['año'], y=ls['area_total_km2'],
            mode='lines+markers', name='Landsat',
            line=dict(color='#e07b39'),
            hovertemplate="%{x}: %{y:.4f} km²<extra>Landsat</extra>"
        ))
        if len(x_ls) >= 2:
            pend, inter = np.polyfit(x_ls, y_ls, 1)
            fig_area.add_trace(go.Scatter(
                x=ls['año'], y=(pend * x_ls + inter).tolist(),
                mode='lines', name='Tendencia LS',
                line=dict(color='#e07b39', dash='dash', width=1),
                hoverinfo='skip'
            ))

        fig_area.add_trace(go.Scatter(
            x=s2['año'], y=s2['area_total_km2'],
            mode='lines+markers', name='Sentinel-2',
            line=dict(color='#1f6fe0'),
            hovertemplate="%{x}: %{y:.4f} km²<extra>Sentinel-2</extra>"
        ))
        if len(x_s2) >= 2:
            pend, inter = np.polyfit(x_s2, y_s2, 1)
            fig_area.add_trace(go.Scatter(
                x=s2['año'], y=(pend * x_s2 + inter).tolist(),
                mode='lines', name='Tendencia S2',
                line=dict(color='#1f6fe0', dash='dash', width=1),
                hoverinfo='skip'
            ))

        if not dec_ls.empty:
            dec_años = [int(d.split('-')[0]) for d in dec_ls['decada']]
            fig_area.add_trace(go.Scatter(
                x=dec_años, y=dec_ls['mediana_km2'].tolist(),
                mode='markers', name='Mediana década (LS)',
                marker=dict(color='#e07b39', size=13, symbol='diamond',
                            line=dict(color='black', width=1)),
                hovertemplate="%{x}s: mediana=%{y:.4f} km²<extra>LS</extra>"
            ))

        fig_area.update_layout(
            xaxis_title="Año", yaxis_title="Área glaciar (km²)",
            margin=dict(l=0, r=0, t=10, b=0), height=420,
            legend=dict(orientation='h', yanchor='bottom', y=1.0,
                        xanchor='right', x=1)
        )
        st.plotly_chart(fig_area, use_container_width=True,
                        config={'displayModeBar': True})

        # Métricas lado a lado
        col_ls, col_s2 = st.columns(2)
        with col_ls:
            st.markdown("**Landsat**")
            c1, c2, c3 = st.columns(3)
            c1.metric(f"Área {int(ls['año'].iloc[0])}",
                      f"{ls['area_total_km2'].iloc[0]:.4f} km²")
            c2.metric(f"Área {int(ls['año'].iloc[-1])}",
                      f"{ls['area_total_km2'].iloc[-1]:.4f} km²")
            c3.metric("Cambio acumulado",
                      f"{ls['pct_cambio'].iloc[-1]:+.1f} %")
        with col_s2:
            st.markdown("**Sentinel-2**")
            c1, c2, c3 = st.columns(3)
            c1.metric(f"Área {int(s2['año'].iloc[0])}",
                      f"{s2['area_total_km2'].iloc[0]:.4f} km²")
            c2.metric(f"Área {int(s2['año'].iloc[-1])}",
                      f"{s2['area_total_km2'].iloc[-1]:.4f} km²")
            c3.metric("Cambio acumulado",
                      f"{s2['pct_cambio'].iloc[-1]:+.1f} %")

        # ── Gráfico 2: delta acumulado ambos sensores ────────────
        st.markdown("#### Delta acumulado respecto al año base de cada sensor")
        st.caption("Rojo = retroceso · Azul = avance")

        fig_delta = go.Figure()
        fig_delta.add_trace(go.Bar(
            x=ls['año'], y=ls['delta_km2'],
            name='Landsat',
            marker_color=['#d62728' if v < 0 else '#4575b4'
                          for v in ls['delta_km2']],
            hovertemplate="%{x}: Δ=%{y:+.4f} km²<extra>Landsat</extra>"
        ))
        fig_delta.add_trace(go.Bar(
            x=s2['año'], y=s2['delta_km2'],
            name='Sentinel-2',
            marker_color=['#d62728' if v < 0 else '#4575b4'
                          for v in s2['delta_km2']],
            hovertemplate="%{x}: Δ=%{y:+.4f} km²<extra>Sentinel-2</extra>"
        ))
        fig_delta.add_hline(y=0, line_color='black', line_width=0.8)
        fig_delta.update_layout(
            barmode='group',
            xaxis_title="Año", yaxis_title="Δ área glaciar (km²)",
            margin=dict(l=0, r=0, t=10, b=0), height=300,
            legend=dict(orientation='h', yanchor='bottom', y=1.0,
                        xanchor='right', x=1)
        )
        st.plotly_chart(fig_delta, use_container_width=True,
                        config={'displayModeBar': False})

    # ── Tabla de décadas (común a todas las vistas) ──────────────────────────
    dec_mostrar = {
        "Landsat":    dec_ls,
        "Sentinel-2": dec_s2,
        "Ambos":      pd.concat([dec_ls, dec_s2], ignore_index=True)
                      if not dec_ls.empty and not dec_s2.empty
                      else (dec_ls if not dec_ls.empty else dec_s2),
    }[vista]

    if not dec_mostrar.empty:
        st.markdown("#### Análisis por décadas (mediana)")
        st.caption(
            "La mediana es robusta a años con nevada atípica. "
            "La tasa es la pendiente de la regresión lineal interna a cada década."
        )
        st.dataframe(
            dec_mostrar.rename(columns={
                'sensor':       'Sensor',
                'decada':       'Década',
                'n_años':       'N años',
                'mediana_km2':  'Mediana (km²)',
                'tasa_km2_año': 'Tasa (km²/año)',
            }),
            use_container_width=True, hide_index=True
        )

    # ── Mapas de extensión por década ────────────────────────────────────────
    st.markdown("#### Mapas de extensión glaciar por década")

    @st.cache_data
    def cargar_clasif(ruta_str):
        with rasterio.open(ruta_str) as src:
            data = src.read(1).astype(float)
        data[data == 255] = np.nan
        return data

    @st.cache_data
    def rutas_por_año(dir_str):
        result = {}
        for p in Path(dir_str).glob("*.tif"):
            m = re.search(r'(\d{4})\d{4}', p.name)
            if m:
                result[int(m.group(1))] = str(p)
        return result

    sensor_mapa = (
        st.radio("Sensor para mapas", ("Landsat", "Sentinel-2"),
                 horizontal=True, key="retro_mapa_sensor")
        if vista == "Ambos" else vista
    )
    subdir  = "landsat" if sensor_mapa == "Landsat" else "sentinel2"
    rutas   = rutas_por_año(str(CLAS_DIR / subdir))
    serie_m = ls if sensor_mapa == "Landsat" else s2

    años_disp    = sorted(set(serie_m['año'].astype(int)) & set(rutas.keys()))
    años_muestra = []
    for ini, fin in DECADAS:
        candidatos = [a for a in años_disp if ini <= a <= fin]
        if candidatos:
            años_muestra.append(candidatos[len(candidatos) // 2])

    if años_muestra:
        cols     = st.columns(len(años_muestra))
        area_map = dict(zip(serie_m['año'].astype(int),
                            serie_m['area_total_km2']))
        for col, año in zip(cols, años_muestra):
            clas = cargar_clasif(rutas[año])
            mini = px.imshow(
                clas,
                color_continuous_scale=[[0.0, '#8c6d4f'], [1.0, '#1f6fe0']],
                zmin=0, zmax=1, origin='upper', aspect='equal'
            )
            mini.update_layout(
                coloraxis_showscale=False,
                margin=dict(l=0, r=0, t=0, b=0), height=160
            )
            mini.update_xaxes(visible=False)
            mini.update_yaxes(visible=False)
            col.markdown(f"**{año}** · {area_map.get(año, 0):.4f} km²")
            col.plotly_chart(mini, use_container_width=True,
                             config={'displayModeBar': False})
    else:
        st.info("No hay clasificaciones disponibles para las décadas seleccionadas.")

    st.caption("🔵 glaciar · 🟤 roca/suelo")