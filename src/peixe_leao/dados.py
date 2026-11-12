"""Do bruto ao agregado: grade de células, limpeza dos registros e as tabelas versionadas em `data/`.

O dado central é o **ano do primeiro registro** de peixe-leão em cada célula de 1 grau da plataforma
continental, nos dois teatros da invasão. Só agregados por célula vão para o git; os registros
individuais (parte deles de conjuntos CC BY-NC) ficam em `data/brutos/`.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import netcdf_file
from scipy.ndimage import label, maximum_filter
from scipy.sparse.csgraph import connected_components

from peixe_leao import coleta
from peixe_leao.geografia import (
    ORIGENS,
    PROFUNDIDADE_MAXIMA_M,
    TEATROS,
    grafo_do_mar,
    id_da_celula,
    no_mais_proximo,
    teatro_do_ponto,
)

PASTA = Path("data")
BRUTOS = PASTA / "brutos"
MINIMO_PONTOS_PLATAFORMA = 2  # de 100 pontos de relevo por célula
ANO_FINAL = 2025  # último ano completo na data da coleta
JANELA_CORROBORACAO = 3  # anos em que um registro precisa ter outro por perto para datar a chegada
# No Mediterrâneo, a literatura revisada reconhece um único registro antes de 2012 (Israel, 1991;
# o segundo é do Líbano, em 2012: Bariche et al. 2013). Os registros públicos com data anterior a
# 2012 contradizem essa cronologia: ficam no extrato (coluna `ano_bruto`), mas não datam a chegada.
ANO_MINIMO_PARA_DATAR = {"atlantico": 1985, "mediterraneo": 2012}
PRIORIDADE = {"NAS": 0, "GBIF": 1, "OBIS": 2}


# ---------------------------------------------------------------- relevo e grade


def ler_relevo(teatro: str, brutos: Path = BRUTOS) -> dict:
    """Relevo do teatro como matriz [lat, lon] a cada 0,1 grau."""
    tabela = pd.read_csv(brutos / f"relevo_{teatro}.csv", skiprows=[1])
    lats = np.sort(tabela["latitude"].unique())
    lons = np.sort(tabela["longitude"].unique())
    altitude = tabela.pivot(index="latitude", columns="longitude", values="altitude").loc[lats, lons].to_numpy(float)
    return {"lat": lats, "lon": lons, "altitude": altitude}


def montar_grade(teatro: str, relevo: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Células de 1 grau com plataforma (0 a -300 m) dentro do teatro, e os nós de mar a cada 0,5 grau.

    Uma célula entra se pelo menos 2 dos seus 100 pontos de relevo são plataforma no teatro. O nó
    de mar existe se há mar do teatro em algum ponto a até 0,2 grau dele, o que mantém abertos os
    canais estreitos.
    """
    lat, lon, alt = relevo["lat"], relevo["lon"], relevo["altitude"]
    lon2, lat2 = np.meshgrid(lon, lat)
    no_teatro = teatro_do_ponto(lon2, lat2) == teatro
    mar = (alt < 0) & no_teatro
    # Só conta o mar ligado ao oceano: lagos e depressões abaixo do nível do mar ficam fora.
    rotulos, quantos = label(mar)
    if quantos > 1:
        mar = rotulos == (np.bincount(rotulos.ravel())[1:].argmax() + 1)
    plataforma = mar & (alt >= -PROFUNDIDADE_MAXIMA_M)

    pontos = pd.DataFrame(
        {
            "lat_sul": np.floor(lat2 + 1e-9).astype(int).ravel(),
            "lon_oeste": np.floor(lon2 + 1e-9).astype(int).ravel(),
            "lat": lat2.ravel(),
            "lon": lon2.ravel(),
            "plataforma": plataforma.ravel(),
        }
    )
    so_plataforma = pontos[pontos["plataforma"]]
    celulas = (
        so_plataforma.groupby(["lat_sul", "lon_oeste"])
        .agg(pontos_plataforma=("plataforma", "size"), lat_c=("lat", "mean"), lon_c=("lon", "mean"))
        .reset_index()
    )
    celulas = celulas[celulas["pontos_plataforma"] >= MINIMO_PONTOS_PLATAFORMA].copy()
    celulas.insert(0, "teatro", teatro)
    celulas.insert(0, "celula", [id_da_celula(teatro, s, o) for s, o in zip(celulas["lat_sul"], celulas["lon_oeste"])])
    celulas[["lat_c", "lon_c"]] = celulas[["lat_c", "lon_c"]].round(3)

    aberto = maximum_filter(mar.astype(np.uint8), size=5, mode="constant")[::5, ::5].astype(bool)
    lon_n, lat_n = np.meshgrid(lon[::5], lat[::5])
    nos = pd.DataFrame({"teatro": teatro, "lat": lat_n[aberto].round(2), "lon": lon_n[aberto].round(2)})

    # Na malha de 0,5 grau pode sobrar algum nó solto: fica só o maior conjunto de nós ligados entre
    # si, e as células presas a ele.
    _, componente = connected_components(grafo_do_mar(nos["lat"].to_numpy(), nos["lon"].to_numpy()), directed=False)
    principal = componente == np.bincount(componente).argmax()
    preso = no_mais_proximo(nos["lat"].to_numpy(), nos["lon"].to_numpy(), celulas["lat_c"].to_numpy(), celulas["lon_c"].to_numpy())
    celulas = celulas[principal[preso]]
    return celulas.reset_index(drop=True), nos[principal].reset_index(drop=True)


def em_terra(relevo: dict, lat, lon) -> np.ndarray:
    """Verdadeiro se o ponto e os seus oito vizinhos de 0,1 grau estão todos acima do nível do mar."""
    i = np.clip(np.rint((np.asarray(lat) - relevo["lat"][0]) * 10).astype(int), 1, len(relevo["lat"]) - 2)
    j = np.clip(np.rint((np.asarray(lon) - relevo["lon"][0]) * 10).astype(int), 1, len(relevo["lon"]) - 2)
    molhado = np.zeros(len(i), dtype=bool)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            molhado |= relevo["altitude"][i + di, j + dj] < 0
    return ~molhado


# ---------------------------------------------------------------- temperatura


def temperatura_do_mes_mais_frio(teatro: str, brutos: Path = BRUTOS) -> dict:
    """Climatologia 2011-2020 do OISST: média de cada mês do ano e, por ponto, o mês mais frio."""
    campos, meses = [], []
    for ano in coleta.ANOS_OISST:
        with netcdf_file(str(brutos / f"oisst_{teatro}_{ano}.nc"), mmap=False, maskandscale=True) as arquivo:
            sst = np.ma.filled(arquivo.variables["sst"][:].astype(float), np.nan)[:, 0]
            tempo = pd.to_datetime(arquivo.variables["time"][:].astype("int64"), unit="s")
            lat = arquivo.variables["latitude"][:].astype(float)
            lon = arquivo.variables["longitude"][:].astype(float)
        campos.append(sst)
        meses.append(tempo.month.to_numpy())
    campos, meses = np.concatenate(campos), np.concatenate(meses)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # pontos de terra são só NaN
        por_mes = np.stack([np.nanmean(campos[meses == m], axis=0) for m in range(1, 13)])
        minimo = np.nanmin(por_mes, axis=0)
    return {"lat": lat, "lon": lon, "tmin": minimo}


def temperatura_por_celula(celulas: pd.DataFrame, campo: dict) -> np.ndarray:
    """Temperatura do mês mais frio em cada célula: média dos pontos de mar dentro dela ou, sem nenhum, o mais próximo."""
    lon2, lat2 = np.meshgrid(campo["lon"], campo["lat"])
    valido = np.isfinite(campo["tmin"])
    lat_v, lon_v, t_v = lat2[valido], lon2[valido], campo["tmin"][valido]
    saida = np.full(len(celulas), np.nan)
    for k, (s, o, lc, oc) in enumerate(celulas[["lat_sul", "lon_oeste", "lat_c", "lon_c"]].to_numpy()):
        dentro = (lat_v >= s) & (lat_v < s + 1) & (lon_v >= o) & (lon_v < o + 1)
        if dentro.any():
            saida[k] = t_v[dentro].mean()
        else:
            saida[k] = t_v[np.argmin((lat_v - lc) ** 2 + (lon_v - oc) ** 2)]
    return saida.round(2)


# ---------------------------------------------------------------- registros


def _data_do_nas(r: dict) -> tuple:
    return r.get("year"), r.get("month"), r.get("day")


def ler_registros(brutos: Path = BRUTOS) -> pd.DataFrame:
    """Junta as três fontes num formato comum, sem limpar nada ainda."""
    linhas = []
    for r in json.loads((brutos / "nas.json").read_text(encoding="utf-8"))["results"]:
        ano, mes, dia = _data_do_nas(r)
        linhas.append(
            {
                "fonte": "NAS", "id": str(r["key"]), "conjunto": "NAS", "lat": r.get("decimalLatitude"),
                "lon": r.get("decimalLongitude"), "ano": ano, "mes": mes, "dia": dia, "base": r.get("recordType"),
                "ocorrencia": None, "situacao": r.get("status") or "",
            }
        )  # fmt: skip
    for teatro in TEATROS:
        for r in json.loads((brutos / f"gbif_{teatro}.json").read_text(encoding="utf-8"))["registros"]:
            linhas.append(
                {
                    "fonte": "GBIF", "id": str(r["key"]), "conjunto": r.get("datasetKey"), "lat": r.get("decimalLatitude"),
                    "lon": r.get("decimalLongitude"), "ano": r.get("year"), "mes": r.get("month"), "dia": r.get("day"),
                    "base": r.get("basisOfRecord"), "ocorrencia": r.get("occurrenceID"),
                    "situacao": r.get("establishmentMeans") or "",
                }
            )  # fmt: skip
        for r in json.loads((brutos / f"obis_{teatro}.json").read_text(encoding="utf-8")):
            data = pd.to_datetime(str(r.get("eventDate") or "")[:10], errors="coerce")
            completa = pd.notna(data) and len(str(r.get("eventDate") or "")) >= 10
            linhas.append(
                {
                    "fonte": "OBIS", "id": r["id"], "conjunto": r.get("dataset_id"), "lat": r.get("decimalLatitude"),
                    "lon": r.get("decimalLongitude"), "ano": r.get("date_year"), "mes": data.month if completa else None,
                    "dia": data.day if completa else None, "base": r.get("basisOfRecord"),
                    "ocorrencia": r.get("occurrenceID"), "situacao": "",
                }
            )  # fmt: skip
    tabela = pd.DataFrame(linhas)
    for coluna in ("lat", "lon", "ano", "mes", "dia"):
        tabela[coluna] = pd.to_numeric(tabela[coluna], errors="coerce")
    return tabela.drop_duplicates(subset=["fonte", "id"]).reset_index(drop=True)


def remover_duplicatas(registros: pd.DataFrame) -> pd.DataFrame:
    """Tira o mesmo registro que aparece em mais de uma fonte, ficando com NAS, depois GBIF, depois OBIS.

    Três critérios, nesta ordem: (1) o conjunto do NAS republicado dentro do GBIF e do OBIS; (2) o mesmo
    identificador de ocorrência (por exemplo, a mesma observação do iNaturalist no GBIF e no OBIS);
    (3) mesma coordenada arredondada a 0,01 grau e mesma data (ano, mês e dia; se a data só tem
    ano, mesmo ano).
    """
    nas_repetido = registros["conjunto"].isin([coleta.CONJUNTO_NAS_NO_GBIF, coleta.CONJUNTO_NAS_NO_OBIS])
    t = registros[~nas_repetido].copy()
    t["_ordem"] = t["fonte"].map(PRIORIDADE)
    t = t.sort_values(["_ordem", "id"], kind="stable")
    com_id = t["ocorrencia"].notna() & (t["ocorrencia"].astype(str).str.len() > 8)
    t = pd.concat([t[com_id].drop_duplicates(subset="ocorrencia"), t[~com_id]]).sort_values(["_ordem", "id"], kind="stable")
    chave = [t["lat"].round(2), t["lon"].round(2), t["ano"], t["mes"].fillna(0), t["dia"].fillna(0)]
    t = t[~pd.concat(chave, axis=1).duplicated()]
    return t.drop(columns="_ordem").reset_index(drop=True)


def limpar_registros(registros: pd.DataFrame, grades: dict[str, pd.DataFrame], relevos: dict[str, dict]) -> tuple[pd.DataFrame, list[dict]]:
    """Aplica os filtros em ordem e devolve os registros limpos, já com a célula, e o funil de contagens."""
    funil = []

    def passo(nome: str, tabela: pd.DataFrame) -> pd.DataFrame:
        contagem = tabela["fonte"].value_counts()
        funil.append({"passo": nome, "total": int(len(tabela)), **{f: int(contagem.get(f, 0)) for f in PRIORIDADE}})
        return tabela

    t = passo("Registros baixados (gênero Pterois nas caixas dos dois teatros; NAS inteiro)", registros)
    t = passo("Com coordenada e ano", t[t["lat"].notna() & t["lon"].notna() & t["ano"].notna()])
    t = t.assign(teatro=teatro_do_ponto(t["lon"], t["lat"]))
    t = passo("Dentro da área invadida (fora do Pacífico, do Mar Vermelho e do Mar Negro)", t[t["teatro"] != ""])
    cativeiro = t["base"].astype(str).str.upper().str.replace("_", "").isin(["LIVINGSPECIMEN", "FOSSILSPECIMEN"])
    cativeiro |= t["situacao"].astype(str).str.lower().isin(["managed", "stocked"])
    t = passo("Sem espécime vivo de coleção ou aquário", t[~cativeiro])
    plausivel = pd.Series(True, index=t.index)
    for teatro, origem in ORIGENS.items():
        plausivel &= ~((t["teatro"] == teatro) & (t["ano"] < origem["ano"]))
    t = passo("Com ano entre a introdução e o último ano completo", t[plausivel & (t["ano"] <= ANO_FINAL)])
    t = passo("Sem duplicata entre fontes", remover_duplicatas(t))

    partes = []
    for teatro, grade in grades.items():
        parte = t[t["teatro"] == teatro].copy()
        parte = parte[~em_terra(relevos[teatro], parte["lat"], parte["lon"])]
        partes.append(parte)
    t = passo("Sem coordenada em terra (ponto e vizinhos de 0,1 grau acima do nível do mar)", pd.concat(partes))

    partes = []
    for teatro, grade in grades.items():
        parte = t[t["teatro"] == teatro].copy()
        parte["celula"] = atribuir_celula(grade, parte["lat"].to_numpy(), parte["lon"].to_numpy())
        partes.append(parte)
    t = pd.concat(partes)
    t = passo("Em célula de plataforma, ou a até uma célula de distância (fica na mais próxima)", t[t["celula"].notna()])
    return t.reset_index(drop=True), funil


def atribuir_celula(grade: pd.DataFrame, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Célula de plataforma de cada ponto; se a célula do ponto não é de plataforma, a vizinha mais próxima."""
    indice = {(s, o): (c, lc, oc) for c, s, o, lc, oc in grade[["celula", "lat_sul", "lon_oeste", "lat_c", "lon_c"]].to_numpy()}
    saida = np.full(len(lat), None, dtype=object)
    for k, (la, lo) in enumerate(zip(lat, lon)):
        s, o = int(np.floor(la)), int(np.floor(lo))
        if (s, o) in indice:
            saida[k] = indice[(s, o)][0]
            continue
        vizinhas = [indice[(s + ds, o + do)] for ds in (-1, 0, 1) for do in (-1, 0, 1) if (s + ds, o + do) in indice]
        if vizinhas:
            saida[k] = min(vizinhas, key=lambda v: (v[1] - la) ** 2 + (v[2] - lo) ** 2)[0]
    return saida


def marcar_corroborados(
    registros: pd.DataFrame, grade: pd.DataFrame, janela: int = JANELA_CORROBORACAO, ano_minimo: int = 0
) -> np.ndarray:
    """Marca os registros que servem para datar a chegada: os que têm algum outro registro por perto.

    A regra: existe outro registro na mesma célula ou numa das oito vizinhas, no mesmo ano ou nos
    `janela` anos seguintes. Um registro sozinho, sem sucessor, pode ser erro de data, de
    identificação ou um animal solto que não deixou população. Registros anteriores a `ano_minimo`
    não datam a chegada nem corroboram outros.
    """
    posicao = {c: (s, o) for c, s, o in grade[["celula", "lat_sul", "lon_oeste"]].to_numpy()}
    preciso = (registros["ano"] >= ano_minimo).to_numpy()
    contagem: dict[tuple, int] = {}
    for celula, ano in zip(registros["celula"].to_numpy()[preciso], registros["ano"].to_numpy()[preciso]):
        s, o = posicao[celula]
        contagem[(s, o, int(ano))] = contagem.get((s, o, int(ano)), 0) + 1
    saida = np.zeros(len(registros), dtype=bool)
    for k, (celula, ano, ok) in enumerate(zip(registros["celula"].to_numpy(), registros["ano"].to_numpy(), preciso)):
        if not ok:
            continue
        s, o = posicao[celula]
        perto = sum(
            contagem.get((s + ds, o + do, int(ano) + da), 0) for ds in (-1, 0, 1) for do in (-1, 0, 1) for da in range(janela + 1)
        )
        saida[k] = perto >= 2  # o próprio registro e pelo menos mais um
    return saida


# ---------------------------------------------------------------- agregados versionados


def preparar(brutos: Path = BRUTOS, destino: Path = PASTA) -> dict:
    """Lê os brutos e grava em `data/` as tabelas agregadas de que a análise precisa para rodar sem rede."""
    relevos = {teatro: ler_relevo(teatro, brutos) for teatro in TEATROS}
    grades, nos = {}, []
    for teatro in TEATROS:
        grade, nos_teatro = montar_grade(teatro, relevos[teatro])
        grade["tmin_c"] = temperatura_por_celula(grade, temperatura_do_mes_mais_frio(teatro, brutos))
        grades[teatro] = grade
        nos.append(nos_teatro)
    celulas = pd.concat(grades.values(), ignore_index=True)

    registros, funil = limpar_registros(ler_registros(brutos), grades, relevos)
    registros["corroborado"] = False
    for teatro, grade in grades.items():
        do_teatro = (registros["teatro"] == teatro).to_numpy()
        registros.loc[do_teatro, "corroborado"] = marcar_corroborados(
            registros[do_teatro], grade, ano_minimo=ANO_MINIMO_PARA_DATAR[teatro]
        )
    contagem = registros.loc[registros["corroborado"], "fonte"].value_counts()
    funil.append(
        {
            "passo": "Servem para datar a chegada (têm outro registro por perto em até 3 anos)",
            "total": int(registros["corroborado"].sum()),
            **{f: int(contagem.get(f, 0)) for f in PRIORIDADE},
        }
    )
    bons = registros[registros["corroborado"]]
    # ano do primeiro registro corroborado (o dado central) e ano do primeiro registro de qualquer tipo
    celulas["ano_primeiro_registro"] = celulas["celula"].map(bons.groupby("celula")["ano"].min()).astype("Int64")
    celulas["ano_bruto"] = celulas["celula"].map(registros.groupby("celula")["ano"].min()).astype("Int64")
    for fonte in PRIORIDADE:
        da_fonte = bons[bons["fonte"] == fonte].groupby("celula")["ano"].min()
        celulas[f"ano_{fonte.lower()}"] = celulas["celula"].map(da_fonte).astype("Int64")
    celulas["registros"] = celulas["celula"].map(registros.groupby("celula").size()).fillna(0).astype(int)
    celulas["registros_corroborados"] = celulas["celula"].map(bons.groupby("celula").size()).fillna(0).astype(int)

    por_ano = registros.groupby(["celula", "ano"]).agg(registros=("id", "size"), corroborados=("corroborado", "sum")).reset_index()
    por_ano["ano"] = por_ano["ano"].astype(int)

    esforco = json.loads((brutos / "esforco.json").read_text(encoding="utf-8"))
    linhas = [
        {"celula": c, "ano": int(ano), "registros_recifais": n} for c, anos in esforco.items() for ano, n in anos.items()
    ]
    esforco_tabela = pd.DataFrame(linhas).sort_values(["celula", "ano"])
    esforco_tabela = esforco_tabela[esforco_tabela["celula"].isin(celulas["celula"])]

    destino.mkdir(parents=True, exist_ok=True)
    celulas.to_csv(destino / "celulas.csv", index=False)
    por_ano.to_csv(destino / "registros_por_celula_ano.csv", index=False)
    esforco_tabela.to_csv(destino / "esforco_por_celula_ano.csv", index=False)
    pd.concat(nos, ignore_index=True).to_csv(destino / "nos_de_mar.csv", index=False)
    if (brutos / "costa_110m.geojson").exists():
        (destino / "costa_110m.geojson").write_bytes((brutos / "costa_110m.geojson").read_bytes())
    ausencias = {
        teatro: int(json.loads((brutos / f"gbif_{teatro}.json").read_text(encoding="utf-8"))["ausencias_nao_baixadas"]) for teatro in TEATROS
    }
    return {
        "funil": funil,
        "ausencias_no_gbif": ausencias,
        "celulas": {t: int((celulas["teatro"] == t).sum()) for t in TEATROS},
        "celulas_com_registro": {t: int(celulas.loc[celulas["teatro"] == t, "ano_primeiro_registro"].notna().sum()) for t in TEATROS},
        "registros_limpos_por_teatro": {t: int((registros["teatro"] == t).sum()) for t in TEATROS},
        "conjuntos_de_dados": int(registros["conjunto"].nunique()),
    }


# ---------------------------------------------------------------- carga


def carregar(pasta: Path = PASTA) -> dict:
    """Lê o extrato agregado versionado em `data/`."""
    celulas = pd.read_csv(pasta / "celulas.csv")
    for coluna in ("ano_primeiro_registro", "ano_bruto", "ano_nas", "ano_gbif", "ano_obis"):
        celulas[coluna] = celulas[coluna].astype("Int64")
    geo = json.loads((pasta / "costa_110m.geojson").read_text(encoding="utf-8"))
    costa = []
    for feicao in geo["features"]:
        geometria = feicao["geometry"]
        trechos = [geometria["coordinates"]] if geometria["type"] == "LineString" else geometria["coordinates"]
        costa += [np.asarray(trecho, dtype=float) for trecho in trechos]
    return {
        "celulas": celulas,
        "registros": pd.read_csv(pasta / "registros_por_celula_ano.csv"),
        "esforco": pd.read_csv(pasta / "esforco_por_celula_ano.csv"),
        "nos": pd.read_csv(pasta / "nos_de_mar.csv"),
        "costa": costa,
        "coleta": json.loads((pasta / "coleta.json").read_text(encoding="utf-8")),
    }
