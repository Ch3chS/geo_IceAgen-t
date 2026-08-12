import numpy as np
import pandas as pd
import pytest

from scripts import spatial_analysis as sa


class TestClasificarNdsi:
    def test_sobre_umbral_sin_dem_es_glaciar(self):
        ndsi = np.array([[0.5, 0.1]], dtype=np.float32)
        clasif = sa.clasificar_ndsi(ndsi)
        assert clasif[0, 0] == 1
        assert clasif[0, 1] == 0

    def test_nodata_se_preserva_como_255(self):
        ndsi = np.array([[sa.NODATA_IN, 0.5]], dtype=np.float32)
        clasif = sa.clasificar_ndsi(ndsi)
        assert clasif[0, 0] == sa.NODATA_OUT
        assert clasif[0, 1] == 1

    def test_nan_se_trata_como_nodata(self):
        ndsi = np.array([[np.nan, 0.5]], dtype=np.float32)
        clasif = sa.clasificar_ndsi(ndsi)
        assert clasif[0, 0] == sa.NODATA_OUT

    def test_filtro_dem_excluye_baja_altitud(self):
        ndsi = np.array([[0.5, 0.5]], dtype=np.float32)
        dem = np.array([[2000, 3500]], dtype=np.float32)
        clasif = sa.clasificar_ndsi(ndsi, dem=dem)
        assert clasif[0, 0] == 0  # NDSI alto pero bajo 3000 m -> descartado
        assert clasif[0, 1] == 1  # NDSI alto y sobre 3000 m -> glaciar

    def test_umbral_exacto_es_glaciar(self):
        ndsi = np.array([[sa.UMBRAL_NDSI]], dtype=np.float32)
        clasif = sa.clasificar_ndsi(ndsi)
        assert clasif[0, 0] == 1


class TestAñoDeNombre:
    def test_extrae_año_de_nombre_estandar(self):
        assert sa._año_de_nombre("landsat_ndsi_20230126.tif") == 2023

    def test_extrae_año_con_prefijo_clasif(self):
        assert sa._año_de_nombre("echaurren_clasif_20180215.tif") == 2018

    def test_sin_fecha_retorna_none(self):
        assert sa._año_de_nombre("archivo_sin_fecha.tif") is None

    def test_año_fuera_de_rango_retorna_none(self):
        assert sa._año_de_nombre("dato_19000101_x.tif") is None


class TestMediaMovilCentrada:
    def test_ventana_completa_en_el_centro(self):
        serie = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        mm = sa._media_movil_centrada(serie, ventana=3)
        assert mm.iloc[2] == pytest.approx(3.0)  # media de (2,3,4)

    def test_extremos_no_quedan_en_nan(self):
        serie = pd.Series([1.0, 2.0, 3.0])
        mm = sa._media_movil_centrada(serie, ventana=5)
        assert not mm.isna().any()


class TestConstruirSerieSensor:
    def _serie_sintetica(self):
        # Área glaciar decreciendo linealmente de 10 a 1 km² entre 1985 y 2024
        años = list(range(1985, 2025))
        areas = np.linspace(10.0, 1.0, num=len(años))
        return pd.DataFrame({"año": años, "area_km2": areas})

    def test_una_fila_por_año(self):
        gdf = self._serie_sintetica()
        serie = sa.construir_serie_sensor(gdf, "landsat")
        assert len(serie) == len(gdf)
        assert list(serie["año"]) == sorted(gdf["año"])

    def test_tendencia_negativa_para_serie_decreciente(self):
        gdf = self._serie_sintetica()
        serie = sa.construir_serie_sensor(gdf, "landsat")
        assert serie["tasa_lineal_km2_año"].iloc[0] < 0

    def test_delta_largo_plazo_usa_mediana_primer_quintil(self):
        gdf = self._serie_sintetica()
        serie = sa.construir_serie_sensor(gdf, "landsat")
        q = max(1, len(gdf) // 5)
        ref_esperada = gdf.sort_values("año")["area_km2"].iloc[:q].median()
        assert serie["area_ref_km2"].iloc[0] == pytest.approx(round(ref_esperada, 5))

    def test_decada_asignada_correctamente(self):
        gdf = self._serie_sintetica()
        serie = sa.construir_serie_sensor(gdf, "landsat")
        fila_1990 = serie[serie["año"] == 1990].iloc[0]
        assert fila_1990["decada"] == "1985-1994"

    def test_año_fuera_de_decadas_conocidas(self):
        gdf = pd.DataFrame({"año": [1970], "area_km2": [5.0]})
        serie = sa.construir_serie_sensor(gdf, "landsat")
        assert serie["decada"].iloc[0] == "fuera_rango"


class TestAnalisisDecadasSensor:
    def test_tendencia_perfectamente_lineal_r2_uno_y_significativa(self):
        años = list(range(1985, 1995))  # década completa 1985-1994, n=10
        areas = [10 - 0.5 * (a - 1985) for a in años]  # pendiente exacta -0.5
        serie = pd.DataFrame({"año": años, "area_total_km2": areas})
        resumen = sa.analisis_decadas_sensor(serie, "landsat")
        fila = resumen[resumen["decada"] == "1985-1994"].iloc[0]
        assert fila["tasa_km2_año"] == pytest.approx(-0.5, abs=1e-6)
        assert fila["r2"] == pytest.approx(1.0, abs=1e-6)
        assert fila["p_valor"] < 0.05

    def test_dos_puntos_r2_uno_sin_p_valor(self):
        serie = pd.DataFrame({"año": [1985, 1986], "area_total_km2": [10.0, 9.0]})
        resumen = sa.analisis_decadas_sensor(serie, "landsat")
        fila = resumen.iloc[0]
        assert fila["n_años"] == 2
        assert fila["r2"] == 1.0
        assert np.isnan(fila["p_valor"])

    def test_un_solo_punto_todo_nan(self):
        serie = pd.DataFrame({"año": [1985], "area_total_km2": [10.0]})
        resumen = sa.analisis_decadas_sensor(serie, "landsat")
        fila = resumen.iloc[0]
        assert fila["n_años"] == 1
        assert np.isnan(fila["tasa_km2_año"])

    def test_decada_sin_datos_no_aparece_en_el_resumen(self):
        serie = pd.DataFrame({"año": [1990], "area_total_km2": [5.0]})
        resumen = sa.analisis_decadas_sensor(serie, "landsat")
        assert set(resumen["decada"]) == {"1985-1994"}


class TestLeerCaudalDga:
    def _csv_temporal(self, tmp_path, filas):
        ruta = tmp_path / "caudal.csv"
        pd.DataFrame(filas).to_csv(ruta, index=False)
        return ruta

    def test_filtra_por_codigo_estacion(self, tmp_path):
        filas = [
            {"CODIGO ESTACION": "05703006", "Año": 2020, "Mes": 1, "Caudal_Medio_mensual": 1.5},
            {"CODIGO ESTACION": "05704002", "Año": 2020, "Mes": 1, "Caudal_Medio_mensual": 9.0},
        ]
        ruta = self._csv_temporal(tmp_path, filas)
        df = sa.leer_caudal_dga(ruta, codigo="05703006")
        assert len(df) == 1
        assert df.iloc[0]["Caudal_Medio_mensual"] == 1.5

    def test_codigo_con_ceros_a_la_izquierda_no_se_pierde(self, tmp_path):
        filas = [{"CODIGO ESTACION": "05703006", "Año": 2020, "Mes": 1, "Caudal_Medio_mensual": 1.5}]
        ruta = self._csv_temporal(tmp_path, filas)
        df = sa.leer_caudal_dga(ruta, codigo="05703006")
        assert len(df) == 1

    def test_estacion_inexistente_retorna_df_vacio_con_columnas(self, tmp_path):
        filas = [{"CODIGO ESTACION": "05703006", "Año": 2020, "Mes": 1, "Caudal_Medio_mensual": 1.5}]
        ruta = self._csv_temporal(tmp_path, filas)
        df = sa.leer_caudal_dga(ruta, codigo="99999999")
        assert df.empty
        assert list(df.columns) == ["Año", "Mes", "Caudal_Medio_mensual"]


class TestCaudalEstivalDjf:
    def _df(self, filas):
        return pd.DataFrame(filas, columns=["Año", "Mes", "Caudal_Medio_mensual"])

    def test_tres_meses_completos(self):
        df = self._df([
            {"Año": 1999, "Mes": 12, "Caudal_Medio_mensual": 3.0},
            {"Año": 2000, "Mes": 1, "Caudal_Medio_mensual": 6.0},
            {"Año": 2000, "Mes": 2, "Caudal_Medio_mensual": 9.0},
        ])
        assert sa.caudal_estival_djf(df, 2000) == pytest.approx(6.0)

    def test_dos_de_tres_meses_es_suficiente(self):
        df = self._df([
            {"Año": 2000, "Mes": 1, "Caudal_Medio_mensual": 4.0},
            {"Año": 2000, "Mes": 2, "Caudal_Medio_mensual": 8.0},
        ])
        assert sa.caudal_estival_djf(df, 2000) == pytest.approx(6.0)

    def test_un_solo_mes_retorna_nan(self):
        df = self._df([{"Año": 2000, "Mes": 1, "Caudal_Medio_mensual": 4.0}])
        assert np.isnan(sa.caudal_estival_djf(df, 2000))

    def test_diciembre_pertenece_al_año_anterior(self):
        df = self._df([
            {"Año": 1999, "Mes": 12, "Caudal_Medio_mensual": 3.0},
            {"Año": 2000, "Mes": 1, "Caudal_Medio_mensual": 6.0},
        ])
        # Si diciembre se asignara al año de la imagen en vez del anterior,
        # este promedio (u otro distinto) no daría 4.5.
        assert sa.caudal_estival_djf(df, 2000) == pytest.approx(4.5)


class TestResiduosDetrended:
    def test_serie_perfectamente_lineal_da_residuos_cero(self):
        x = [1985, 1986, 1987, 1988, 1989]
        y = [10.0, 9.0, 8.0, 7.0, 6.0]
        _, residuos = sa._residuos_detrended(x, y)
        assert np.allclose(residuos, 0.0, atol=1e-8)

    def test_menos_de_tres_puntos_retorna_nan(self):
        _, residuos = sa._residuos_detrended([1985, 1986], [10.0, 9.0])
        assert np.all(np.isnan(residuos))
