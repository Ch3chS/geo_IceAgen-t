import streamlit as st
import rasterio
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import re

DECADAS = [(1985, 1994), (1995, 2004), (2005, 2014), (2015, 2025)]

# Patrón de fecha consistente con spatial_analysis.py
_RE_FECHA_NOMBRE = re.compile(r'(?:^|_)(\d{4})(\d{2})(\d{2})(?:_|\.)')


def _año_de_ruta(nombre: str):
    """Extrae año de un nombre de archivo con _YYYYMMDD_."""
    m = _RE_FECHA_NOMBRE.search(nombre)
    return int(m.group(1)) if m and 1972 <= int(m.group(1)) <= 2100 else None


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
    # HELPER: gráfico de área con tendencia lineal precalculada
    # (sin media móvil)
    # ============================================================
    def _fig_area(df, dec_df, color, label):
        """Gráfico de área glaciar con puntos observados, tendencia lineal global
        (calculada en spatial_analysis.py) y medianas por década."""
        fig = go.Figure()

        # Serie principal
        fig.add_trace(go.Scatter(
            x=df['año'], y=df['area_total_km2'],
            mode='lines+markers', name=label,
            line=dict(color=color),
            hovertemplate="%{x}: %{y:.4f} km²<extra></extra>"
        ))

        # Tendencia lineal global (precalculada en el CSV)
        if 'tasa_lineal_km2_año' in df.columns and len(df) >= 2:
            pend = df['tasa_lineal_km2_año'].iloc[0]
            inter = df['area_tendencia_inicio_km2'].iloc[0] - pend * df['año'].iloc[0]
            y_tend = pend * df['año'].values + inter
            fig.add_trace(go.Scatter(
                x=df['año'], y=y_tend,
                mode='lines', name='Tendencia lineal',
                line=dict(color=color, dash='dash', width=1),
                hoverinfo='skip'
            ))

        # Medianas de décadas
        if not dec_df.empty:
            dec_años = [int(d.split('-')[0]) for d in dec_df['decada']]
            fig.add_trace(go.Scatter(
                x=dec_años, y=dec_df['mediana_km2'].tolist(),
                mode='markers', name='Mediana década',
                marker=dict(color=color, size=13, symbol='diamond',
                            line=dict(color='black', width=1)),
                hovertemplate="%{x}s: mediana=%{y:.4f} km²<extra></extra>"
            ))

        fig.update_layout(
            xaxis_title="Año", yaxis_title="Área glaciar (km²)",
            margin=dict(l=0, r=0, t=10, b=0), height=380,
            legend=dict(orientation='h', yanchor='bottom', y=1.0,
                        xanchor='right', x=1)
        )
        return fig

    # ============================================================
    # HELPER: gráfico de delta (barras rojo/azul)
    # ============================================================
    def _fig_delta(df, color, label):
        """Cambio acumulado respecto al año base (delta_largo_plazo_km2)."""
        col_delta = 'delta_largo_plazo_km2'
        colores_bar = ['#d62728' if v < 0 else '#4575b4' for v in df[col_delta]]
        fig = go.Figure(go.Bar(
            x=df['año'], y=df[col_delta],
            marker_color=colores_bar,
            hovertemplate="%{x}: Δ=%{y:+.4f} km²<extra></extra>"
        ))
        fig.add_hline(y=0, line_color='black', line_width=0.8)
        fig.update_layout(
            xaxis_title="Año",
            yaxis_title="Δ área glaciar (km²)",
            margin=dict(l=0, r=0, t=10, b=0), height=280,
            showlegend=False
        )
        return fig

    # ============================================================
    # VISTA SENSOR ÚNICO
    # ============================================================
    if vista in ("Landsat", "Sentinel-2"):
        df = ls.copy() if vista == "Landsat" else s2.copy()
        color = '#e07b39' if vista == "Landsat" else '#1f6fe0'
        dec_df = dec_ls if vista == "Landsat" else dec_s2
        año_ini = int(df['año'].iloc[0])
        año_fin = int(df['año'].iloc[-1])

        # Leer métricas robustas precalculadas por spatial_analysis.py
        area_ini_tend = df['area_tendencia_inicio_km2'].iloc[0]
        area_fin_tend = df['area_tendencia_fin_km2'].iloc[0]
        tasa = df['tasa_lineal_km2_año'].iloc[0]
        cambio_pct = df['cambio_tendencia_pct'].iloc[0]

        st.markdown("#### Serie temporal de área glaciar")
        st.caption(f"{vista} ({año_ini}–{año_fin})")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Área inicio (tend.)", f"{area_ini_tend:.4f} km²",
                  help="Valor estimado por regresión lineal en el primer año de la serie")
        c2.metric("Área fin (tend.)",   f"{area_fin_tend:.4f} km²",
                  help="Valor estimado por regresión lineal en el último año")
        c3.metric("Tasa (regresión lineal)", f"{tasa:+.5f} km²/año",
                  help="Pendiente de la recta de tendencia global")
        c4.metric("Cambio acumulado (tend.)", f"{cambio_pct:+.1f} %",
                  help="(área final tendencia − área inicial tendencia) / área inicial tendencia")

        st.plotly_chart(
            _fig_area(df, dec_df, color, vista),
            use_container_width=True, config={'displayModeBar': True}
        )

        st.markdown("#### Delta acumulado y anomalía interanual")
        st.caption(
            "Barras: cambio acumulado respecto al año base (largo plazo). "
            "Línea: desviación respecto a la media móvil de 5 años (anomalía interanual)."
        )
        st.plotly_chart(
            _fig_delta(df, color, vista),
            use_container_width=True, config={'displayModeBar': False}
        )

    # ============================================================
    # VISTA AMBOS SENSORES
    # ============================================================
    else:
        st.markdown("#### Serie temporal de área glaciar")
        st.caption(
            "Landsat (1985–2026) y Sentinel-2 (2016–2024) como series independientes. "
            "El solapamiento 2016–2024 permite comparar ambos sensores directamente."
        )
        
        # Métricas lado a lado usando tendencia precalculada
        col_ls, col_s2 = st.columns(2)
        for col_ui, df, label in [(col_ls, ls, "Landsat"),
                                   (col_s2, s2, "Sentinel-2")]:
            with col_ui:
                st.markdown(f"**{label}**")
                area_ini = df['area_tendencia_inicio_km2'].iloc[0]
                area_fin = df['area_tendencia_fin_km2'].iloc[0]
                cambio = df['cambio_tendencia_pct'].iloc[0]
                tasa = df['tasa_lineal_km2_año'].iloc[0]
                c1, c2, c3 = st.columns(3)
                c1.metric("Área inicio (tend.)", f"{area_ini:.4f} km²")
                c2.metric("Área fin (tend.)",   f"{area_fin:.4f} km²")
                c3.metric("Cambio acumulado",   f"{cambio:+.1f} %")
                st.caption(f"Tasa: {tasa:+.5f} km²/año")

        fig_area = go.Figure()

        for df, color, label, dec_df in [
            (ls, '#e07b39', 'Landsat', dec_ls),
            (s2, '#1f6fe0', 'Sentinel-2', dec_s2),
        ]:
            # Serie observada
            fig_area.add_trace(go.Scatter(
                x=df['año'], y=df['area_total_km2'],
                mode='lines+markers', name=label,
                line=dict(color=color),
                hovertemplate=f"%{{x}}: %{{y:.4f}} km²<extra>{label}</extra>"
            ))
            # Tendencia lineal precalculada
            if 'tasa_lineal_km2_año' in df.columns and len(df) >= 2:
                pend = df['tasa_lineal_km2_año'].iloc[0]
                inter = df['area_tendencia_inicio_km2'].iloc[0] - pend * df['año'].iloc[0]
                y_tend = pend * df['año'].values + inter
                fig_area.add_trace(go.Scatter(
                    x=df['año'], y=y_tend,
                    mode='lines', name=f'Tendencia {label}',
                    line=dict(color=color, dash='dash', width=1),
                    hoverinfo='skip'
                ))
            # Medianas por década
            if not dec_df.empty:
                dec_años = [int(d.split('-')[0]) for d in dec_df['decada']]
                fig_area.add_trace(go.Scatter(
                    x=dec_años, y=dec_df['mediana_km2'].tolist(),
                    mode='markers', name=f'Mediana {label}',
                    marker=dict(color=color, size=13, symbol='diamond',
                                line=dict(color='black', width=1)),
                    hovertemplate=f"%{{x}}s: mediana=%{{y:.4f}} km²<extra>{label}</extra>"
                ))

        fig_area.update_layout(
            xaxis_title="Año", yaxis_title="Área glaciar (km²)",
            margin=dict(l=0, r=0, t=10, b=0), height=420,
            legend=dict(orientation='h', yanchor='bottom', y=1.0,
                        xanchor='right', x=1)
        )
        st.plotly_chart(fig_area, use_container_width=True,
                        config={'displayModeBar': True})

        # Delta ambos sensores
        st.markdown("#### Delta acumulado y anomalía interanual")
        st.caption(
            "Barras: cambio acumulado respecto al año base de cada sensor. "
            "Línea: anomalía respecto a la media móvil de 5 años."
        )
        for df, color, label in [
            (ls, '#e07b39', 'Landsat'),
            (s2, '#1f6fe0', 'Sentinel-2'),
        ]:
            st.markdown(f"**{label}**")
            st.plotly_chart(
                _fig_delta(df, color, label),
                use_container_width=True, config={'displayModeBar': False}
            )

    # ── Tabla de décadas ─────────────────────────────────────────────────────
    dec_mostrar = {
        "Landsat":    dec_ls,
        "Sentinel-2": dec_s2,
        "Ambos":      pd.concat([dec_ls, dec_s2], ignore_index=True)
                      if not dec_ls.empty and not dec_s2.empty
                      else (dec_ls if not dec_ls.empty else dec_s2),
    }[vista]

    if not dec_mostrar.empty:
        st.markdown("#### Análisis por décadas")
        st.caption(
            "Mediana robusta a años atípicos. "
            "Tasa = pendiente de regresión lineal interna a cada década. "
            "✓ = p < 0.05 (significativo)."
        )

        # Seleccionar y renombrar columnas según disponibilidad
        col_map = {
            'sensor':        'Sensor',
            'decada':        'Década',
            'n_años':        'N años',
            'mediana_km2':   'Mediana (km²)',
            'tasa_km2_año':  'Tasa (km²/año)',
            'r2':            'R²',
            'p_valor':       'p-valor',
            'ic95_inf':      'IC95 inf.',
            'ic95_sup':      'IC95 sup.',
        }
        cols_presentes = [c for c in col_map if c in dec_mostrar.columns]
        tabla = dec_mostrar[cols_presentes].rename(columns=col_map).copy()

        # Marcar significancia visualmente
        if 'p-valor' in tabla.columns:
            tabla['sig.'] = tabla['p-valor'].apply(
                lambda p: '✓' if (pd.notna(p) and p < 0.05) else '–'
            )

        st.dataframe(tabla, use_container_width=True, hide_index=True)

    # ── Mapas de extensión por década ────────────────────────────────────────
    st.markdown("#### Mapas de extensión glaciar por década")
    st.caption("🔵 glaciar · 🟤 roca/suelo")

    @st.cache_data
    def cargar_clasif(ruta_str):
        with rasterio.open(ruta_str) as src:
            data = src.read(1).astype(float)
        data[data == 255] = np.nan
        return data

    @st.cache_data
    def rutas_por_año(dir_str):
        """Extrae año de cada .tif usando el mismo patrón que spatial_analysis.py."""
        result = {}
        for p in Path(dir_str).glob("*.tif"):
            año = _año_de_ruta(p.name)
            if año is not None:
                result[año] = str(p)
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