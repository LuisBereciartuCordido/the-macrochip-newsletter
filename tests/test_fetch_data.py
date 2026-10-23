import json
from pathlib import Path

import fetch_data
from briefing.modelos import Dato


def _dato(fecha: str = "2026-09-01") -> Dato:
    return Dato(valor=1.0, unidad="%", fecha=fecha, fuente="test", url="https://x")


def _parchear_fuentes(monkeypatch) -> None:
    monkeypatch.setattr(fetch_data.ecb, "tipo_facilidad_deposito", lambda: _dato("2026-10-06"))
    monkeypatch.setattr(fetch_data.ecb, "eur_usd_referencia", lambda: _dato("2026-10-06"))
    monkeypatch.setattr(fetch_data.eurostat, "ipca_eurozona", lambda: _dato("2026-09-01"))
    monkeypatch.setattr(fetch_data.ine, "ipc_espana", lambda: _dato("2026-09-01"))
    monkeypatch.setattr(fetch_data.fred, "tipo_fed", lambda: _dato("2026-10-03"))
    monkeypatch.setattr(fetch_data.fred, "ipc_eeuu", lambda: _dato("2026-09-01"))
    monkeypatch.setattr(fetch_data.fred, "sp500", lambda: _dato("2026-10-03"))
    monkeypatch.setattr(fetch_data.fred, "brent", lambda: _dato("2026-10-03"))
    monkeypatch.setattr(
        fetch_data.mercados,
        "cierres_semanales",
        lambda: {
            "nikkei225": _dato("2026-10-03"),
            "oro": _dato("2026-10-03"),
            "msci_world": _dato("2026-10-03"),
            "msci_em": _dato("2026-10-03"),
            "msci_europe": _dato("2026-10-03"),
        },
    )


def test_descargar_junta_los_13_instrumentos(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(fetch_data, "DATA_DIR", tmp_path)
    _parchear_fuentes(monkeypatch)

    datos = fetch_data.descargar()

    assert set(datos) == {
        "bce_tipo_deposito",
        "eur_usd",
        "ipca_eurozona",
        "ipc_espana",
        "fed_tipo",
        "ipc_eeuu",
        "sp500",
        "brent",
        "nikkei225",
        "oro",
        "msci_world",
        "msci_em",
        "msci_europe",
    }


def test_descargar_incluye_mensuales_aunque_no_hayan_cambiado(
    tmp_path: Path, monkeypatch
) -> None:
    # Hallazgo real (semana 2026-S42): si el IPC/IPCA se omitía por no ser
    # "nuevo", el redactor se quedaba sin ningún dato oficial estructurado
    # al que citar y acababa citando un medio externo en su lugar. Ahora se
    # incluye siempre, con su fecha real — la frescura la juzga el redactor
    # mirando esa fecha, no la presencia o ausencia del dato.
    monkeypatch.setattr(fetch_data, "DATA_DIR", tmp_path)
    (tmp_path / "2026-S40").mkdir()
    (tmp_path / "2026-S40" / "datos.json").write_text(
        json.dumps({"ipc_espana": {"fecha": "2026-09-01"}})
    )
    _parchear_fuentes(monkeypatch)  # ine.ipc_espana sigue devolviendo "2026-09-01"

    datos = fetch_data.descargar()

    assert datos["ipc_espana"]["fecha"] == "2026-09-01"


def test_main_escribe_datos_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(fetch_data, "DATA_DIR", tmp_path)
    _parchear_fuentes(monkeypatch)

    codigo = fetch_data.main(["--semana", "2026-S41"])

    assert codigo == 0
    contenido = json.loads((tmp_path / "2026-S41" / "datos.json").read_text())
    assert contenido["sp500"]["valor"] == 1.0


def test_descargar_con_variacion_semanal_plausible_no_avisa(monkeypatch) -> None:
    _parchear_fuentes(monkeypatch)  # msci_world queda en 1.0 (ver _parchear_fuentes)
    datos_previos = {"msci_world": {"valor": 1.01}}

    datos = fetch_data.descargar(datos_semana_anterior=datos_previos)

    assert "aviso" not in datos["msci_world"]


def test_descargar_con_variacion_semanal_sospechosa_no_aborta_pero_avisa(monkeypatch) -> None:
    # No debe abortar: un movimiento real así, aunque rarísimo, es posible
    # — y sería justo la semana en la que más falta hace el newsletter.
    _parchear_fuentes(monkeypatch)
    datos_previos = {"msci_world": {"valor": 100.0}}  # 1.0 vs 100.0: variación absurda

    datos = fetch_data.descargar(datos_semana_anterior=datos_previos)

    assert "aviso" in datos["msci_world"]
    assert "100.0%" in datos["msci_world"]["aviso"] or "variación" in datos["msci_world"]["aviso"]


def test_descargar_sin_semana_anterior_no_comprueba_variacion(monkeypatch) -> None:
    _parchear_fuentes(monkeypatch)
    # Sin dato de la semana anterior (primera semana, o se borró el
    # histórico), no hay nada contra lo que comparar — no debe avisar.
    datos = fetch_data.descargar(datos_semana_anterior=None)

    assert "aviso" not in datos["msci_world"]


def test_main_lee_la_semana_anterior_y_escribe_el_aviso_en_datos_json(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(fetch_data, "DATA_DIR", tmp_path)
    _parchear_fuentes(monkeypatch)  # msci_world queda en 1.0
    (tmp_path / "2026-S40").mkdir()
    (tmp_path / "2026-S40" / "datos.json").write_text(
        json.dumps({"msci_world": {"valor": 100.0}})
    )

    codigo = fetch_data.main(["--semana", "2026-S41"])

    assert codigo == 0
    contenido = json.loads((tmp_path / "2026-S41" / "datos.json").read_text())
    assert "aviso" in contenido["msci_world"]


def test_main_no_escribe_nada_si_falla_una_fuente(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(fetch_data, "DATA_DIR", tmp_path)

    def _falla():
        raise RuntimeError("BCE no responde")

    monkeypatch.setattr(fetch_data.ecb, "tipo_facilidad_deposito", _falla)

    codigo = fetch_data.main(["--semana", "2026-S41"])

    assert codigo == 1
    assert not (tmp_path / "2026-S41").exists()
