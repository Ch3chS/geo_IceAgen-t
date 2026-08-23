import pandas as pd
import pytest

from scripts import validar_dga as vd


class TestCalcularDiscrepancias:
    def _serie(self):
        return pd.DataFrame({
            'año': [2020, 2021, 2022],
            'area_total_km2': [0.30, 0.20, 0.10],
        })

    def test_una_fila_por_año(self):
        tabla = vd.calcular_discrepancias(self._serie(), area_dga_km2=0.20, sensor='landsat')
        assert len(tabla) == 3
        assert list(tabla['sensor'].unique()) == ['landsat']

    def test_diff_positivo_es_sobreestimacion(self):
        tabla = vd.calcular_discrepancias(self._serie(), area_dga_km2=0.20, sensor='landsat')
        fila_2020 = tabla[tabla['año'] == 2020].iloc[0]
        assert fila_2020['diff_km2'] == pytest.approx(0.10)
        assert fila_2020['abs_diff_km2'] == pytest.approx(0.10)

    def test_diff_negativo_es_subestimacion(self):
        tabla = vd.calcular_discrepancias(self._serie(), area_dga_km2=0.20, sensor='landsat')
        fila_2022 = tabla[tabla['año'] == 2022].iloc[0]
        assert fila_2022['diff_km2'] == pytest.approx(-0.10)
        assert fila_2022['abs_diff_km2'] == pytest.approx(0.10)

    def test_diff_pct_relativo_a_referencia_dga(self):
        tabla = vd.calcular_discrepancias(self._serie(), area_dga_km2=0.20, sensor='landsat')
        fila_2020 = tabla[tabla['año'] == 2020].iloc[0]
        assert fila_2020['diff_pct'] == pytest.approx(50.0)


class TestResumenPorSensor:
    def _tabla_dos_sensores(self):
        landsat = vd.calcular_discrepancias(
            pd.DataFrame({'año': [2020, 2021], 'area_total_km2': [0.40, 0.30]}),
            area_dga_km2=0.20, sensor='landsat')
        sentinel = vd.calcular_discrepancias(
            pd.DataFrame({'año': [2019, 2022], 'area_total_km2': [0.25, 0.22]}),
            area_dga_km2=0.20, sensor='sentinel2')
        return pd.concat([landsat, sentinel], ignore_index=True)

    def test_una_fila_por_sensor(self):
        resumen = vd.resumen_por_sensor(self._tabla_dos_sensores(), año_referencia=2022)
        assert set(resumen['sensor']) == {'landsat', 'sentinel2'}
        assert len(resumen) == 2

    def test_mae_es_media_de_abs_diff(self):
        resumen = vd.resumen_por_sensor(self._tabla_dos_sensores(), año_referencia=2022)
        fila = resumen[resumen['sensor'] == 'landsat'].iloc[0]
        # diffs: 0.40-0.20=0.20, 0.30-0.20=0.10 -> MAE = 0.15
        assert fila['mae_km2'] == pytest.approx(0.15)

    def test_sesgo_medio_conserva_signo(self):
        resumen = vd.resumen_por_sensor(self._tabla_dos_sensores(), año_referencia=2022)
        fila = resumen[resumen['sensor'] == 'landsat'].iloc[0]
        # sesgo medio = (0.20 + 0.10) / 2 = 0.15 (sobreestima)
        assert fila['sesgo_medio_km2'] == pytest.approx(0.15)

    def test_año_mas_cercano_cuando_no_hay_coincidencia_exacta(self):
        resumen = vd.resumen_por_sensor(self._tabla_dos_sensores(), año_referencia=2022)
        fila = resumen[resumen['sensor'] == 'landsat'].iloc[0]
        # landsat no tiene 2022; el más cercano entre 2020/2021 es 2021
        assert fila['año_mas_cercano'] == 2021

    def test_año_mas_cercano_con_coincidencia_exacta(self):
        resumen = vd.resumen_por_sensor(self._tabla_dos_sensores(), año_referencia=2022)
        fila = resumen[resumen['sensor'] == 'sentinel2'].iloc[0]
        assert fila['año_mas_cercano'] == 2022
