"""Coleta das bases públicas para `data/brutos/` (fora do git). Uma requisição por vez, com pausa.

Fontes (todas sem chave):
- USGS Nonindigenous Aquatic Species (NAS): registros de Pterois volitans/miles (species_ID 963).
- GBIF e OBIS: registros do gênero Pterois dentro das caixas dos dois teatros da invasão.
- GBIF: contagem por célula e ano de registros de famílias de peixes recifais e costeiros (esforço).
- NOAA ETOPO1 (relevo) e NOAA OISST v2.1 (temperatura da superfície do mar), via ERDDAP.
- Natural Earth 1:110m (linha de costa, só para desenhar os mapas).
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from peixe_leao.geografia import TEATROS

AGENTE = "portfolio-estudos/1.0"
PAUSA_S = 0.4
BRUTOS = Path("data") / "brutos"

NAS_URL = "https://nas.er.usgs.gov/api/v2/occurrence/search?species_ID=963"
GBIF = "https://api.gbif.org/v1"
OBIS = "https://api.obis.org/v3"
ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
COSTA_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_coastline.geojson"

GENERO_PTEROIS_GBIF = 2334432
CONJUNTO_NAS_NO_GBIF = "d6cc311c-c5ab-4f23-9a20-10514f9eb9c4"  # o NAS também é publicado no GBIF
CONJUNTO_NAS_NO_OBIS = "62125eda-53d3-41bd-ae1f-1b7e0cda2963"  # e no OBIS
# Famílias de peixes recifais e costeiros usadas como indicador de esforço de observação (chaves do GBIF).
FAMILIAS_ESFORCO = {
    "Pomacentridae": 4499, "Labridae": 8535, "Scaridae": 4504, "Chaetodontidae": 8517, "Acanthuridae": 4233,
    "Pomacanthidae": 4498, "Haemulidae": 4276, "Lutjanidae": 8542, "Serranidae": 8597, "Epinephelidae": 8172666,
    "Sparidae": 5068,
}  # fmt: skip
ANOS_OISST = range(2011, 2021)

CAMPOS_GBIF = (
    "key", "datasetKey", "species", "scientificName", "decimalLatitude", "decimalLongitude", "year", "month", "day",
    "basisOfRecord", "establishmentMeans", "occurrenceID", "coordinateUncertaintyInMeters", "license", "issues",
)  # fmt: skip
CAMPOS_OBIS = (
    "id", "dataset_id", "scientificName", "decimalLatitude", "decimalLongitude", "date_year", "eventDate",
    "basisOfRecord", "occurrenceID", "coordinateUncertaintyInMeters", "license", "flags", "shoredistance", "bathymetry",
)  # fmt: skip


def _abrir(url: str, tentativas: int = 5, espera: int = 240) -> bytes:
    """Uma requisição, com repetição e espera crescente."""
    requisicao = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    for tentativa in range(1, tentativas + 1):
        try:
            with urllib.request.urlopen(requisicao, timeout=espera) as resposta:
                corpo = resposta.read()
            time.sleep(PAUSA_S)
            return corpo
        except (urllib.error.URLError, TimeoutError, ConnectionError) as erro:
            if tentativa == tentativas:
                raise RuntimeError(f"falha ao baixar {url[:120]}: {erro}") from erro
            time.sleep(8 * tentativa)
    raise RuntimeError("inalcançável")


def _json(url: str) -> dict:
    return json.loads(_abrir(url))


def _caixa_wkt(teatro: str) -> str:
    """Polígono da caixa do teatro, em sentido anti-horário (o GBIF exige)."""
    (o, l), (s, n) = TEATROS[teatro]["lon"], TEATROS[teatro]["lat"]
    return f"POLYGON(({o} {s},{l} {s},{l} {n},{o} {n},{o} {s}))"


def baixar_nas(destino: Path) -> None:
    corpo = _abrir(NAS_URL)
    if len(corpo) < 5_000_000 or json.loads(corpo)["count"] < 10_000:
        raise RuntimeError("resposta do NAS menor que o esperado (cerca de 11 MB e mais de 12 mil registros)")
    destino.write_bytes(corpo)


def contar_ausencias_gbif(teatro: str) -> int:
    """Quantos registros do gênero na caixa do teatro são de ausência (a faceta os chama de NOT_DETECTED)."""
    consulta = {"taxonKey": GENERO_PTEROIS_GBIF, "hasCoordinate": "true", "geometry": _caixa_wkt(teatro), "limit": 0}
    faceta = _json(f"{GBIF}/occurrence/search?{urllib.parse.urlencode({**consulta, 'facet': 'occurrenceStatus'})}")
    return sum(c["count"] for c in faceta["facets"][0]["counts"] if c["name"] in ("ABSENT", "NOT_DETECTED"))


def baixar_gbif(teatro: str, destino: Path) -> None:
    """Registros do gênero Pterois com coordenada e ano na caixa do teatro.

    A busca é feita ano a ano, 300 por página: a paginação profunda do GBIF numa consulta só fica
    lenta (dezenas de segundos por página depois de 30 mil registros).
    """
    tudo = {"taxonKey": GENERO_PTEROIS_GBIF, "hasCoordinate": "true", "geometry": _caixa_wkt(teatro)}
    # A busca do GBIF devolve também registros de AUSÊNCIA (censos que procuraram e não acharam).
    # Só os de presença são baixados; a contagem das ausências fica guardada para o funil.
    ausencias = contar_ausencias_gbif(teatro)
    base = {**tudo, "occurrenceStatus": "PRESENT"}
    faceta = _json(f"{GBIF}/occurrence/search?{urllib.parse.urlencode({**base, 'limit': 0, 'facet': 'year', 'facetLimit': 400})}")
    por_ano = {int(c["name"]): c["count"] for c in faceta["facets"][0]["counts"]}
    registros = []
    for ano in sorted(por_ano):
        deslocamento = 0
        while True:
            consulta = urllib.parse.urlencode({**base, "year": ano, "limit": 300, "offset": deslocamento})
            pagina = _json(f"{GBIF}/occurrence/search?{consulta}")
            registros += [{c: r.get(c) for c in CAMPOS_GBIF} for r in pagina["results"]]
            deslocamento += 300
            if pagina["endOfRecords"]:
                break
    if len(registros) < 0.99 * sum(por_ano.values()):
        raise RuntimeError(f"GBIF {teatro}: {len(registros)} de {sum(por_ano.values())} registros")
    destino.write_text(json.dumps({"ausencias_nao_baixadas": ausencias, "registros": registros}), encoding="utf-8")


def baixar_obis(teatro: str, destino: Path) -> None:
    """Registros do gênero Pterois na caixa do teatro, paginados pelo identificador."""
    base = {"scientificname": "Pterois", "geometry": _caixa_wkt(teatro), "size": 5000, "fields": ",".join(CAMPOS_OBIS)}
    registros, depois = [], None
    while True:
        parametros = dict(base) if depois is None else {**base, "after": depois}
        pagina = _json(f"{OBIS}/occurrence?{urllib.parse.urlencode(parametros)}")
        lote = pagina["results"]
        registros += lote
        if len(lote) < 5000:
            total = pagina["total"]
            break
        depois = lote[-1]["id"]
    if len(registros) < total:
        raise RuntimeError(f"OBIS {teatro}: {len(registros)} de {total} registros")
    destino.write_text(json.dumps(registros), encoding="utf-8")


def baixar_relevo(teatro: str, destino: Path) -> None:
    """ETOPO1 a cada 0,1 grau (um ponto em seis da grade de 1 minuto de arco)."""
    (o, l), (s, n) = TEATROS[teatro]["lon"], TEATROS[teatro]["lat"]
    corpo = _abrir(f"{ERDDAP}/etopo180.csv?altitude[({s}):6:({n})][({o}):6:({l})]", espera=600)
    esperado = (round((n - s) * 10) + 1) * (round((l - o) * 10) + 1)
    if corpo.count(b"\n") < esperado:
        raise RuntimeError(f"relevo de {teatro}: menos linhas que o esperado ({esperado})")
    destino.write_bytes(corpo)


def baixar_temperatura(teatro: str, ano: int, destino: Path) -> None:
    """OISST: um dia a cada 30, numa grade de 0,5 grau, em NetCDF-3 (lido com scipy.io)."""
    (o, l), (s, n) = TEATROS[teatro]["lon"], TEATROS[teatro]["lat"]
    consulta = f"sst[({ano}-01-15T12:00:00Z):30:({ano}-12-31T12:00:00Z)][(0.0)][({s}):2:({n})][({o}):2:({l})]"
    corpo = _abrir(f"{ERDDAP}/ncdcOisst21Agg_LonPM180.nc?{consulta}", espera=600)
    if not corpo.startswith(b"CDF") or len(corpo) < 50_000:
        raise RuntimeError(f"temperatura de {teatro} em {ano}: arquivo inesperado")
    destino.write_bytes(corpo)
    time.sleep(3)


def baixar_esforco(celulas: list[tuple[str, int, int]], destino: Path) -> None:
    """Para cada célula (id, lat sul, lon oeste), registros por ano das famílias recifais no GBIF.

    Usa só a contagem por faceta (`limit=0`): nenhum registro individual é baixado. Grava a cada 40
    células para poder retomar.
    """
    feito = json.loads(destino.read_text(encoding="utf-8")) if destino.exists() else {}
    taxons = "&".join(f"taxonKey={chave}" for chave in FAMILIAS_ESFORCO.values())
    for numero, (celula, s, o) in enumerate(celulas, 1):
        if celula in feito:
            continue
        wkt = f"POLYGON(({o} {s},{o + 1} {s},{o + 1} {s + 1},{o} {s + 1},{o} {s}))"
        resto = urllib.parse.urlencode(
            {"geometry": wkt, "hasCoordinate": "true", "limit": 0, "facet": "year", "facetLimit": 300, "year": "1950,2026"}
        )
        resposta = _json(f"{GBIF}/occurrence/search?{taxons}&{resto}")
        contagens = resposta["facets"][0]["counts"] if resposta.get("facets") else []
        feito[celula] = {c["name"]: c["count"] for c in contagens}
        if numero % 40 == 0:
            destino.write_text(json.dumps(feito), encoding="utf-8")
    destino.write_text(json.dumps(feito), encoding="utf-8")


def baixar_costa(destino: Path) -> None:
    corpo = _abrir(COSTA_URL)
    if json.loads(corpo)["type"] != "FeatureCollection":
        raise RuntimeError("linha de costa: arquivo inesperado")
    destino.write_bytes(corpo)


def resumo_dos_arquivos(pasta: Path = BRUTOS) -> dict:
    """Tamanho e SHA-256 de cada arquivo bruto, para registrar o que foi coletado."""
    return {
        arquivo.name: {"bytes": arquivo.stat().st_size, "sha256": hashlib.sha256(arquivo.read_bytes()).hexdigest()[:16]}
        for arquivo in sorted(pasta.iterdir())
        if arquivo.is_file()
    }
