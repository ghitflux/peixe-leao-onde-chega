"""Baixa as bases públicas para data/brutos/ e regrava o extrato agregado em data/.

Cada arquivo bruto é conferido (tamanho, formato ou contagem) ao chegar e não é baixado de novo se
já existe. A coleta inteira leva de 20 a 40 minutos, quase tudo em pausas entre requisições. Para
refazer do zero, apague data/brutos/.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

from peixe_leao import coleta, dados
from peixe_leao.geografia import TEATROS


def _etapa(nome: str, arquivo, funcao, *argumentos) -> None:
    if arquivo.exists():
        print(f"  já existe: {arquivo.name}")
        return
    inicio = time.time()
    funcao(*argumentos, arquivo)
    print(f"  {nome}: {arquivo.name} ({arquivo.stat().st_size / 1e6:.1f} MB, {time.time() - inicio:.0f} s)")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    brutos = dados.BRUTOS
    brutos.mkdir(parents=True, exist_ok=True)

    print("Registros de peixe-leão")
    _etapa("USGS NAS", brutos / "nas.json", coleta.baixar_nas)
    for teatro in TEATROS:
        _etapa("GBIF", brutos / f"gbif_{teatro}.json", coleta.baixar_gbif, teatro)
        _etapa("OBIS", brutos / f"obis_{teatro}.json", coleta.baixar_obis, teatro)

    print("Relevo, linha de costa e temperatura")
    _etapa("Natural Earth", brutos / "costa_110m.geojson", coleta.baixar_costa)
    for teatro in TEATROS:
        _etapa("ETOPO1", brutos / f"relevo_{teatro}.csv", coleta.baixar_relevo, teatro)
    for teatro in TEATROS:
        for ano in coleta.ANOS_OISST:
            _etapa("OISST", brutos / f"oisst_{teatro}_{ano}.nc", coleta.baixar_temperatura, teatro, ano)

    print("Esforço de observação (peixes recifais por célula e ano)")
    celulas = []
    for teatro in TEATROS:
        grade, _ = dados.montar_grade(teatro, dados.ler_relevo(teatro, brutos))
        celulas += list(grade[["celula", "lat_sul", "lon_oeste"]].itertuples(index=False, name=None))
    inicio = time.time()
    coleta.baixar_esforco(celulas, brutos / "esforco.json")
    print(f"  {len(celulas)} células ({time.time() - inicio:.0f} s)")

    print("Extrato agregado em data/")
    resumo = dados.preparar(brutos)
    registro = {
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "fontes": {
            "nas": coleta.NAS_URL,
            "gbif": f"{coleta.GBIF}/occurrence/search (taxonKey {coleta.GENERO_PTEROIS_GBIF}, gênero Pterois)",
            "obis": f"{coleta.OBIS}/occurrence (scientificname=Pterois)",
            "esforco": f"GBIF, contagem por célula e ano das famílias {', '.join(coleta.FAMILIAS_ESFORCO)}",
            "relevo": "NOAA ETOPO1 via ERDDAP (etopo180), um ponto a cada 0,1 grau",
            "temperatura": "NOAA OISST v2.1 via ERDDAP (ncdcOisst21Agg_LonPM180), 2011-2020, um dia a cada 30",
            "costa": "Natural Earth 1:110m (domínio público)",
        },
        "arquivos_brutos": coleta.resumo_dos_arquivos(brutos),
        **resumo,
    }
    (dados.PASTA / "coleta.json").write_text(json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")
    for linha in resumo["funil"]:
        print(f"  {linha['total']:>7}  {linha['passo']}")
    print(resumo["celulas"], resumo["celulas_com_registro"])


if __name__ == "__main__":
    main()
