import numpy as np
import pandas as pd
import pytest

from scripts import run_snowmelt as rs


class TestAñoHidrologicoDjf:
    def test_diciembre_pertenece_al_año_siguiente(self):
        assert rs._año_hidrologico_djf(pd.Timestamp("2020-12-15")) == 2021

    def test_enero_y_febrero_pertenecen_al_mismo_año(self):
        assert rs._año_hidrologico_djf(pd.Timestamp("2021-01-10")) == 2021
        assert rs._año_hidrologico_djf(pd.Timestamp("2021-02-20")) == 2021

    def test_mes_fuera_de_djf_retorna_none(self):
        assert rs._año_hidrologico_djf(pd.Timestamp("2021-06-01")) is None


class TestAgregarDjfSerie:
    def _serie_diaria(self, año, meses=(12, 1, 2), dias_por_mes=28):
        """Construye una serie diaria sintética cubriendo dic(año-1) +
        ene/feb(año), con melt_mm=1.0 y swe_mm=10.0 constantes por día."""
        fechas = []
        for mes in meses:
            y = año - 1 if mes == 12 else año
            fechas += list(pd.date_range(f"{y}-{mes:02d}-01", periods=dias_por_mes, freq="D"))
        return pd.DataFrame({
            "date": [f.strftime("%Y-%m-%d") for f in fechas],
            "melt_mm": 1.0,
            "runoff_mm": 0.5,
            "routed_mm": 0.4,
            "swe_mm": 10.0,
        })

    def test_una_fila_por_año_con_cobertura_suficiente(self):
        df = self._serie_diaria(2020)
        djf = rs._agregar_djf_serie(df, min_dias=10)
        assert len(djf) == 1
        assert djf.iloc[0]["año"] == 2020

    def test_variables_de_flujo_se_suman(self):
        df = self._serie_diaria(2020, dias_por_mes=10)
        djf = rs._agregar_djf_serie(df, min_dias=10)
        n_dias = 30  # 3 meses x 10 días
        assert djf.iloc[0]["melt_djf_mm"] == pytest.approx(1.0 * n_dias)
        assert djf.iloc[0]["n_dias"] == n_dias

    def test_variables_de_estado_se_promedian(self):
        df = self._serie_diaria(2020)
        djf = rs._agregar_djf_serie(df, min_dias=10)
        assert djf.iloc[0]["swe_mm_djf_medio"] == pytest.approx(10.0)

    def test_año_con_poca_cobertura_se_descarta(self):
        df = self._serie_diaria(2020, dias_por_mes=5)  # 15 días < min_dias
        djf = rs._agregar_djf_serie(df, min_dias=60)
        assert djf.empty


class TestCentroideAoiWgs84:
    def test_centroide_cae_en_chile_central(self):
        lon, lat = rs._centroide_aoi_wgs84()
        # El AOI del glaciar Echaurren Norte está en la cuenca del Yeso,
        # Región Metropolitana, Chile central.
        assert -71 < lon < -70
        assert -34 < lat < -33


class TestParsearResumenStdout:
    def test_extrae_ela_balance_y_swe(self):
        texto = (
            "Simulación completada: 100 pasos diarios\n"
            "  ELA estimada        : 4300 m\n"
            "  balance de masa     : out/mass_balance.asc (medio -120.5 mm w.e.)\n"
            "  SWE medio final     : 85.2 mm\n"
        )
        resumen = rs._parsear_resumen_stdout(texto)
        assert resumen["ela_m"] == pytest.approx(4300.0)
        assert resumen["balance_medio_mm_we"] == pytest.approx(-120.5)
        assert resumen["swe_medio_final_mm"] == pytest.approx(85.2)

    def test_sin_cruce_de_balance_deja_ela_nan(self):
        texto = (
            "  ELA estimada        : sin cruce de balance "
            "(toda la cuenca gana o pierde masa)\n"
            "  SWE medio final     : 10.0 mm\n"
        )
        resumen = rs._parsear_resumen_stdout(texto)
        assert np.isnan(resumen["ela_m"])
        assert resumen["swe_medio_final_mm"] == pytest.approx(10.0)
