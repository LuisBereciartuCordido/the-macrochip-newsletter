#!/usr/bin/env python3
"""Renderiza informe.json (+ datos.json) a data/<semana>/informe.md.

Uso:
    python scripts/render.py --semana AAAA-Sww

También escribe data/<semana>/transparencia.md ("cómo se hizo este
informe") — es de uso interno, nunca se publica ni se adjunta al
borrador de Buttondown (decisión de producto, sección 5 de CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

from briefing.render import renderizar_informe, renderizar_transparencia
from briefing.semanas import semana_anterior

log = logging.getLogger("render")

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"
CONFIG_DIR = RAIZ / "config"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semana", required=True, help="Semana ISO a renderizar (AAAA-Sww)")
    args = parser.parse_args(argv)

    carpeta = DATA_DIR / args.semana
    informe = json.loads((carpeta / "informe.json").read_text())
    datos = json.loads((carpeta / "datos.json").read_text())

    ruta_anterior = DATA_DIR / semana_anterior(args.semana) / "datos.json"
    datos_semana_anterior = json.loads(ruta_anterior.read_text()) if ruta_anterior.exists() else None

    semana_mes_atras = args.semana
    for _ in range(4):
        semana_mes_atras = semana_anterior(semana_mes_atras)
    ruta_mes_atras = DATA_DIR / semana_mes_atras / "datos.json"
    datos_mes_anterior = json.loads(ruta_mes_atras.read_text()) if ruta_mes_atras.exists() else None

    mercados_cfg = yaml.safe_load((CONFIG_DIR / "mercados.yaml").read_text())
    modulos_cfg = yaml.safe_load((CONFIG_DIR / "modulos.yaml").read_text())
    general_cfg = yaml.safe_load((CONFIG_DIR / "general.yaml").read_text())

    markdown = renderizar_informe(
        informe,
        datos,
        datos_semana_anterior,
        mercados_cfg=mercados_cfg,
        modulos_cfg=modulos_cfg,
        nombre_newsletter=general_cfg["nombre_newsletter"],
        logo_url=general_cfg["logo_url"],
        datos_mes_anterior=datos_mes_anterior,
    )

    ruta_salida = carpeta / "informe.md"
    ruta_salida.write_text(markdown)
    log.info("Escrito %s", ruta_salida)

    ruta_transparencia = carpeta / "transparencia.md"
    ruta_transparencia.write_text(renderizar_transparencia(informe))
    log.info("Escrito %s (uso interno, no se publica)", ruta_transparencia)
    return 0


if __name__ == "__main__":
    sys.exit(main())
