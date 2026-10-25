#!/usr/bin/env python3
"""Valida informe.json contra el esquema y las reglas de la sección 10 de CLAUDE.md.

Uso:
    python scripts/validate.py --semana AAAA-Sww [--sin-comprobar-enlaces]

Si hay errores (bloqueantes), termina con código de salida 1: el flujo
semanal (sección 8.5) debe detenerse sin publicar el borrador. Los
errores y avisos quedan siempre en data/<semana>/log.json, se publique o
no, para poder revisarlos después.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import jsonschema
import yaml

from briefing import validacion
from briefing.validacion import EntradaPalabra, ResultadoValidacion
from briefing.validacion_enlaces import comprobar_enlaces_informe

log = logging.getLogger("validate")

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"
CONFIG_DIR = RAIZ / "config"
SCHEMA_PATH = RAIZ / "schema" / "informe.schema.json"

_PATRON_SEMANA = re.compile(r"^\d{4}-S\d{2}$")
MAX_SEMANAS_HISTORIAL = 8


def _historial_de_semanas(data_dir: Path, semana_actual: str) -> dict[str, dict]:
    """Hasta MAX_SEMANAS_HISTORIAL semanas con datos.json anteriores a semana_actual.

    Usadas por avisos_tendencias_inconsistentes (sección 10) para contrastar
    afirmaciones de tendencia contra la serie real. Compara por cadena
    ("AAAA-Sww" ordena igual cronológicamente que como texto), sin asumir
    que las semanas sean contiguas — puede haber huecos.
    """
    candidatas = sorted(
        p.name
        for p in data_dir.iterdir()
        if p.is_dir()
        and _PATRON_SEMANA.match(p.name)
        and p.name < semana_actual
        and (p / "datos.json").exists()
    )
    return {
        nombre: json.loads((data_dir / nombre / "datos.json").read_text())
        for nombre in candidatas[-MAX_SEMANAS_HISTORIAL:]
    }


def _errores_de_esquema(informe: dict, esquema: dict) -> list[str]:
    validador = jsonschema.Draft202012Validator(esquema, format_checker=jsonschema.FormatChecker())
    return sorted(
        f"{'.'.join(str(p) for p in error.path) or '(raíz)'}: {error.message}"
        for error in validador.iter_errors(informe)
    )


def _validar_forma_de_palabras(palabras: object) -> None:
    """Falla pronto y con un mensaje claro si validacion.yaml está mal formado,
    en vez de dejar que yaml.safe_load devuelva algo inesperado que rompa
    validar_palabras_prohibidas más adelante con un error confuso.
    """
    if not isinstance(palabras, dict):
        raise ValueError("config/validacion.yaml debe ser un diccionario de categoría -> lista")
    for categoria, lista in palabras.items():
        if not isinstance(lista, list):
            raise ValueError(f"config/validacion.yaml: '{categoria}' debe ser una lista")
        for entrada in lista:
            es_cadena = isinstance(entrada, str)
            es_raiz_valida = (
                isinstance(entrada, dict) and set(entrada) == {"raiz"} and isinstance(entrada["raiz"], str)
            )
            if not (es_cadena or es_raiz_valida):
                raise ValueError(
                    f"config/validacion.yaml: entrada inválida en '{categoria}': {entrada!r} "
                    '(debe ser una cadena, o {"raiz": "..."})'
                )


def validar_informe(
    informe: dict,
    datos: dict,
    *,
    esquema: dict,
    palabras: Mapping[str, Sequence[EntradaPalabra]],
    modulos_cfg: list[dict],
    fuentes_cfg: dict,
    antiguedad_maxima_dias: int = 10,
    comprobar_enlaces: bool = True,
    historial_semanas: Mapping[str, dict] | None = None,
) -> ResultadoValidacion:
    """Corre todas las comprobaciones de la sección 10 sobre un informe ya cargado."""
    resultado = ResultadoValidacion()

    errores_esquema = _errores_de_esquema(informe, esquema)
    resultado.errores.extend(errores_esquema)
    if errores_esquema:
        # El resto de comprobaciones asumen que informe.json tiene la forma
        # del esquema; si no la tiene, seguir solo daría errores en cascada
        # que no aportan nada nuevo.
        return resultado

    resultado.errores.extend(validacion.validar_titular(informe))
    resultado.errores.extend(validacion.validar_confianza_y_fuentes(informe, fuentes_cfg))
    resultado.errores.extend(validacion.validar_nivel_de_fuentes(informe, fuentes_cfg))
    resultado.errores.extend(validacion.validar_cifras(informe, datos))
    resultado.errores.extend(
        validacion.validar_fechas_fuente(informe, antiguedad_maxima_dias)
    )
    resultado.errores.extend(validacion.validar_palabras_prohibidas(informe, palabras))
    resultado.errores.extend(validacion.validar_ids_de_noticia_unicos(informe))
    resultado.errores.extend(validacion.validar_periodo_coherente_con_semana(informe))
    resultado.errores.extend(
        validacion.validar_cambios_verificador_referencian_noticias_reales(informe)
    )

    resultado.avisos.extend(validacion.avisos_limite_palabras(informe, modulos_cfg))
    resultado.avisos.extend(validacion.avisos_concentracion_medios(informe))
    resultado.avisos.extend(validacion.avisos_modulo_sin_fuentes_fiables(informe))
    resultado.avisos.extend(validacion.avisos_fuentes_no_catalogadas(informe, fuentes_cfg))
    resultado.avisos.extend(validacion.avisos_titular_largo(informe))
    resultado.avisos.extend(validacion.avisos_concepto_semana_largo(informe))
    resultado.avisos.extend(validacion.avisos_cifras_sin_verificar(informe))
    resultado.avisos.extend(
        validacion.avisos_tendencias_inconsistentes(informe, datos, historial_semanas or {})
    )

    if comprobar_enlaces:
        errores_enlaces, avisos_enlaces = comprobar_enlaces_informe(informe)
        resultado.errores.extend(errores_enlaces)
        resultado.avisos.extend(avisos_enlaces)

    return resultado


def _escribir_en_log(carpeta: Path, resultado: ResultadoValidacion) -> None:
    """Escribe el resultado de este intento en log.json, sin perder los anteriores.

    TAREA_SEMANAL.md (sección 5) permite hasta 2 intentos de validate.py por
    semana; sobrescribir "validacion" en cada intento perdía los hallazgos
    del primero. Ahora se acumulan en "validacion_intentos" (uno por
    ejecución) y "validacion" sigue siendo el más reciente, por
    compatibilidad con quien ya lee esa clave.
    """
    ruta = carpeta / "log.json"
    contenido = json.loads(ruta.read_text()) if ruta.exists() else {}
    intento = {"errores": resultado.errores, "avisos": resultado.avisos}
    intentos = contenido.get("validacion_intentos", [])
    intentos.append(intento)
    contenido["validacion_intentos"] = intentos
    contenido["validacion"] = intento
    ruta.write_text(json.dumps(contenido, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semana", required=True, help="Semana ISO a validar (AAAA-Sww)")
    parser.add_argument(
        "--sin-comprobar-enlaces",
        action="store_true",
        help="No comprobar los enlaces por HTTP (más rápido para iterar en local)",
    )
    args = parser.parse_args(argv)

    carpeta = DATA_DIR / args.semana
    informe = json.loads((carpeta / "informe.json").read_text())
    datos = json.loads((carpeta / "datos.json").read_text())
    esquema = json.loads(SCHEMA_PATH.read_text())
    palabras = yaml.safe_load((CONFIG_DIR / "validacion.yaml").read_text())
    _validar_forma_de_palabras(palabras)
    modulos_cfg = yaml.safe_load((CONFIG_DIR / "modulos.yaml").read_text())
    fuentes_cfg = yaml.safe_load((CONFIG_DIR / "fuentes.yaml").read_text())
    historial_semanas = _historial_de_semanas(DATA_DIR, args.semana)

    try:
        resultado = validar_informe(
            informe,
            datos,
            esquema=esquema,
            palabras=palabras,
            antiguedad_maxima_dias=fuentes_cfg["antiguedad_maxima_dias"],
            historial_semanas=historial_semanas,
            modulos_cfg=modulos_cfg,
            fuentes_cfg=fuentes_cfg,
            comprobar_enlaces=not args.sin_comprobar_enlaces,
        )
    except Exception as exc:
        # Una excepción inesperada en cualquier comprobación no debe abortar
        # sin dejar rastro: log.json siempre se escribe, se publique o no
        # (así lo dice el docstring del módulo) — antes, esto rompía con un
        # traceback sin pasar por _escribir_en_log.
        log.exception("La validación lanzó una excepción inesperada")
        resultado = ResultadoValidacion(
            errores=[f"excepción inesperada durante la validación: {exc}"]
        )
    _escribir_en_log(carpeta, resultado)

    for error in resultado.errores:
        log.error(error)
    for aviso in resultado.avisos:
        log.warning(aviso)

    if not resultado.es_valido:
        log.error("informe.json tiene %d error(es); no se debe publicar", len(resultado.errores))
        return 1

    log.info("informe.json válido (%d aviso(s))", len(resultado.avisos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
