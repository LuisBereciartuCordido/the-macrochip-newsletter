"""Comprobaciones deterministas de informe.json (sección 10 de CLAUDE.md).

Separa "errores" (bloquean la publicación) de "avisos" (no bloquean, pero
se muestran en el resumen). La comprobación de enlaces caídos vive en
validacion_enlaces.py porque hace peticiones HTTP reales; todo lo de este
módulo es puro (no toca la red ni el disco), lo que lo hace fácil de
testear y de reutilizar.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlparse

from briefing.modelos import MODULOS_IDS, todas_las_noticias
from briefing.semanas import periodo_de_semana


@dataclass
class ResultadoValidacion:
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def es_valido(self) -> bool:
        return not self.errores


def _dominio(url: str) -> str:
    """Dominio de una URL, en minúsculas y sin puerto ni prefijo "www.".

    Usa `.hostname` (no `.netloc`): netloc conserva el puerto si la URL lo
    lleva y no normaliza mayúsculas, lo que podría hacer que un dominio con
    mayúsculas o puerto no coincidiera con fuentes.yaml pese a ser el mismo
    dominio.
    """
    return (urlparse(url).hostname or "").removeprefix("www.")


def _nivel_catalogado(dominio: str, fuentes_cfg: dict) -> int | None:
    """Nivel real de un dominio según fuentes.yaml, o None si no está catalogado.

    Coincide también por subdominio: "ecb.europa.eu" coincide con el
    catalogado "europa.eu", no solo por igualdad exacta (config/fuentes.yaml
    documenta por qué: europa.eu cubre todas las instituciones de la UE).

    Si un dominio coincidiera con entradas catalogadas en más de un nivel,
    se queda con el sufijo más largo (más específico), no con el primero que
    aparezca en el YAML: el orden de los niveles en el fichero no debería
    decidir el resultado.
    """
    mejor_nivel: int | None = None
    mejor_longitud = -1
    for nivel, datos_nivel in fuentes_cfg["niveles"].items():
        for catalogado in datos_nivel["dominios"]:
            coincide = dominio == catalogado or dominio.endswith("." + catalogado)
            if coincide and len(catalogado) > mejor_longitud:
                mejor_nivel = nivel
                mejor_longitud = len(catalogado)
    return mejor_nivel


def validar_confianza_y_fuentes(informe: dict, fuentes_cfg: dict) -> list[str]:
    """confirmado exige >=2 fuentes de dominios distintos, o alguna de nivel 1 real.

    "Nivel 1 real" = catalogado como tal en fuentes.yaml, no el `nivel` que
    la propia noticia autodeclara: un dominio no catalogado no puede, por sí
    solo, confirmar una noticia aunque diga nivel=1 (el mismatch entre nivel
    declarado y nivel catalogado lo bloquea aparte validar_nivel_de_fuentes).
    """
    errores = []
    for ubicacion, noticia in todas_las_noticias(informe):
        if noticia["confianza"] != "confirmado":
            continue
        fuentes = noticia["fuentes"]
        dominios_distintos = {_dominio(f["url"]) for f in fuentes}
        hay_nivel_1_real = any(
            _nivel_catalogado(_dominio(f["url"]), fuentes_cfg) == 1 for f in fuentes
        )
        if len(dominios_distintos) < 2 and not hay_nivel_1_real:
            errores.append(
                f"[{ubicacion}] {noticia['id']}: confianza=confirmado pero no tiene "
                f"ni 2 fuentes de dominios distintos ni ninguna catalogada como nivel 1"
            )
    return errores


def validar_nivel_de_fuentes(informe: dict, fuentes_cfg: dict) -> list[str]:
    """El nivel que declara cada fuente debe coincidir con el de fuentes.yaml.

    Sin esto, el esquema solo exige que `nivel` sea 1, 2 o 3 — nada impedía
    que una noticia autodeclarase nivel=1 citando un dominio catalogado como
    nivel 2 (o al revés). Un dominio no catalogado no es error aquí: eso lo
    cubre avisos_fuentes_no_catalogadas, porque puede ser una fuente nueva
    legítima que solo falta añadir a la lista.
    """
    errores = []
    for ubicacion, noticia in todas_las_noticias(informe):
        for fuente in noticia["fuentes"]:
            dominio = _dominio(fuente["url"])
            nivel_real = _nivel_catalogado(dominio, fuentes_cfg)
            if nivel_real is not None and nivel_real != fuente["nivel"]:
                errores.append(
                    f"[{ubicacion}] {noticia['id']}: {dominio} está catalogado como "
                    f"nivel {nivel_real} en fuentes.yaml, pero la fuente declara "
                    f"nivel {fuente['nivel']}"
                )
    return errores


def avisos_fuentes_no_catalogadas(informe: dict, fuentes_cfg: dict) -> list[str]:
    """Aviso (no bloquea) por cada dominio citado que no está en fuentes.yaml.

    Puede ser una fuente nueva legítima — por eso es aviso, no error — pero
    conviene revisarla y, si corresponde, añadirla a fuentes.yaml en vez de
    dejarla citada sin catalogar semana tras semana.
    """
    avisos = []
    dominios_avisados: set[str] = set()
    for _, noticia in todas_las_noticias(informe):
        for fuente in noticia["fuentes"]:
            dominio = _dominio(fuente["url"])
            if dominio in dominios_avisados:
                continue
            if _nivel_catalogado(dominio, fuentes_cfg) is None:
                avisos.append(f"{dominio}: dominio no catalogado en fuentes.yaml")
                dominios_avisados.add(dominio)
    return avisos


def validar_titular(informe: dict) -> list[str]:
    """titular.noticia_id debe corresponder a una noticia real del informe.

    Sin esta comprobación, un id mal escrito o que quedó huérfano tras
    deduplicar en la "Unión" (sección 8) pasaría el esquema sin más —
    noticia_id es solo una cadena, el esquema no sabe qué ids existen
    (hallazgo real de /code-review).
    """
    ids_existentes = {n["id"] for _, n in todas_las_noticias(informe)}
    noticia_id = informe["titular"]["noticia_id"]
    if noticia_id not in ids_existentes:
        return [f"titular.noticia_id ('{noticia_id}') no corresponde a ninguna noticia del informe"]
    return []


def avisos_titular_largo(informe: dict, limite_caracteres: int = 60) -> list[str]:
    """Avisa (no bloquea) si el titular se pasa de largo.

    El titular se reutiliza tal cual como asunto del email
    (`"{NOMBRE}: {titular}"`, scripts/publish.py) — uno demasiado largo se
    trunca en varios clientes de correo. Es solo un aviso, no un error: es
    un problema de estilo, no de corrección del contenido.
    """
    texto = informe["titular"]["texto"]
    if len(texto) > limite_caracteres:
        return [f"titular.texto: {len(texto)} caracteres, supera el límite de {limite_caracteres}"]
    return []


def _parsear_numero(texto: str) -> float:
    """Extrae el primer número de un texto.

    Cuando aparecen los dos separadores, el último es el decimal y el otro
    es de miles (sirve tanto para "7.700,5" en español como para
    "7,700.5" en inglés). Con un solo separador no hay forma fiable de
    saber si es decimal o de miles (sin saber el idioma de origen), así
    que se asume siempre decimal — que es como vienen los números crudos
    en datos.json. Si el redactor escribe miles con un único punto o coma
    y sin parte decimal (p. ej. "7.700" queriendo decir siete mil
    setecientos), esta función lo interpretará mal a propósito: es
    preferible que validate.py señale una cifra para revisar a mano que
    adivinar en silencio.
    """
    # Normaliza los guiones tipográficos de signo negativo (−, – y —, que un
    # redactor o un editor de texto pueden escribir en vez del guion ASCII)
    # al guion normal: sin esto, "−2,3" se leía como +2,3 porque el regex
    # solo reconoce "-" (hallazgo real de revisión externa, confirmado con
    # una prueba contra las tres variantes).
    texto = texto.replace("−", "-").replace("–", "-").replace("—", "-")

    coincidencia = re.search(r"-?\d[\d.,]*", texto)
    if not coincidencia:
        raise ValueError(f"no se encontró ningún número en «{texto}»")
    # Quita puntuación final de frase ("2,3." al final de una oración no es
    # "veintitrés", el punto es solo el punto final — hallazgo real de
    # revisión externa, confirmado con una prueba).
    numero = coincidencia.group().rstrip(".,")

    if "," in numero and "." in numero:
        if numero.rindex(",") > numero.rindex("."):
            numero = numero.replace(".", "").replace(",", ".")
        else:
            numero = numero.replace(",", "")
    elif "," in numero:
        numero = numero.replace(",", ".")

    return float(numero)


def validar_cifras(informe: dict, datos: dict) -> list[str]:
    """Cada cifra con ref_datos debe existir en datos.json y coincidir en valor."""
    errores = []
    for ubicacion, noticia in todas_las_noticias(informe):
        for cifra in noticia.get("cifras", []):
            ref = cifra["ref_datos"]
            if ref is None:
                continue
            if ref not in datos:
                errores.append(
                    f"[{ubicacion}] {noticia['id']}: cifra «{cifra['valor']}» referencia "
                    f"'{ref}', que no existe en datos.json"
                )
                continue
            try:
                valor_cifra = _parsear_numero(cifra["valor"])
            except ValueError as exc:
                errores.append(
                    f"[{ubicacion}] {noticia['id']}: no se pudo interpretar la cifra "
                    f"«{cifra['valor']}» ({exc})"
                )
                continue
            valor_dato = float(datos[ref]["valor"])
            tolerancia = max(0.01, abs(valor_dato) * 0.005)
            if abs(valor_cifra - valor_dato) > tolerancia:
                errores.append(
                    f"[{ubicacion}] {noticia['id']}: cifra «{cifra['valor']}» "
                    f"({valor_cifra}) no coincide con datos.json['{ref}'] ({valor_dato})"
                )
    return errores


def validar_fechas_fuente(informe: dict, antiguedad_maxima_dias: int = 10) -> list[str]:
    """Una fuente más antigua que `antiguedad_maxima_dias` (prompts/redactor.md,
    config/fuentes.yaml) debe estar marcada como contexto histórico.

    No exige que la fuente caiga dentro del periodo exacto del informe: una
    noticia del lunes puede perfectamente citar un artículo del jueves
    anterior, que sigue siendo "de esta semana" a efectos periodísticos.
    Lo que no se permite sin marcar es una fuente más vieja que el límite
    de antigüedad, ni una fuente con fecha futura respecto al cierre del
    periodo (eso sería sospechoso, no "reciente").
    """
    fin = datetime.date.fromisoformat(informe["periodo"]["fin"])
    limite_antiguedad = fin - datetime.timedelta(days=antiguedad_maxima_dias)
    errores = []
    for ubicacion, noticia in todas_las_noticias(informe):
        for fuente in noticia["fuentes"]:
            if fuente.get("contexto_historico", False):
                continue
            fecha_fuente = datetime.date.fromisoformat(fuente["fecha"])
            if not (limite_antiguedad <= fecha_fuente <= fin):
                errores.append(
                    f"[{ubicacion}] {noticia['id']}: fuente del {fuente['fecha']} tiene más "
                    f"de {antiguedad_maxima_dias} días de antigüedad respecto al "
                    f"{fin.isoformat()} (o es posterior), y no está marcada como contexto histórico"
                )
    return errores


def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para que "pánico" y "PANICO" se traten igual."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.lower()


def _textos_publicos(informe: dict) -> list[tuple[str, str]]:
    """[(ubicacion, texto), ...] de todo lo que llega al email, no solo las noticias.

    `validar_palabras_prohibidas` solo miraba título/texto/por_qué_importa de
    cada noticia — un sensacionalismo o una recomendación de inversión en
    `titular.texto`, `lo_esencial`, `concepto_semana` o
    `perspectiva_largo_plazo` pasaba sin comprobar (hallazgo real de
    revisión externa, verificado contra el código).
    """
    textos = [
        (f"{ubicacion}:{noticia['id']}", " ".join([noticia["titulo"], noticia["texto"], noticia["por_que_importa"]]))
        for ubicacion, noticia in todas_las_noticias(informe)
    ]
    textos.append(("titular", informe["titular"]["texto"]))
    textos.extend(("lo_esencial", linea) for linea in informe["lo_esencial"])
    concepto = informe["concepto_semana"]
    textos.append(("concepto_semana", f"{concepto['titulo']} {concepto['texto']}"))
    perspectiva = informe["perspectiva_largo_plazo"]
    textos.extend(("perspectiva_largo_plazo.estructural", linea) for linea in perspectiva["estructural"])
    textos.extend(("perspectiva_largo_plazo.ruido", linea) for linea in perspectiva["ruido"])
    return textos


EntradaPalabra = str | dict[str, str]


def validar_palabras_prohibidas(
    informe: dict, palabras: Mapping[str, Sequence[EntradaPalabra]]
) -> list[str]:
    """Bloquea contenido con sensacionalismo o recomendaciones de inversión.

    Cada entrada de `palabras` (config/validacion.yaml) es, por defecto, una
    frase exacta que debe coincidir por límites de palabra tras normalizar
    tildes y mayúsculas — así "estallido" no haría saltar un "reestallido"
    por simple subcadena. Una entrada puede marcarse explícitamente para
    coincidir por raíz (subcadena, sin límites) con `{"raiz": "texto"}`, para
    los casos donde sí interese pillar variantes o conjugaciones.
    """
    todas_las_palabras = []
    for categoria, lista in palabras.items():
        for entrada in lista:
            if isinstance(entrada, dict):
                todas_las_palabras.append((categoria, _normalizar(entrada["raiz"]), True))
            else:
                todas_las_palabras.append((categoria, _normalizar(entrada), False))

    errores = []
    for ubicacion, texto in _textos_publicos(informe):
        texto_normalizado = _normalizar(texto)
        for categoria, palabra, es_raiz in todas_las_palabras:
            if es_raiz:
                encontrada = palabra in texto_normalizado
            else:
                encontrada = re.search(rf"\b{re.escape(palabra)}\b", texto_normalizado) is not None
            if encontrada:
                errores.append(f"[{ubicacion}] contiene «{palabra}» ({categoria})")
    return errores


def avisos_limite_palabras(informe: dict, modulos_cfg: list[dict]) -> list[str]:
    """Avisa si el texto de un módulo supera su límite de palabras."""
    limites = {m["id"]: m["limite_palabras"] for m in modulos_cfg}
    avisos = []
    for id_modulo in MODULOS_IDS:
        modulo = informe["modulos"][id_modulo]
        if modulo.get("sin_novedades"):
            continue
        texto = " ".join(
            " ".join([n["titulo"], n["texto"], n["por_que_importa"]])
            for n in modulo["noticias"]
        )
        n_palabras = len(texto.split())
        limite = limites.get(id_modulo)
        if limite and n_palabras > limite:
            avisos.append(
                f"Módulo '{id_modulo}': {n_palabras} palabras, supera el límite de {limite}"
            )
    return avisos


def avisos_concepto_semana_largo(informe: dict, limite_palabras: int = 120) -> list[str]:
    """Avisa si el texto de concepto_semana se pasa de las "4-5 líneas" de la sección 5.

    A diferencia de los módulos (avisos_limite_palabras, con su propio
    límite en config/modulos.yaml) o el titular (avisos_titular_largo),
    concepto_semana no tenía ninguna comprobación de longitud pese a que
    CLAUDE.md sí fija una — 120 palabras es una estimación en la misma
    proporción que el límite de los módulos (110 palabras para 3-5
    líneas).
    """
    n_palabras = len(informe["concepto_semana"]["texto"].split())
    if n_palabras > limite_palabras:
        return [f"concepto_semana: {n_palabras} palabras, supera el límite de {limite_palabras}"]
    return []


def avisos_concentracion_medios(informe: dict, umbral: float = 0.5) -> list[str]:
    """Avisa si más de `umbral` de las fuentes de UNA noticia son del mismo medio.

    Antes se calculaba sobre el total de fuentes de todo el informe, pero
    CLAUDE.md (sección 10) siempre dijo "more than 50% of a story's sources
    from a single outlet" — por historia, no por informe. El código no
    coincidía con lo documentado (hallazgo real de revisión externa,
    verificado contra CLAUDE.md).
    """
    avisos = []
    for ubicacion, noticia in todas_las_noticias(informe):
        medios: dict[str, int] = {}
        total = 0
        for fuente in noticia["fuentes"]:
            medios[fuente["medio"]] = medios.get(fuente["medio"], 0) + 1
            total += 1
        if total == 0:
            continue
        for medio, cuenta in medios.items():
            proporcion = cuenta / total
            if proporcion > umbral:
                avisos.append(
                    f"[{ubicacion}] {noticia['id']}: '{medio}' es el {proporcion:.0%} de sus "
                    f"fuentes (umbral: {umbral:.0%})"
                )
    return avisos


def avisos_cifras_sin_verificar(informe: dict) -> list[str]:
    """Avisa con el recuento de cifras con `ref_datos: null`, que validar_cifras
    nunca comprueba contra datos.json (son números sueltos de prensa, no de
    datos.json) — para poder revisar a ojo cuántas hay cada semana.
    """
    sin_verificar = sum(
        1
        for _, noticia in todas_las_noticias(informe)
        for cifra in noticia.get("cifras", [])
        if cifra["ref_datos"] is None
    )
    if sin_verificar:
        return [f"{sin_verificar} cifra(s) sin ref_datos, no comprobadas contra datos.json"]
    return []


def validar_ids_de_noticia_unicos(informe: dict) -> list[str]:
    """Cada id de noticia debe aparecer una sola vez en todo el informe."""
    ids = [noticia["id"] for _, noticia in todas_las_noticias(informe)]
    duplicados = sorted({id_ for id_ in ids if ids.count(id_) > 1})
    return [f"id de noticia duplicado: '{id_}'" for id_ in duplicados]


def validar_periodo_coherente_con_semana(informe: dict) -> list[str]:
    """periodo.inicio/fin debe ser exactamente el lunes y el domingo de `semana`."""
    lunes, domingo = periodo_de_semana(informe["semana"])
    inicio = datetime.date.fromisoformat(informe["periodo"]["inicio"])
    fin = datetime.date.fromisoformat(informe["periodo"]["fin"])
    if (inicio, fin) != (lunes, domingo):
        return [
            f"periodo ({inicio.isoformat()} a {fin.isoformat()}) no coincide con la semana "
            f"{informe['semana']} ({lunes.isoformat()} a {domingo.isoformat()})"
        ]
    return []


def validar_cambios_verificador_referencian_noticias_reales(informe: dict) -> list[str]:
    """Cada cambios_verificador[].noticia_id debe ser una noticia real del informe."""
    ids_existentes = {noticia["id"] for _, noticia in todas_las_noticias(informe)}
    return [
        f"cambios_verificador: noticia_id '{cambio['noticia_id']}' no corresponde a ninguna noticia del informe"
        for cambio in informe.get("cambios_verificador", [])
        if cambio["noticia_id"] not in ids_existentes
    ]


def avisos_modulo_sin_fuentes_fiables(informe: dict) -> list[str]:
    """Avisa si un módulo con novedades no tiene ninguna fuente de nivel 1 o 2."""
    avisos = []
    for id_modulo in MODULOS_IDS:
        modulo = informe["modulos"][id_modulo]
        if modulo.get("sin_novedades"):
            continue
        niveles = {
            fuente["nivel"] for noticia in modulo["noticias"] for fuente in noticia["fuentes"]
        }
        if niveles and niveles.issubset({3}):
            avisos.append(f"Módulo '{id_modulo}': ninguna fuente de nivel 1 o 2")
    return avisos


_NUMEROS_ES = {
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "doce": 12,
}

_PATRON_SEMANAS_SEGUIDAS = re.compile(
    r"(\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+semanas?\s+(seguidas|consecutivas)"
)
_PATRON_MAXIMO_MESES = re.compile(r"\bmaximos?\b.{0,20}?(\d+|tres|seis|nueve|doce)\s+mes(es)?")
_PATRON_MINIMO_MESES = re.compile(r"\bminimos?\b.{0,20}?(\d+|tres|seis|nueve|doce)\s+mes(es)?")

_PALABRAS_ALZA = ("alza", "subida", "suben", "sube", "subiendo", "repunte", "repunta")
_PALABRAS_BAJA = ("baja", "caida", "cae", "caen", "cayendo", "descenso", "desciende")


def _a_entero(texto: str) -> int:
    texto = texto.strip()
    return int(texto) if texto.isdigit() else _NUMEROS_ES.get(texto, 0)


def avisos_tendencias_inconsistentes(
    informe: dict, datos: Mapping[str, dict], historial_semanas: Mapping[str, dict]
) -> list[str]:
    """Avisa si una noticia afirma una tendencia que la propia serie de datos
    duros no respalda: "N semanas seguidas al alza/a la baja" cuando la
    serie no sube/baja esas N semanas, o "máximo/mínimo de N meses" cuando
    el valor actual no es, de hecho, el máximo/mínimo de las semanas
    disponibles.

    `datos` es el datos.json de esta semana (el mismo que usa
    validar_cifras). `historial_semanas` es {semana_iso: datos.json de esa
    semana} de semanas **anteriores**, en cualquier orden — se ordena aquí
    por la clave (funciona porque "AAAA-Sww" ordena cronológicamente como
    cadena) y se le añade al final el valor de esta semana, para que la
    serie siempre termine en el dato que la noticia está citando ahora.

    No bloquea: es texto libre, el patrón es aproximado por diseño (más
    falsos negativos que falsos positivos). Hallazgo real (semana
    2026-S43): una noticia sobre el Brent decía "tres semanas seguidas de
    subidas" cuando la serie real de datos duros había caído la última
    semana, y la regla previa del paquete de contexto permitía
    descartarlo como "solo una diferencia de fecha" sin comprobar los
    números.
    """
    semanas_ordenadas = sorted(historial_semanas)
    avisos = []
    for ubicacion, noticia in todas_las_noticias(informe):
        texto = _normalizar(f"{noticia['titulo']} {noticia['texto']}")
        for cifra in noticia.get("cifras", []):
            ref = cifra["ref_datos"]
            if ref is None or ref not in datos:
                continue
            serie = [
                historial_semanas[semana][ref]["valor"]
                for semana in semanas_ordenadas
                if ref in historial_semanas[semana]
            ]
            serie.append(datos[ref]["valor"])
            if len(serie) < 2:
                continue

            coincidencia = _PATRON_SEMANAS_SEGUIDAS.search(texto)
            if coincidencia:
                n = _a_entero(coincidencia.group(1))
                if 2 <= n <= len(serie):
                    ventana = serie[-n:]
                    sube_siempre = all(b > a for a, b in zip(ventana, ventana[1:]))
                    baja_siempre = all(b < a for a, b in zip(ventana, ventana[1:]))
                    dice_alza = any(p in texto for p in _PALABRAS_ALZA)
                    dice_baja = any(p in texto for p in _PALABRAS_BAJA)
                    if dice_alza and not sube_siempre:
                        avisos.append(
                            f"[{ubicacion}] {noticia['id']}: dice \"{n} semanas seguidas\" al "
                            f"alza sobre '{ref}', pero la serie real no sube esas {n} semanas "
                            f"seguidas ({ventana})"
                        )
                    elif dice_baja and not baja_siempre:
                        avisos.append(
                            f"[{ubicacion}] {noticia['id']}: dice \"{n} semanas seguidas\" a la "
                            f"baja sobre '{ref}', pero la serie real no baja esas {n} semanas "
                            f"seguidas ({ventana})"
                        )

            if _PATRON_MAXIMO_MESES.search(texto) and serie[-1] != max(serie):
                avisos.append(
                    f"[{ubicacion}] {noticia['id']}: dice un máximo reciente sobre '{ref}', "
                    f"pero no es el valor más alto del historial disponible ({serie})"
                )
            if _PATRON_MINIMO_MESES.search(texto) and serie[-1] != min(serie):
                avisos.append(
                    f"[{ubicacion}] {noticia['id']}: dice un mínimo reciente sobre '{ref}', "
                    f"pero no es el valor más bajo del historial disponible ({serie})"
                )
    return avisos
