import copy
import json
from pathlib import Path

import pytest
import yaml

import validate

from .test_schema import _informe_minimo_valido

SCHEMA = json.loads(validate.SCHEMA_PATH.read_text())
MODULOS_CFG = [{"id": "eeuu", "limite_palabras": 110}]
PALABRAS: dict[str, list[str]] = {"sensacionalismo": [], "recomendacion": []}
# El fuentes.yaml real: así este test cubre también que _informe_minimo_valido()
# (fuente BCE, dominio ecb.europa.eu) siga validando con la lista real tras
# ampliarla, en vez de depender de una lista de prueba separada.
FUENTES_CFG = yaml.safe_load((validate.CONFIG_DIR / "fuentes.yaml").read_text())


def test_informe_valido_no_tiene_errores() -> None:
    # El informe mínimo solo trae una fuente (BCE), así que SÍ dispara el
    # aviso (no bloqueante) de concentración de medios: es el comportamiento
    # esperado, no un fallo. Lo que importa aquí es que no hay errores.
    resultado = validate.validar_informe(
        _informe_minimo_valido(),
        datos={},
        esquema=SCHEMA,
        palabras=PALABRAS,
        modulos_cfg=MODULOS_CFG,
        fuentes_cfg=FUENTES_CFG,
        comprobar_enlaces=False,
    )

    assert resultado.es_valido
    assert resultado.errores == []


def test_error_de_esquema_no_sigue_con_las_demas_comprobaciones() -> None:
    informe = copy.deepcopy(_informe_minimo_valido())
    del informe["modulos"]["geopolitica_riesgos"]  # rompe el esquema (módulo obligatorio)

    resultado = validate.validar_informe(
        informe,
        datos={},
        esquema=SCHEMA,
        palabras=PALABRAS,
        modulos_cfg=MODULOS_CFG,
        fuentes_cfg=FUENTES_CFG,
        comprobar_enlaces=False,
    )

    assert not resultado.es_valido
    assert len(resultado.errores) == 1  # solo el error de esquema, sin cascada


def test_titular_con_id_inexistente_bloquea_un_informe_por_lo_demas_valido() -> None:
    informe = copy.deepcopy(_informe_minimo_valido())
    informe["titular"]["noticia_id"] = "no-existe"

    resultado = validate.validar_informe(
        informe,
        datos={},
        esquema=SCHEMA,
        palabras=PALABRAS,
        modulos_cfg=MODULOS_CFG,
        fuentes_cfg=FUENTES_CFG,
        comprobar_enlaces=False,
    )

    assert not resultado.es_valido
    assert "no-existe" in resultado.errores[0]


def test_palabra_prohibida_bloquea_un_informe_por_lo_demas_valido() -> None:
    informe = copy.deepcopy(_informe_minimo_valido())
    informe["macro_global"][0]["texto"] += " Cunde el pánico en los mercados."

    resultado = validate.validar_informe(
        informe,
        datos={},
        esquema=SCHEMA,
        palabras={"sensacionalismo": ["pánico"], "recomendacion": []},
        modulos_cfg=MODULOS_CFG,
        fuentes_cfg=FUENTES_CFG,
        comprobar_enlaces=False,
    )

    assert not resultado.es_valido


def test_recomendacion_en_el_titular_bloquea_un_informe_por_lo_demas_valido() -> None:
    # Antes del punto 1 (cobertura completa del filtro), titular.texto no se
    # comprobaba: una recomendación de inversión ahí pasaba sin bloquear.
    informe = copy.deepcopy(_informe_minimo_valido())
    informe["titular"]["texto"] = "Deberías comprar antes de que suba"

    resultado = validate.validar_informe(
        informe,
        datos={},
        esquema=SCHEMA,
        palabras={"sensacionalismo": [], "recomendacion": ["deberías comprar"]},
        modulos_cfg=MODULOS_CFG,
        fuentes_cfg=FUENTES_CFG,
        comprobar_enlaces=False,
    )

    assert not resultado.es_valido


def test_nivel_de_fuente_falso_bloquea_un_informe_por_lo_demas_valido() -> None:
    # La noticia autodeclara nivel 1 citando reuters.com, catalogado como
    # nivel 2 en el fuentes.yaml real.
    informe = copy.deepcopy(_informe_minimo_valido())
    informe["macro_global"][0]["fuentes"] = [
        {
            "url": "https://www.reuters.com/markets/x",
            "medio": "Reuters",
            "nivel": 1,
            "fecha": "2026-10-08",
            "idioma": "en",
        }
    ]

    resultado = validate.validar_informe(
        informe,
        datos={},
        esquema=SCHEMA,
        palabras=PALABRAS,
        modulos_cfg=MODULOS_CFG,
        fuentes_cfg=FUENTES_CFG,
        comprobar_enlaces=False,
    )

    assert not resultado.es_valido


def test_id_de_noticia_duplicado_bloquea_un_informe_por_lo_demas_valido() -> None:
    informe = copy.deepcopy(_informe_minimo_valido())
    informe["modulos"]["eeuu"] = {
        "sin_novedades": False,
        "noticias": [dict(informe["macro_global"][0])],  # mismo id que la de macro_global
    }

    resultado = validate.validar_informe(
        informe,
        datos={},
        esquema=SCHEMA,
        palabras=PALABRAS,
        modulos_cfg=MODULOS_CFG,
        fuentes_cfg=FUENTES_CFG,
        comprobar_enlaces=False,
    )

    assert not resultado.es_valido


def test_periodo_incoherente_con_semana_bloquea_un_informe_por_lo_demas_valido() -> None:
    informe = copy.deepcopy(_informe_minimo_valido())
    informe["periodo"] = {"inicio": "2026-10-12", "fin": "2026-10-18"}  # es la semana 2026-S42

    resultado = validate.validar_informe(
        informe,
        datos={},
        esquema=SCHEMA,
        palabras=PALABRAS,
        modulos_cfg=MODULOS_CFG,
        fuentes_cfg=FUENTES_CFG,
        comprobar_enlaces=False,
    )

    assert not resultado.es_valido


def test_cambio_verificador_huerfano_bloquea_un_informe_por_lo_demas_valido() -> None:
    informe = copy.deepcopy(_informe_minimo_valido())
    informe["cambios_verificador"] = [{"noticia_id": "no-existe", "cambio": "x", "motivo": "y"}]

    resultado = validate.validar_informe(
        informe,
        datos={},
        esquema=SCHEMA,
        palabras=PALABRAS,
        modulos_cfg=MODULOS_CFG,
        fuentes_cfg=FUENTES_CFG,
        comprobar_enlaces=False,
    )

    assert not resultado.es_valido


# --- _validar_forma_de_palabras ----------------------------------------------


def test_forma_de_palabras_valida_no_lanza() -> None:
    validate._validar_forma_de_palabras(
        {"sensacionalismo": ["pánico", {"raiz": "hund"}], "recomendacion": []}
    )


def test_forma_de_palabras_no_es_dict_lanza_value_error() -> None:
    with pytest.raises(ValueError):
        validate._validar_forma_de_palabras(["pánico"])


def test_forma_de_palabras_entrada_invalida_lanza_value_error() -> None:
    with pytest.raises(ValueError):
        validate._validar_forma_de_palabras({"sensacionalismo": [{"algo": "x"}]})


def _escribir_semana(tmp_path: Path, semana: str, informe: dict, datos: dict) -> Path:
    carpeta = tmp_path / semana
    carpeta.mkdir()
    (carpeta / "informe.json").write_text(json.dumps(informe))
    (carpeta / "datos.json").write_text(json.dumps(datos))
    return carpeta


def test_main_informe_valido_devuelve_0_y_escribe_log(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(validate, "DATA_DIR", tmp_path)
    carpeta = _escribir_semana(tmp_path, "2026-S41", _informe_minimo_valido(), {})

    codigo = validate.main(["--semana", "2026-S41", "--sin-comprobar-enlaces"])

    assert codigo == 0
    log_contenido = json.loads((carpeta / "log.json").read_text())
    assert log_contenido["validacion"]["errores"] == []


def test_main_informe_invalido_devuelve_1_y_registra_el_error(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validate, "DATA_DIR", tmp_path)
    informe_roto = copy.deepcopy(_informe_minimo_valido())
    del informe_roto["modulos"]["geopolitica_riesgos"]
    carpeta = _escribir_semana(tmp_path, "2026-S41", informe_roto, {})

    codigo = validate.main(["--semana", "2026-S41", "--sin-comprobar-enlaces"])

    assert codigo == 1
    log_contenido = json.loads((carpeta / "log.json").read_text())
    assert len(log_contenido["validacion"]["errores"]) == 1


def test_main_dos_intentos_se_acumulan_en_el_log_sin_perder_el_primero(
    tmp_path: Path, monkeypatch
) -> None:
    # TAREA_SEMANAL.md (sección 5) permite hasta 2 intentos de validate.py.
    # Antes, el segundo intento sobrescribía "validacion" y el primero se
    # perdía sin dejar rastro.
    monkeypatch.setattr(validate, "DATA_DIR", tmp_path)
    informe_roto = copy.deepcopy(_informe_minimo_valido())
    del informe_roto["modulos"]["geopolitica_riesgos"]
    carpeta = _escribir_semana(tmp_path, "2026-S41", informe_roto, {})

    validate.main(["--semana", "2026-S41", "--sin-comprobar-enlaces"])  # 1er intento: falla
    (carpeta / "informe.json").write_text(json.dumps(_informe_minimo_valido()))
    validate.main(["--semana", "2026-S41", "--sin-comprobar-enlaces"])  # 2º intento: corregido

    log_contenido = json.loads((carpeta / "log.json").read_text())
    assert len(log_contenido["validacion_intentos"]) == 2
    assert log_contenido["validacion_intentos"][0]["errores"] != []
    assert log_contenido["validacion_intentos"][1]["errores"] == []
    assert log_contenido["validacion"]["errores"] == []  # el más reciente


def test_main_no_revienta_con_traceback_si_una_comprobacion_lanza_excepcion(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validate, "DATA_DIR", tmp_path)
    carpeta = _escribir_semana(tmp_path, "2026-S41", _informe_minimo_valido(), {})

    def _revienta(informe, fuentes_cfg):
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(validate.validacion, "validar_nivel_de_fuentes", _revienta)

    codigo = validate.main(["--semana", "2026-S41", "--sin-comprobar-enlaces"])

    assert codigo == 1
    log_contenido = json.loads((carpeta / "log.json").read_text())
    assert "fallo inesperado" in log_contenido["validacion"]["errores"][0]
