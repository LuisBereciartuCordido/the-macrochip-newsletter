"""Renderiza informe.json (+ datos.json) a Markdown (sección 11 de CLAUDE.md)."""

from __future__ import annotations

import datetime
from urllib.parse import quote

from briefing.modelos import MODULOS_IDS, todas_las_noticias

MESES_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

AVISO_LEGAL = "Contenido informativo. No es asesoramiento financiero."

INSTRUCCION_CONTEXTO_IA = (
    "Toca uno de los enlaces para abrirlo directamente con el mensaje ya puesto, "
    "o copia el bloque de abajo y pégalo en tu asistente de IA preferido."
)

PROMPT_SUGERIDO_IA = (
    "Este es el contexto del briefing semanal de The Macrochip. Antes de nada, "
    "pregúntame sobre qué tema de los incluidos quiero profundizar. Cuando te "
    "lo diga, explícamelo en detalle y qué significa para alguien que vive en "
    "España. Si algo no está en el contexto, búscalo en fuentes fiables y dime "
    "cuáles son."
)

LIMITE_CONTEXTO_IA_CARACTERES = 10000

# claude.ai/new?q=... y chat.openai.com/?q=... precargan ese texto en un
# chat nuevo (sin enviarlo solo, por seguridad: el lector sigue teniendo
# que darle a enviar) — son enlaces normales, sin JavaScript, así que
# funcionan dentro de un email a diferencia de un botón de "copiar al
# portapapeles" (eso sí necesita JavaScript, y los clientes de correo lo
# bloquean siempre). Gemini no tiene nada equivalente de forma nativa —
# solo funciona con una extensión de Chrome de terceros que casi nadie
# tiene instalada, así que no se incluye un enlace falso para él.
URL_BASE_CLAUDE = "https://claude.ai/new?q="
URL_BASE_CHATGPT = "https://chat.openai.com/?q="

EMOJI_CONFIANZA = {
    "confirmado": "✅",
    "una_fuente": "⚠️",
    "interpretacion": "💬",
}

COLOR_VARIACION_POSITIVA = "#0A7D3C"
COLOR_VARIACION_NEGATIVA = "#C23B2E"

LOGO_ANCHO_PX = 220


def _formatear_valor(valor: float, unidad: str) -> str:
    if unidad == "puntos":
        return f"{valor:,.0f} puntos"
    if unidad in ("% anual", "% interanual"):
        return f"{valor:.1f} %"
    if unidad == "USD por EUR":
        return f"{valor:.4f} USD"
    return f"{valor:,.2f} {unidad}"


def _formatear_variacion(actual: float, anterior: float | None) -> str:
    if anterior is None or anterior == 0:
        return "—"
    variacion = (actual - anterior) / anterior * 100
    return f"{variacion:+.2f} %"


def _formatear_variacion_coloreada(actual: float, anterior: float | None) -> str:
    """Como _formatear_variacion, pero en verde si sube y en rojo si baja.

    Buttondown deja usar HTML suelto dentro del Markdown ("All HTML is
    valid Markdown" — docs.buttondown.com/using-markdown), así que un
    <span style="color:..."> puntual no exige pasar todo el email a HTML.
    """
    variacion_fmt = _formatear_variacion(actual, anterior)
    if variacion_fmt == "—":
        return variacion_fmt
    color = COLOR_VARIACION_POSITIVA if variacion_fmt.startswith("+") else COLOR_VARIACION_NEGATIVA
    return f'<span style="color:{color}">{variacion_fmt}</span>'


def renderizar_lo_esencial(informe: dict) -> str:
    lineas = "\n".join(f"- {linea}" for linea in informe["lo_esencial"])
    return f"## Lo esencial\n\n{lineas}\n"


def renderizar_mercados(
    datos: dict, datos_semana_anterior: dict | None, mercados_cfg: list[dict]
) -> str:
    """Lista (no tabla) de instrumentos: valor y variación semanal.

    Una tabla Markdown pierde su fila de cabecera si alguien abre el
    borrador en el editor "fancy" de Buttondown y toca el cuerpo
    (comprobado, ver CLAUDE.md sección 11) — una lista no tiene cabecera
    que perder, así que el problema desaparece en vez de solo avisarse.
    También se lee mejor en móvil que una tabla de 3 columnas.
    """
    filas = []
    for instrumento in mercados_cfg:
        id_ = instrumento["id"]
        dato = datos.get(id_)
        if dato is None:
            filas.append(f"- **{instrumento['nombre']}:** sin dato (—)")
            continue
        anterior = (datos_semana_anterior or {}).get(id_, {}).get("valor")
        valor_fmt = _formatear_valor(dato["valor"], instrumento["unidad"])
        variacion_fmt = _formatear_variacion_coloreada(dato["valor"], anterior)
        filas.append(f"- **{instrumento['nombre']}:** {valor_fmt} ({variacion_fmt})")
    lista = "\n".join(filas)
    return f"## Mercados esta semana\n\n{lista}\n"


def _renderizar_fuentes(fuentes: list[dict]) -> str:
    return " · ".join(f"[{f['medio']}]({f['url']})" for f in fuentes)


def _renderizar_noticia(noticia: dict) -> str:
    emoji = EMOJI_CONFIANZA[noticia["confianza"]]
    return (
        f"**{noticia['titulo']}**\n\n"
        f"{noticia['texto']} {emoji}\n\n"
        f"*Por qué importa:* {noticia['por_que_importa']}\n\n"
        f"Fuentes: {_renderizar_fuentes(noticia['fuentes'])}\n"
    )


def renderizar_macro_global(informe: dict) -> str:
    noticias = "\n".join(_renderizar_noticia(n) for n in informe["macro_global"])
    return f"## Macro global\n\n{noticias}"


def renderizar_modulos(informe: dict, modulos_cfg: list[dict]) -> str:
    titulos = {m["id"]: m["titulo"] for m in modulos_cfg}
    secciones = []
    for id_modulo in MODULOS_IDS:
        modulo = informe["modulos"][id_modulo]
        titulo = titulos.get(id_modulo, id_modulo)
        if modulo.get("sin_novedades"):
            secciones.append(f"## {titulo}\n\n_Sin novedades relevantes esta semana._\n")
            continue
        noticias = "\n".join(_renderizar_noticia(n) for n in modulo["noticias"])
        secciones.append(f"## {titulo}\n\n{noticias}")
    return "\n\n".join(secciones)


def renderizar_concepto_semana(informe: dict) -> str:
    concepto = informe["concepto_semana"]
    return f"## Concepto de la semana: {concepto['titulo']}\n\n{concepto['texto']}\n"


def renderizar_perspectiva(informe: dict) -> str:
    perspectiva = informe["perspectiva_largo_plazo"]
    estructural = "\n".join(f"- {linea}" for linea in perspectiva["estructural"]) or "- (nada reseñable)"
    ruido = "\n".join(f"- {linea}" for linea in perspectiva["ruido"]) or "- (nada reseñable)"
    return (
        "## Perspectiva de largo plazo\n\n"
        f"**Estructural (relevancia de años):**\n\n{estructural}\n\n"
        f"**Ruido (relevancia de días):**\n\n{ruido}\n"
    )


def renderizar_para_profundizar(informe: dict, modulos_cfg: list[dict]) -> str:
    titulos = {m["id"]: m["titulo"] for m in modulos_cfg}
    bloques = []
    for id_modulo in ("macro_global", *MODULOS_IDS):
        if id_modulo == "macro_global":
            noticias = informe["macro_global"]
            titulo = "Macro global"
        else:
            modulo = informe["modulos"][id_modulo]
            if modulo.get("sin_novedades"):
                continue
            noticias = modulo["noticias"]
            titulo = titulos.get(id_modulo, id_modulo)
        if not noticias:
            continue
        enlaces = "\n".join(
            f"- {_renderizar_fuentes(n['fuentes'])}" for n in noticias
        )
        bloques.append(f"**{titulo}**\n\n{enlaces}")
    return "## Para profundizar\n\n" + "\n\n".join(bloques) + "\n"


def renderizar_indice(modulos_cfg: list[dict]) -> str:
    # Sin enlaces de anclaje: el soporte de "#ancla" dentro de un email es
    # demasiado inconsistente entre clientes de correo para prometer que
    # vayan a funcionar. Es una lista de lectura, no de navegación.
    lineas = "\n".join(f"- {m['titulo']}" for m in modulos_cfg)
    return f"**En este informe:**\n\n{lineas}\n"


def _formatear_fecha_es(fecha_iso: str) -> tuple[int, str, int]:
    fecha = datetime.date.fromisoformat(fecha_iso)
    return fecha.day, MESES_ES[fecha.month], fecha.year


def _formatear_rango_fechas(inicio: str, fin: str) -> str:
    dia_i, mes_i, anio_i = _formatear_fecha_es(inicio)
    dia_f, mes_f, anio_f = _formatear_fecha_es(fin)
    if (mes_i, anio_i) == (mes_f, anio_f):
        return f"{dia_i} al {dia_f} de {mes_f} de {anio_f}"
    if anio_i == anio_f:
        return f"{dia_i} de {mes_i} al {dia_f} de {mes_f} de {anio_f}"
    return f"{dia_i} de {mes_i} de {anio_i} al {dia_f} de {mes_f} de {anio_f}"


def renderizar_titulo(informe: dict, nombre_newsletter: str, logo_url: str) -> str:
    """Logo + el titular llamativo de la semana, con la fecha en una línea
    pequeña debajo (sección 5: "título llamativo", no una fecha mecánica).

    El logo ya lleva el nombre de la newsletter en la propia imagen
    (wordmark), así que no se repite como texto aparte — se vio repetido
    en una prueba real (logo + "The Macrochip" debajo, dos veces seguidas).
    El titular pasa a ser el encabezado principal del texto.

    El logo es una URL fija (config/general.yaml) — se sube una sola vez
    a Buttondown, no en cada ejecución, porque no cambia semana a semana.
    Va con un <img width="..."> explícito, no la sintaxis Markdown de
    imagen: en una prueba real, algunos clientes de correo estiraban la
    imagen al ancho de la columna del email sin respetar su tamaño
    natural, pixelándola — fijar el ancho de visualización (con el PNG
    a mayor resolución de base, LOGO_ANCHO_PX) lo evita.
    """
    rango = _formatear_rango_fechas(informe["periodo"]["inicio"], informe["periodo"]["fin"])
    return (
        f'<img src="{logo_url}" alt="{nombre_newsletter}" width="{LOGO_ANCHO_PX}">\n\n'
        f"# {informe['titular']['texto']}\n\n"
        f"_Semana del {rango}_\n"
    )


def renderizar_contexto_ia(
    informe: dict, datos: dict, *, limite_caracteres: int = LIMITE_CONTEXTO_IA_CARACTERES
) -> str:
    """Bloque de código copiable con el contexto en bruto (sección 11).

    Solo usa resúmenes propios (ya están en informe.json, nunca texto
    copiado de un artículo) y datos con su fecha y fuente — nunca un
    número suelto sin de dónde sale.
    """
    lineas = [
        f"PROMPT SUGERIDO: {PROMPT_SUGERIDO_IA}",
        "",
        f"PERIODO: {informe['periodo']['inicio']} a {informe['periodo']['fin']}",
        "",
        "DATOS DUROS:",
    ]
    for clave, dato in sorted(datos.items()):
        lineas.append(
            f"- {clave}: {dato['valor']} {dato['unidad']} "
            f"({dato['fecha']}, fuente: {dato['fuente']})"
        )

    lineas.append("")
    lineas.append("NOTICIAS:")
    for _, noticia in todas_las_noticias(informe):
        fuentes = "; ".join(f"{f['medio']} {f['fecha']}" for f in noticia["fuentes"])
        lineas.append(
            f"- [{noticia['hilo_id']}] {noticia['titulo']} — {noticia['texto']} "
            f"(confianza: {noticia['confianza']}; fuentes: {fuentes})"
        )

    cuerpo_completo = "\n".join(lineas)
    if len(cuerpo_completo) <= limite_caracteres:
        cuerpo = cuerpo_completo
        nota_recorte = ""
    else:
        # Recorta por línea completa (cada "- ..." es un dato o una noticia
        # entera), no por conteo de caracteres a lo bruto: lo que queda
        # dentro del límite está siempre completo, nunca una frase a medias.
        acumuladas: list[str] = []
        longitud = 0
        for linea in lineas:
            longitud_con_esta = longitud + len(linea) + 1  # +1 por el salto de línea
            if longitud_con_esta > limite_caracteres:
                break
            acumuladas.append(linea)
            longitud = longitud_con_esta
        cuerpo = "\n".join(acumuladas).rstrip()
        nota_recorte = "\n\n[...contexto recortado por tamaño...]"

    texto_completo = f"{cuerpo}{nota_recorte}"
    enlace_claude = URL_BASE_CLAUDE + quote(texto_completo)
    enlace_chatgpt = URL_BASE_CHATGPT + quote(texto_completo)

    return (
        "## Paquete de contexto para IA\n\n"
        f"[Abrir directamente en Claude →]({enlace_claude}) · "
        f"[Abrir directamente en ChatGPT →]({enlace_chatgpt})\n\n"
        f"{INSTRUCCION_CONTEXTO_IA}\n\n"
        "```\n"
        f"{texto_completo}\n"
        "```\n"
    )


def renderizar_transparencia(informe: dict) -> str:
    """Versión breve de "cómo se hizo este informe" (sección 11).

    De uso interno: scripts/render.py escribe esto en transparencia.md,
    nunca en informe.md — mostrarlo a todos los suscriptores resta
    fiabilidad percibida en vez de sumarla (decisión de producto, sección
    5). El detalle completo (cada cambio, cada fuente descartada con su
    motivo exacto) queda en log.json; aquí solo van los números.
    """
    conteo_niveles = {1: 0, 2: 0, 3: 0}
    for _, noticia in todas_las_noticias(informe):
        for fuente in noticia["fuentes"]:
            conteo_niveles[fuente["nivel"]] += 1
    resumen_niveles = ", ".join(f"nivel {n}: {c}" for n, c in sorted(conteo_niveles.items()))

    conteo_descartes: dict[str, int] = {}
    for descartada in informe.get("fuentes_descartadas", []):
        motivo = descartada["motivo"]
        conteo_descartes[motivo] = conteo_descartes.get(motivo, 0) + 1
    resumen_descartes = (
        ", ".join(f"{motivo}: {c}" for motivo, c in conteo_descartes.items()) or "ninguna"
    )

    cambios = informe.get("cambios_verificador", [])
    primeros_cambios = "\n".join(f"- {c['noticia_id']}: {c['cambio']}" for c in cambios[:5])
    resumen_cambios = primeros_cambios or "- (sin cambios)"
    if len(cambios) > 5:
        resumen_cambios += f"\n\n_{len(cambios) - 5} cambio(s) más en log.json._"

    return (
        "## Cómo se hizo este informe\n\n"
        f"Fuentes citadas por nivel: {resumen_niveles}.\n\n"
        f"Fuentes descartadas: {resumen_descartes}.\n\n"
        f"Principales cambios del verificador:\n\n{resumen_cambios}\n\n"
        "El detalle completo queda en `log.json`.\n"
    )


def renderizar_aviso_legal() -> str:
    return f"---\n\n_{AVISO_LEGAL}_\n"


def renderizar_informe(
    informe: dict,
    datos: dict,
    datos_semana_anterior: dict | None,
    *,
    mercados_cfg: list[dict],
    modulos_cfg: list[dict],
    nombre_newsletter: str,
    logo_url: str,
) -> str:
    """Ensambla el Markdown **público** del email, en el orden de la sección 5.

    No incluye "Cómo se hizo este informe": esa sección es de uso interno
    (decisión de producto, sección 5) y la escribe por separado
    renderizar_transparencia(), en transparencia.md — nunca en el email
    que reciben los suscriptores.
    """
    secciones = [
        renderizar_titulo(informe, nombre_newsletter, logo_url),
        renderizar_indice(modulos_cfg),
        renderizar_lo_esencial(informe),
        renderizar_mercados(datos, datos_semana_anterior, mercados_cfg),
        renderizar_macro_global(informe),
        renderizar_modulos(informe, modulos_cfg),
        renderizar_concepto_semana(informe),
        renderizar_perspectiva(informe),
        renderizar_para_profundizar(informe, modulos_cfg),
        renderizar_contexto_ia(informe, datos),
        renderizar_aviso_legal(),
    ]
    return "\n\n".join(secciones) + "\n"
