import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import sys

BASE_DIR_APP = Path(__file__).resolve().parents[2]
if str(BASE_DIR_APP) not in sys.path:
    sys.path.insert(0, str(BASE_DIR_APP))
from scripts.glacier_config import get_config  # noqa: E402


def _fig_scatter(joined, var, estacion_nombre):
    """Scatter área glaciar vs caudal estival DJF con recta de regresión."""
    glac = joined[var]
    caud = joined["caudal_djf_m3s"]
    pend, inter = np.polyfit(glac, caud, 1)
    xline = np.linspace(glac.min(), glac.max(), 50)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=glac, y=caud, mode='markers', name='Años',
        marker=dict(size=10, color='#1f6fe0',
                    line=dict(color='black', width=0.6)),
        text=[f"{a}" for a in joined['año']], hovertemplate=
        "%{text} · área=%{x:.4f} km² · caudal=%{y:.4f} m³/s<extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=xline, y=pend * xline + inter, mode='lines',
        name='Regresión lineal',
        line=dict(color='#d62728', dash='dash')
    ))
    fig.update_layout(
        xaxis_title="Área glaciar (km²)",
        yaxis_title="Caudal estival DJF (m³/s)",
        margin=dict(l=0, r=0, t=10, b=0), height=420,
        legend=dict(orientation='h', yanchor='bottom', y=1.0,
                    xanchor='right', x=1)
    )
    return fig


def _fig_serie(joined, var, estacion_nombre):
    """Serie temporal de doble eje: área glaciar y caudal estival."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=joined['año'], y=joined[var], mode='lines+markers',
        name='Área glaciar', line=dict(color='#1f6fe0'),
        hovertemplate="%{x}: %{y:.4f} km²<extra>Área</extra>",
        yaxis='y1'
    ))
    fig.add_trace(go.Scatter(
        x=joined['año'], y=joined['caudal_djf_m3s'], mode='lines+markers',
        name='Caudal DJF', line=dict(color='#d62728'),
        hovertemplate="%{x}: %{y:.4f} m³/s<extra>Caudal</extra>",
        yaxis='y2'
    ))
    fig.update_layout(
        xaxis_title="Año",
        yaxis=dict(title="Área glaciar (km²)", color='#1f6fe0'),
        yaxis2=dict(title="Caudal estival DJF (m³/s)", color='#d62728',
                    overlaying='y', side='right'),
        margin=dict(l=0, r=0, t=10, b=0), height=380,
        legend=dict(orientation='h', yanchor='bottom', y=1.0,
                    xanchor='right', x=1)
    )
    return fig


def run_correlacion(glaciar=None):
    glaciar = glaciar or get_config("echaurren")
    estaciones = glaciar.dga_estaciones
    st.markdown("""
        <style>
            .reportview-container .main .block-container {
                padding-top: 1rem; padding-bottom: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    st.subheader("Correlación área glaciar — caudal DGA")
    st.caption(
        f"Etapa 5 | {glaciar.nombre} | "
        "Correlación de Pearson entre el área glaciar del pipeline y "
        "el caudal estival (DJF) de la DGA, alineados al mismo año hidrológico."
    )

    BASE_DIR = Path(__file__).resolve().parents[2]
    OUT_DIR  = BASE_DIR / "outputs" / glaciar.slug

    SERIE   = OUT_DIR / "serie_temporal_landsat.csv"
    CAUDAL  = OUT_DIR / "caudal_dga_djf.csv"
    CORR    = OUT_DIR / "correlacion_pearson.csv"

    faltantes = [p for p in [SERIE, CAUDAL, CORR] if not p.exists()]
    if faltantes:
        st.error(
            "No se encontraron los archivos de la Etapa 5. "
            "Ejecuta primero `scripts/spatial_analysis.py`.\n\n"
            + "\n".join(f"- `{p.name}`" for p in faltantes)
        )
        st.stop()

    @st.cache_data
    def cargar(path_str, mtime):
        return pd.read_csv(path_str)

    @st.cache_data
    def cargar_estacion(path_str, mtime):
        # El código de estación tiene ceros a la izquierda (p. ej. 05703006);
        # debe leerse como texto para no perderlos.
        return pd.read_csv(path_str, dtype={"codigo_estacion": str})

    # El mtime entra en la clave de cache: si el CSV cambió (p. ej. al
    # re-ejecutar spatial_analysis.py), se recarga en lugar de servir el viejo.
    serie  = cargar(str(SERIE),  SERIE.stat().st_mtime)
    caudal = cargar_estacion(str(CAUDAL), CAUDAL.stat().st_mtime)
    corr   = cargar_estacion(str(CORR),   CORR.stat().st_mtime)

    # ── Selector de estación ────────────────────────────────────────────────
    estacion = st.selectbox(
        "Estación DGA",
        list(estaciones.keys()),
        format_func=lambda c: f"{c} — {estaciones[c]}",
        key="corr_estacion"
    )

    sub_corr = corr[corr["codigo_estacion"] == estacion]
    if sub_corr.empty:
        st.info("Sin resultados de correlación para esta estación.")
        st.stop()

    joined = serie.merge(
        caudal[caudal["codigo_estacion"] == estacion],
        on="año", how="inner"
    ).dropna(subset=["caudal_djf_m3s"]).sort_values("año")

    # ── Métricas de correlación ─────────────────────────────────────────────
    fila = sub_corr[sub_corr["variable"] == "area_total_km2"].iloc[0]

    def fmt_p(p):
        """Formatea p-valor: notación científica si es muy pequeño."""
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

    st.caption(
        "r detrended: correlación sobre los residuos tras eliminar la tendencia "
        "temporal de ambas series. Controla el riesgo de correlación espuria "
        "porque área y caudal co-decrecen a lo largo de las décadas."
    )

    # ── Robustez: Maipo restringido a años con estero ───────────────────────
    sub_rob = corr[(corr["codigo_estacion"] == estacion)
                   & (corr["subperiodo"] == "solape_estero")]
    if estacion == "05704002" and not sub_rob.empty:
        fila_rob = sub_rob[sub_rob["variable"] == "area_total_km2"].iloc[0]
        st.warning(
            f"**Robustez — mismo subperiodo que el estero**: "
            f"restringiendo el Maipo a los {fila_rob['n']} años con caudal del "
            f"estero (1985–2004), r={fila_rob['r']:.4f} (p={fmt_p(fila_rob['p_valor'])}). "
            "La correlación fuerte del Maipo NO se explica por el mayor periodo "
            "muestreado ni por un mayor n."
        )

    # ── Scatter con regresión ───────────────────────────────────────────────
    st.markdown("#### Área glaciar vs caudal estival")
    st.caption(
        f"Variable: área glaciar total (km²) · {estaciones[estacion]} · "
        f"{int(fila['año_inicio'])}–{int(fila['año_fin'])}"
    )
    st.plotly_chart(
        _fig_scatter(joined, "area_total_km2", estaciones[estacion]),
        use_container_width=True, config={'displayModeBar': True}
    )

    # ── Serie de doble eje ──────────────────────────────────────────────────
    st.markdown("#### Serie temporal de doble eje")
    st.caption(
        "Alineación: la imagen de ~26 de enero del año A corresponde al caudal "
        "DJF del mismo verano (dic A−1 + ene A + feb A)."
    )
    st.plotly_chart(
        _fig_serie(joined, "area_total_km2", estaciones[estacion]),
        use_container_width=True, config={'displayModeBar': True}
    )

    # ── Tabla de resultados ─────────────────────────────────────────────────
    st.markdown("#### Resultados por variable")
    col_map = {
        "variable":        "Variable",
        "n":               "N",
        "año_inicio":      "Desde",
        "año_fin":         "Hasta",
        "r":               "r",
        "p_valor":         "p",
        "r_detrended":     "r detrended",
        "p_detrended":     "p detrended",
        "subperiodo":      "Subperiodo",
    }
    tabla = sub_corr[[c for c in col_map if c in sub_corr.columns]].copy()
    tabla["subperiodo"] = tabla["subperiodo"].map(
        {"completo": "Completo",
         "solape_estero": "Solo años con estero"})
    for col in ["p_valor", "p_detrended"]:
        if col in tabla.columns:
            tabla[col] = tabla[col].apply(fmt_p)
    st.dataframe(tabla.rename(columns=col_map),
                 use_container_width=True, hide_index=True)

    # ── Nota metodológica ───────────────────────────────────────────────────
    st.markdown("#### Notas y limitaciones")
    codigos = list(estaciones.keys())
    directa = codigos[0] if codigos else None
    integradora = codigos[1] if len(codigos) > 1 else None
    notas = []
    if directa:
        notas.append(
            f"- **{estaciones[directa]} ({directa})**: estación de la cuenca del "
            f"glaciar — señal hidrológicamente directa de su drenaje."
        )
    if integradora:
        notas.append(
            f"- **{estaciones[integradora]} ({integradora})**: estación integradora "
            f"aguas abajo de la cuenca; extiende el solapamiento temporal con Landsat."
        )
    notas += [
        "- **Interpretación crítica**: el área NDSI de ~26 de enero captura **nieve "
        "transitoria**, no solo hielo glaciar permanente. En años húmedos hay más "
        "nieve acumulada → área NDSI inflada Y más escorrentía estival. Por eso la "
        "correlación puede reflejar la co-variación **nieve↔escorrentía del mismo "
        "año hidrológico**, no la contribución del derretimiento glaciar.",
        "- **Vacío de cobertura**: si la estación de la cuenca correcta no está "
        "disponible en el periodo de Sentinel-2, no es posible correlacionar "
        "Sentinel-2 con el caudal de la cuenca correcta.",
        "- La correlación **detrended** es la interpretable: elimina el efecto de que "
        "ambas series tienden a decrecer juntas por retroceso + sequía.",
    ]
    st.markdown("\n".join(notas))
