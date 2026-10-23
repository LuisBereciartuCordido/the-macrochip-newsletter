#!/usr/bin/env python3
"""Crea el borrador semanal en Buttondown (sección 8.7 de CLAUDE.md).

Uso:
    python scripts/publish.py --semana AAAA-Sww

Nunca envía el email, solo crea un borrador: la revisión y el envío son
manuales (sección 2.3 de CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

from briefing.buttondown import crear_borrador

log = logging.getLogger("publish")

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"
CONFIG_DIR = RAIZ / "config"


def construir_asunto(informe: dict, nombre_newsletter: str) -> str:
    return f"{nombre_newsletter}: {informe['titular']['texto']}"


class InformeNoValidado(RuntimeError):
    """log.json no confirma que informe.json haya pasado validate.py sin errores."""


def _comprobar_que_el_informe_es_valido(carpeta: Path) -> None:
    """Se niega a crear el borrador si log.json no dice explícitamente que
    el informe es válido.

    Antes, publish.py confiaba en que nadie lo llamara si validate.py había
    fallado — una garantía solo en TAREA_SEMANAL.md, no en el código: nada
    impedía ejecutar publish.py suelto tras una validación fallida
    (hallazgo real de revisión externa).
    """
    ruta_log = carpeta / "log.json"
    if not ruta_log.exists():
        raise InformeNoValidado(f"no existe {ruta_log}; ejecuta validate.py antes de publicar")
    log_contenido = json.loads(ruta_log.read_text())
    validacion = log_contenido.get("validacion")
    if validacion is None:
        raise InformeNoValidado("log.json no tiene la clave 'validacion'")
    if validacion.get("errores"):
        raise InformeNoValidado(f"log.json tiene errores de validación: {validacion['errores']}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semana", required=True, help="Semana ISO a publicar (AAAA-Sww)")
    args = parser.parse_args(argv)

    carpeta = DATA_DIR / args.semana

    try:
        _comprobar_que_el_informe_es_valido(carpeta)
    except InformeNoValidado:
        log.exception("No se crea el borrador: el informe no está validado")
        return 1

    informe = json.loads((carpeta / "informe.json").read_text())
    markdown = (carpeta / "informe.md").read_text()
    general_cfg = yaml.safe_load((CONFIG_DIR / "general.yaml").read_text())

    asunto = construir_asunto(informe, general_cfg["nombre_newsletter"])

    try:
        respuesta = crear_borrador(asunto, markdown)
    except Exception:
        log.exception("Fallo al crear el borrador en Buttondown")
        return 1

    log.info("Borrador creado en Buttondown (id=%s): %s", respuesta.get("id", "?"), asunto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
