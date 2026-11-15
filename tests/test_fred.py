import pytest
import responses
from responses import matchers

from briefing.fuentes import fred
from briefing.fuentes.fred import FredApiKeyFaltante, SinObservaciones

URL = "https://api.stlouisfed.org/fred/series/observations"


@pytest.fixture(autouse=True)
def clave_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "clave-de-prueba")


def _mock_serie(serie: str, fecha: str, valor: str, **params_extra: str) -> None:
    responses.add(
        responses.GET,
        URL,
        json={"observations": [{"date": fecha, "value": valor}]},
        status=200,
        match=[
            matchers.query_param_matcher(
                {"series_id": serie, **params_extra}, strict_match=False
            )
        ],
    )


@responses.activate
def test_tipo_fed() -> None:
    _mock_serie("FEDFUNDS", "2026-09-01", "4.5")

    dato = fred.tipo_fed()

    assert dato.valor == 4.5
    assert dato.unidad == "% anual"
    assert dato.fuente == "FRED"


@responses.activate
def test_ipc_eeuu_pide_la_variacion_interanual() -> None:
    _mock_serie("CPIAUCSL", "2026-09-01", "2.8", units="pc1")

    dato = fred.ipc_eeuu()

    assert dato.valor == 2.8
    assert dato.unidad == "% interanual"


@responses.activate
def test_sp500() -> None:
    _mock_serie("SP500", "2026-10-03", "7700.5")

    dato = fred.sp500()

    assert dato.valor == 7700.5
    assert dato.unidad == "puntos"


@responses.activate
def test_brent() -> None:
    _mock_serie("DCOILBRENTEU", "2026-10-03", "82.1")

    dato = fred.brent()

    assert dato.valor == 82.1
    assert dato.unidad == "USD/barril"


@responses.activate
def test_valor_vacio_lanza_error_explicito() -> None:
    responses.add(
        responses.GET,
        URL,
        json={"observations": [{"date": "2026-09-01", "value": "."}]},
        status=200,
    )

    with pytest.raises(SinObservaciones):
        fred.tipo_fed()


@responses.activate
def test_retrocede_hasta_encontrar_un_valor_real() -> None:
    # Hallazgo real (noviembre de 2026): CPIAUCSL con units=pc1 devolvía "."
    # para octubre de 2026 porque el índice de octubre de 2025 (necesario
    # para la comparación interanual) nunca se publicó por el cierre del
    # Gobierno de EE. UU. — no es un hueco de un día, dura hasta que sale el
    # dato de noviembre. FRED devuelve las observaciones más recientes
    # primero (sort_order=desc); la más antigua con valor real es la que se
    # debe usar, con su fecha real.
    responses.add(
        responses.GET,
        URL,
        json={
            "observations": [
                {"date": "2026-10-01", "value": "."},
                {"date": "2026-09-01", "value": "3.71725"},
                {"date": "2026-08-01", "value": "3.6"},
            ]
        },
        status=200,
    )

    dato = fred.ipc_eeuu()

    assert dato.valor == 3.71725
    assert dato.fecha == "2026-09-01"  # la fecha real del dato usado, no la pedida


@responses.activate
def test_sin_ningun_valor_real_en_el_margen_lanza_error_explicito() -> None:
    responses.add(
        responses.GET,
        URL,
        json={
            "observations": [
                {"date": "2026-10-01", "value": "."},
                {"date": "2026-09-01", "value": "."},
            ]
        },
        status=200,
    )

    with pytest.raises(SinObservaciones):
        fred.ipc_eeuu()


def test_sin_api_key_lanza_error_explicito(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    with pytest.raises(FredApiKeyFaltante):
        fred.tipo_fed()
