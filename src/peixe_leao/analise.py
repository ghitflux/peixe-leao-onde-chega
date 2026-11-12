"""Orquestra cada tabela do estudo a partir do extrato agregado em `data/`."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from peixe_leao import espalhamento as esp
from peixe_leao import frente
from peixe_leao.dados import ANO_MINIMO_PARA_DATAR
from peixe_leao.geografia import ORIGENS, TEATROS, distancias_pelo_mar

ANO_FINAL = 2025  # último ano completo na coleta
# Ano a partir do qual a expansão é contada em cada teatro. No Atlântico, não houve novo registro
# nos EUA entre 1985 e 2000 (Schofield 2009); no Mediterrâneo, o segundo registro é de 2012, 21 anos
# depois do primeiro (Bariche et al. 2013). As células com registro até esse ano são as sementes.
INICIO_EXPANSAO = {"atlantico": 2000, "mediterraneo": 2012}
CORTES = {"atlantico": [2010, 2018], "mediterraneo": [2018]}
HORIZONTES = (5, 10)
HORIZONTE_PREVISAO = 10
JANELA_ESFORCO = 3  # anos da média móvel do esforço
# Temperaturas de Kimball et al. (2004) para o complexo P. volitans/miles, em graus Celsius.
TEMPERATURA_LETAL = 10.0
TEMPERATURA_SEM_ALIMENTACAO = 16.1

# As três formas do modelo comparadas na validação.
FORMAS = {
    "modelo": esp.Forma(suscetivel=True, termico=True),  # o completo
    "modelo_sem_temperatura": esp.Forma(suscetivel=True, termico=False),
    "modelo_sem_fracao_suscetivel": esp.Forma(suscetivel=False, termico=False),  # a primeira versão
}
# Forma usada na previsão de cada teatro. A regra, fixada antes de olhar a previsão: a temperatura
# entra se, na validação daquele teatro, reduzir o erro de Brier em todos os cortes e horizontes.
# O resultado da regra fica em `resultados.json` (`escolha_da_forma`).
ROTULOS = {
    "modelo": "Modelo de espalhamento (completo)",
    "modelo_sem_temperatura": "Modelo sem temperatura",
    "modelo_sem_fracao_suscetivel": "Modelo sem fração suscetível (1ª versão)",
    "velocidade_constante": "Velocidade constante",
    "vizinha": "Célula vizinha",
}


@dataclass
class Teatro:
    chave: str
    nome: str
    celulas: pd.DataFrame
    distancias: np.ndarray  # célula x célula, km pelo mar
    distancia_origem: np.ndarray  # km pelo mar até o ponto de introdução
    primeiro: np.ndarray  # ano do primeiro registro (nan = sem registro)
    anos_esforco: np.ndarray
    esforco: np.ndarray  # [ano, célula], média móvel de três anos dos registros de peixes recifais
    habitat: np.ndarray  # [ano, célula], log(1 + registros de peixes recifais acumulados até o ano)
    tmin: np.ndarray
    isolada: np.ndarray  # células cujo registro a literatura atribui a soltura isolada, fora da frente
    ramo: np.ndarray  # células do ramo em que a frente é medida

    @property
    def inicio(self) -> int:
        return INICIO_EXPANSAO[self.chave]

    @property
    def na_frente(self) -> np.ndarray:
        """Células que contam para medir a frente: as do ramo, sem o registro isolado."""
        return self.ramo & ~self.isolada

    def _linha(self, ano: int) -> int:
        return int(np.clip(ano, self.anos_esforco[0], self.anos_esforco[-1]) - self.anos_esforco[0])

    def esforco_no_ano(self, ano: int) -> np.ndarray:
        return self.esforco[self._linha(ano)]

    def habitat_no_ano(self, ano: int) -> np.ndarray:
        return self.habitat[self._linha(ano)]


# Registro isolado que a literatura trata como possível soltura de aquário, sem população em volta:
# Arraial do Cabo (RJ), avistado em 2014 e 2015 (Ferreira et al. 2015; Luiz et al. 2021).
def _isolada(celulas: pd.DataFrame) -> np.ndarray:
    return ((celulas["lat_c"] < -20.0) & (celulas["lat_c"] > -25.0) & (celulas["lon_c"] > -44.0) & (celulas["lon_c"] < -40.0)).to_numpy()


# No Atlântico a invasão saiu da Flórida em dois ramos. Para o norte, pela costa leste dos EUA, a
# Corrente do Golfo levou o peixe até Nova York em 2001, e ali ele não passa o inverno (Kimball et
# al. 2004): não é uma frente que avança. A frente que interessa é a que vai para o sul e o oeste
# (Bahamas, Caribe, Golfo do México, América do Sul). A velocidade é medida nela.
def _ramo_sul_e_oeste(celulas: pd.DataFrame) -> np.ndarray:
    return ~((celulas["lat_c"] > 27.0) & (celulas["lon_c"] > -82.0)).to_numpy()


def regioes(teatro: Teatro) -> dict[str, np.ndarray]:
    """Recortes aproximados (por coordenada do centro da célula) usados nas leituras."""
    lat, lon = teatro.celulas["lat_c"].to_numpy(), teatro.celulas["lon_c"].to_numpy()
    if teatro.chave == "atlantico":
        brasil = (lat < 4.6) & (lon > -52.0) & (lat > -34.0)
        return {
            "Costa brasileira": brasil,
            "Brasil ao sul de 13°S": brasil & (lat < -13.0),
            "Guianas (Guiana, Suriname, Guiana Francesa)": (lat < 8.6) & (lat >= 4.0) & (lon > -60.5) & (lon <= -52.0),
            "EUA ao norte do Cabo Hatteras": (lat > 35.3) & (lon > -78.0),
        }
    return {
        "Mediterrâneo ocidental (a oeste de 12°L)": lon < 12.0,
        "Adriático": (lat > 40.0) & (lon > 12.0) & (lon < 20.0),
        "Mediterrâneo oriental (a leste de 22°L)": lon > 22.0,
    }


def montar_teatro(base: dict, chave: str) -> Teatro:
    celulas = base["celulas"][base["celulas"]["teatro"] == chave].reset_index(drop=True)
    nos = base["nos"][base["nos"]["teatro"] == chave]
    origem = ORIGENS[chave]
    lat = np.append(celulas["lat_c"].to_numpy(), origem["lat"])
    lon = np.append(celulas["lon_c"].to_numpy(), origem["lon"])
    matriz = distancias_pelo_mar(nos["lat"].to_numpy(), nos["lon"].to_numpy(), lat, lon)

    anos = np.arange(1990, ANO_FINAL + 1)
    tabela = base["esforco"].pivot_table(index="ano", columns="celula", values="registros_recifais", aggfunc="sum")
    tabela = tabela.reindex(index=np.arange(1950, ANO_FINAL + 1), columns=celulas["celula"]).fillna(0.0)
    movel = tabela.rolling(JANELA_ESFORCO, min_periods=1).mean().loc[anos].to_numpy()
    acumulado = np.log1p(tabela.cumsum().loc[anos].to_numpy())

    isolada = _isolada(celulas) if chave == "atlantico" else np.zeros(len(celulas), bool)
    ramo = _ramo_sul_e_oeste(celulas) if chave == "atlantico" else np.ones(len(celulas), bool)
    return Teatro(
        chave=chave,
        nome=TEATROS[chave]["nome"],
        celulas=celulas,
        distancias=matriz[:-1, :-1],
        distancia_origem=matriz[-1, :-1],
        primeiro=celulas["ano_primeiro_registro"].astype(float).to_numpy(),
        anos_esforco=anos,
        esforco=movel,
        habitat=acumulado,
        tmin=celulas["tmin_c"].to_numpy(float),
        isolada=isolada,
        ramo=ramo,
    )


# ---------------------------------------------------------------- 1. reconstrução da frente


def area_e_frente(t: Teatro) -> pd.DataFrame:
    """Por ano: células com registro (acumulado) e distância da frente ao ponto de introdução.

    A frente é a maior distância pelo mar entre as células já registradas do ramo medido.
    """
    anos = np.arange(ORIGENS[t.chave]["ano"], ANO_FINAL + 1)
    linhas = []
    for ano in anos:
        tem = t.primeiro <= ano
        frente_km = t.distancia_origem[tem & t.na_frente].max() if (tem & t.na_frente).any() else np.nan
        linhas.append({"ano": int(ano), "celulas_com_registro": int(tem.sum()), "frente_km": float(frente_km)})
    saida = pd.DataFrame(linhas)
    saida["novas_celulas"] = saida["celulas_com_registro"].diff().fillna(saida["celulas_com_registro"]).astype(int)
    return saida


def resumo_do_teatro(t: Teatro) -> dict:
    tem = np.isfinite(t.primeiro)
    bruto = t.celulas["ano_bruto"].notna().to_numpy()
    curva = area_e_frente(t)
    pico = curva.loc[curva["novas_celulas"].idxmax()]
    return {
        "celulas_de_plataforma": int(len(t.primeiro)),
        "celulas_com_registro": int(tem.sum()),
        "fracao_com_registro": float(tem.mean()),
        "celulas_so_com_registro_nao_corroborado": int((bruto & ~tem).sum()),
        "celulas_com_ano_alterado_pela_corroboracao": int((tem & (t.celulas["ano_bruto"].astype(float).to_numpy() < t.primeiro)).sum()),
        "primeiro_ano": int(np.nanmin(t.primeiro)),
        "ano_de_inicio_da_expansao": t.inicio,
        "celulas_semente": int((t.primeiro <= t.inicio).sum()),
        "ano_de_pico": int(pico["ano"]),
        "novas_celulas_no_pico": int(pico["novas_celulas"]),
        "novas_celulas_nos_ultimos_5_anos": int(((t.primeiro > ANO_FINAL - 5) & tem).sum()),
        "frente_km_no_ano_final": float(t.distancia_origem[tem & t.na_frente].max()),
        "celula_mais_distante": str(t.celulas["celula"].to_numpy()[np.argmax(np.where(tem & t.na_frente, t.distancia_origem, -1))]),
    }


def fontes_do_primeiro_registro(t: Teatro) -> dict:
    """De que fonte vem o ano do primeiro registro de cada célula."""
    c = t.celulas[t.celulas["ano_primeiro_registro"].notna()]
    fontes = {"NAS": "ano_nas", "GBIF": "ano_gbif", "OBIS": "ano_obis"}
    saida = {"celulas": int(len(c))}
    for nome, coluna in fontes.items():
        tem = c[coluna].notna()
        outras = [v for v in fontes.values() if v != coluna]
        saida[nome] = {
            "celulas_com_registro": int(tem.sum()),
            "celulas_em_que_tem_o_primeiro_ano": int((c[coluna] == c["ano_primeiro_registro"]).sum()),
            "celulas_so_nesta_fonte": int((tem & c[outras].isna().all(axis=1)).sum()),
        }
    return saida


# ---------------------------------------------------------------- 2. velocidade da frente


def dados_da_frente(t: Teatro, ate: int = ANO_FINAL) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Distância, ano e esforço das células registradas depois do início da expansão e até `ate`."""
    usa = (t.primeiro > t.inicio) & (t.primeiro <= ate) & t.na_frente
    esforco = np.array([t.esforco_no_ano(int(a))[k] for k, a in zip(np.flatnonzero(usa), t.primeiro[usa])])
    return t.distancia_origem[usa], t.primeiro[usa], esforco


def velocidades(t: Teatro, ate: int = ANO_FINAL, repeticoes: int = 300) -> pd.DataFrame:
    """Cada estimador de velocidade nos dados reais, com intervalo de 95% por bootstrap de células."""
    distancia, ano, esforco = dados_da_frente(t, ate)
    linhas = []
    for nome, funcao in frente.ESTIMADORES.items():
        inferior, superior = frente.bootstrap(distancia, ano, esforco, funcao, repeticoes=repeticoes)
        linhas.append(
            {"estimador": nome, "km_por_ano": funcao(distancia, ano, esforco), "inferior": inferior, "superior": superior, "celulas": int(len(ano))}
        )
    return pd.DataFrame(linhas).set_index("estimador")


def esforco_e_atraso(t: Teatro) -> dict:
    """O esforço de observação cai com a distância? E as células menos observadas têm registro mais tarde?

    A segunda conta compara o ano do primeiro registro com o esperado pela distância (resíduo da
    regressão de quantil 0,10 do ano): resíduo maior em célula menos observada é o viés de detecção.
    """
    distancia, ano, esforco = dados_da_frente(t)
    X = np.column_stack([np.ones(len(ano)), distancia])
    residuo = ano - X @ frente.regressao_quantilica(X, ano, 0.10)
    r_dist = spearmanr(distancia, esforco)
    r_atraso = spearmanr(esforco, residuo)
    pouco = esforco <= np.median(esforco)
    return {
        "celulas": int(len(ano)),
        "correlacao_esforco_distancia": float(r_dist.statistic),
        "p_esforco_distancia": float(r_dist.pvalue),
        "correlacao_esforco_atraso": float(r_atraso.statistic),
        "p_esforco_atraso": float(r_atraso.pvalue),
        "atraso_mediano_pouco_esforco_anos": float(np.median(residuo[pouco])),
        "atraso_mediano_muito_esforco_anos": float(np.median(residuo[~pouco])),
        "esforco_mediano": float(np.median(esforco)),
    }


# ---------------------------------------------------------------- 3 e 4. modelo e validação no tempo


def painel(t: Teatro, corte: int) -> esp.Painel:
    """Painel de ajuste: anos do início da expansão até o corte; registro depois do corte vira 'sem registro'.

    O esforço e o habitat usam só o que estava registrado até o corte.
    """
    anos = np.arange(t.inicio + 1, corte + 1)
    primeiro = np.where(t.primeiro <= corte, t.primeiro, np.nan)
    esforco = np.stack([t.esforco_no_ano(int(a)) for a in anos])
    return esp.Painel(
        anos=anos, distancias=t.distancias, primeiro=primeiro, esforco=esforco, habitat=t.habitat_no_ano(corte), tmin=t.tmin, fonte=~t.isolada
    )


def _parametros(ajuste: dict, dados_painel: esp.Painel) -> dict:
    theta, forma = ajuste["theta"], ajuste["forma"]
    erro = np.sqrt(np.clip(np.diag(ajuste["covariancia"]), 0, None))
    saida = {
        "alcance_km": float(np.exp(theta[1])),
        "alcance_km_ic": [float(np.exp(theta[1] - 1.96 * erro[1])), float(np.exp(theta[1] + 1.96 * erro[1]))],
        "elasticidade_esforco": float(theta[2]),
        "elasticidade_esforco_ic": [float(theta[2] - 1.96 * erro[2]), float(theta[2] + 1.96 * erro[2])],
        "contagio": float(np.exp(theta[0])),
        "fundo": float(np.exp(theta[3])),
        "log_verossimilhanca": ajuste["log_verossimilhanca"],
        "aic": ajuste["aic"],
        "parametros": int(len(theta)),
        "eventos": ajuste["eventos"],
        "celulas_ano_em_risco": ajuste["celulas_ano_em_risco"],
    }
    if forma.suscetivel:
        saida["suscetivel_constante"] = float(theta[4])
        saida["suscetivel_inclinacao_do_habitat"] = float(theta[5])
        saida["suscetivel_inclinacao_do_habitat_ic"] = [float(theta[5] - 1.96 * erro[5]), float(theta[5] + 1.96 * erro[5])]
    if forma.termico:
        k = forma.parametros - 1
        saida["limite_termico_c"] = float(theta[k])
        saida["limite_termico_c_ic"] = [float(theta[k] - 1.96 * erro[k]), float(theta[k] + 1.96 * erro[k])]
    if forma.suscetivel or forma.termico:
        sem = ~np.isfinite(dados_painel.primeiro)
        atualizada = esp.suscetibilidade_atualizada(theta, dados_painel, forma)
        saida["celulas_sem_registro"] = int(sem.sum())
        saida["suscetiveis_esperadas_entre_as_sem_registro"] = float(atualizada[sem].sum())
    return saida


def simular_com_incerteza(
    t: Teatro, ajuste: dict, dados_painel: esp.Painel, corte: int, ate: int, sorteios: int, por_sorteio: int, semente: int
) -> tuple[np.ndarray, np.ndarray]:
    """Simula de `corte + 1` até `ate`, sorteando também os parâmetros.

    Devolve o ano do primeiro registro, [simulação, célula], e o índice do sorteio de cada simulação.
    O esforço fica congelado no valor do ano de corte. Em cada sorteio, a probabilidade de cada
    célula ser suscetível é atualizada pela história até o corte.
    """
    gerador = np.random.default_rng(semente)
    thetas = esp.sortear_parametros(ajuste, sorteios, gerador)
    com_registro = t.primeiro <= corte
    esforco = t.esforco_no_ano(corte)
    anos = np.arange(corte + 1, ate + 1)
    partes = []
    for theta in thetas:
        suscetivel = esp.suscetibilidade_atualizada(theta, dados_painel, ajuste["forma"])
        partes.append(esp.simular(theta, t.distancias, com_registro, esforco, anos, por_sorteio, gerador, suscetivel=suscetivel, fonte=~t.isolada))
    return np.concatenate(partes), np.repeat(np.arange(sorteios), por_sorteio)


def _curvas(t: Teatro, corte: int, simulados: dict[str, np.ndarray], previsto_cv: np.ndarray, previsto_viz: np.ndarray) -> list[dict]:
    """Por ano depois do corte: células com registro e distância da frente, observadas e previstas."""
    com_registro = t.primeiro <= corte
    linhas = []
    for ano in range(corte, ANO_FINAL + 1):
        obs = t.primeiro <= ano
        cv = com_registro | (previsto_cv <= ano)
        viz = com_registro | (previsto_viz <= ano)
        linha = {
            "ano": ano,
            "observado_celulas": int(obs.sum()),
            "velocidade_constante_celulas": int(cv.sum()),
            "vizinha_celulas": int(viz.sum()),
            "observado_frente_km": float(t.distancia_origem[obs & t.na_frente].max()),
            "velocidade_constante_frente_km": float(t.distancia_origem[cv & t.na_frente].max()),
        }
        for nome, simulado in simulados.items():
            sim_tem = com_registro[None, :] | (simulado <= ano)
            contagem = sim_tem.sum(axis=1)
            linha[f"{nome}_celulas"] = float(np.median(contagem))
            linha[f"{nome}_celulas_p05"] = float(np.percentile(contagem, 5))
            linha[f"{nome}_celulas_p95"] = float(np.percentile(contagem, 95))
            if nome == "modelo":
                frente_sim = np.where(sim_tem & t.na_frente[None, :], t.distancia_origem[None, :], 0.0).max(axis=1)
                linha["modelo_frente_km"] = float(np.median(frente_sim))
                linha["modelo_frente_km_p05"] = float(np.percentile(frente_sim, 5))
                linha["modelo_frente_km_p95"] = float(np.percentile(frente_sim, 95))
        linhas.append(linha)
    return linhas


def _metricas(aconteceu: np.ndarray, probabilidade: np.ndarray, nota: np.ndarray) -> dict:
    inferior, superior = esp.bootstrap_metrica(esp.auc, aconteceu, nota, repeticoes=400)
    return {
        "auc": esp.auc(aconteceu, nota),
        "auc_ic": [inferior, superior],
        "brier": esp.brier(aconteceu, probabilidade),
        "previstas": float(np.sum(probabilidade)),
    }


def _ano_previsto(simulado: np.ndarray, teto: int) -> np.ndarray:
    """Ano previsto para cada célula: a mediana do ano de chegada nas simulações em que ela chega.

    Célula que chega em menos de 5% das simulações é dada como 'não chega no período' (`teto`).
    """
    chega = np.isfinite(simulado)
    ordenado = np.sort(np.where(chega, simulado, np.inf), axis=0)
    quantas = chega.sum(axis=0)
    meio = np.clip((quantas - 1) // 2, 0, None)
    mediana = ordenado[meio, np.arange(simulado.shape[1])]
    return np.where(quantas >= 0.05 * simulado.shape[0], mediana, teto)


def validar(t: Teatro, corte: int, sorteios: int = 30, por_sorteio: int = 40, semente: int = 0) -> dict:
    """Ajusta só com o que se sabia até `corte`, prevê os anos seguintes e compara com o que aconteceu."""
    dados_painel = painel(t, corte)
    ajustes = {nome: esp.ajustar(dados_painel, forma) for nome, forma in FORMAS.items()}
    # o modelo completo roda com mais simulações; as variantes, com menos (só entram na tabela de comparação)
    simulados = {
        nome: simular_com_incerteza(
            t, ajuste, dados_painel, corte, ANO_FINAL, sorteios if nome == "modelo" else 20, por_sorteio if nome == "modelo" else 25, semente + k
        )[0]
        for k, (nome, ajuste) in enumerate(ajustes.items())
    }
    simulado = simulados["modelo"]

    com_registro = t.primeiro <= corte
    alvo = ~com_registro
    distancia, ano, _ = dados_da_frente(t, ate=corte)
    velocidade = frente.velocidade_media(distancia, ano)
    na_frente = com_registro & t.na_frente
    previsto_cv = esp.base_velocidade_constante(t.distancia_origem, na_frente, velocidade, corte)
    previsto_viz = esp.base_vizinha(t.distancias, na_frente, corte)

    saida = {
        "corte": corte,
        "celulas_com_registro_no_corte": int(com_registro.sum()),
        "celulas_alvo": int(alvo.sum()),
        "parametros": {nome: _parametros(ajuste, dados_painel) for nome, ajuste in ajustes.items()},
        "velocidade_media_historica_km_ano": float(velocidade),
        "horizontes": {},
    }
    for horizonte in HORIZONTES:
        limite = corte + horizonte
        if limite > ANO_FINAL:
            continue
        aconteceu = (t.primeiro[alvo] > corte) & (t.primeiro[alvo] <= limite)
        p_cv = (previsto_cv[alvo] <= limite).astype(float)
        p_viz = (previsto_viz[alvo] <= limite).astype(float)
        linha = {"ate": limite, "celulas_alvo": int(alvo.sum()), "colonizadas": int(aconteceu.sum())}
        for nome, sim in simulados.items():
            with np.errstate(invalid="ignore"):
                p = (sim[:, alvo] <= limite).mean(axis=0)
            linha[nome] = {**_metricas(aconteceu, p, p), "calibracao": esp.calibracao(aconteceu, p)}
        linha["velocidade_constante"] = _metricas(aconteceu, p_cv, -previsto_cv[alvo])
        linha["vizinha"] = _metricas(aconteceu, p_viz, -previsto_viz[alvo])
        saida["horizontes"][str(horizonte)] = linha

    # erro no ano de chegada, nas células que tiveram o primeiro registro depois do corte
    chegou = alvo & (t.primeiro > corte)
    teto = ANO_FINAL + 1
    saida["erro_no_ano"] = {"celulas": int(chegou.sum())}
    previstos = {nome: _ano_previsto(sim, teto) for nome, sim in simulados.items()}
    previstos["velocidade_constante"] = np.minimum(previsto_cv, teto)
    previstos["vizinha"] = np.minimum(previsto_viz, teto)
    for nome, previsto in previstos.items():
        saida["erro_no_ano"][nome] = {
            "erro_absoluto_medio": float(np.mean(np.abs(previsto[chegou] - t.primeiro[chegou]))),
            "vies": float(np.mean(previsto[chegou] - t.primeiro[chegou])),
        }
    saida["curvas"] = _curvas(t, corte, simulados, previsto_cv, previsto_viz)

    saida["regioes"] = {}
    for nome, mascara in regioes(t).items():
        na_regiao = mascara & alvo & ~t.isolada
        if not na_regiao.any():
            continue
        primeiro_sim = np.nanmin(np.where(np.isnan(simulado[:, na_regiao]), np.inf, simulado[:, na_regiao]), axis=1)
        observado = t.primeiro[na_regiao]
        chegou_na_regiao = bool(np.isfinite(observado).any())
        quantis = np.percentile(primeiro_sim, [5, 50, 95], method="lower")  # sem interpolar: há infinitos ("não chegou")
        linha = {
            "celulas_alvo": int(na_regiao.sum()),
            "celulas_com_registro_ate_o_ano_final": int(np.isfinite(observado).sum()),
            "ano_observado_do_primeiro_registro": int(np.nanmin(observado)) if chegou_na_regiao else None,
            "probabilidade_de_algum_registro_ate_o_ano_final": float(np.isfinite(primeiro_sim).mean()),
            "ano_previsto_p05": float(quantis[0]) if np.isfinite(quantis[0]) else None,
            "ano_mediano_previsto": float(quantis[1]) if np.isfinite(quantis[1]) else None,
            "ano_previsto_p95": float(quantis[2]) if np.isfinite(quantis[2]) else None,
            "celulas_previstas_ate_o_ano_final": float(np.isfinite(simulado[:, na_regiao]).sum(axis=1).mean()),
            "ano_velocidade_constante": float(previsto_cv[na_regiao].min()),
            "ano_vizinha": float(previsto_viz[na_regiao].min()),
        }
        if chegou_na_regiao:
            linha["probabilidade_ate_o_ano_observado"] = float((primeiro_sim <= np.nanmin(observado)).mean())
        saida["regioes"][nome] = linha
    return saida


def escolha_da_forma(validacoes: dict[str, dict], chave: str) -> dict:
    """Aplica a regra: a temperatura entra na previsão do teatro se reduzir o Brier em todos os cortes e horizontes."""
    comparacoes = []
    for nome, v in validacoes.items():
        if not nome.startswith(chave):
            continue
        for horizonte, h in v["horizontes"].items():
            comparacoes.append(
                {
                    "corte": v["corte"],
                    "horizonte": int(horizonte),
                    "brier_sem_temperatura": h["modelo_sem_temperatura"]["brier"],
                    "brier_com_temperatura": h["modelo"]["brier"],
                }
            )
    usa = bool(comparacoes) and all(c["brier_com_temperatura"] < c["brier_sem_temperatura"] for c in comparacoes)
    return {"usa_temperatura": usa, "comparacoes": comparacoes}


# ---------------------------------------------------------------- 6. previsão


def prever(t: Teatro, usa_temperatura: bool, sorteios: int = 50, por_sorteio: int = 50, semente: int = 7) -> tuple[pd.DataFrame, dict]:
    """Ajusta com tudo até o último ano completo e simula os dez anos seguintes.

    Para cada célula ainda sem registro: probabilidade de primeiro registro em 5 e em 10 anos. A
    faixa de 90% vem da incerteza dos parâmetros (a probabilidade recalculada em cada sorteio).
    """
    forma = esp.Forma(suscetivel=True, termico=usa_temperatura)
    dados_painel = painel(t, ANO_FINAL)
    ajuste = esp.ajustar(dados_painel, forma)
    ate = ANO_FINAL + HORIZONTE_PREVISAO
    simulado, sorteio = simular_com_incerteza(t, ajuste, dados_painel, ANO_FINAL, ate, sorteios, por_sorteio, semente)
    tabela = t.celulas[["celula", "teatro", "lat_sul", "lon_oeste", "lat_c", "lon_c", "tmin_c", "ano_bruto"]].copy()
    tabela["distancia_origem_km"] = t.distancia_origem.round(0)
    tabela["ocupada"] = np.isfinite(t.primeiro)
    tabela["ano_primeiro_registro"] = t.celulas["ano_primeiro_registro"]
    sem_registro = ~np.isfinite(t.primeiro)
    tabela["prob_suscetivel"] = np.where(sem_registro, esp.suscetibilidade_atualizada(ajuste["theta"], dados_painel, forma), np.nan).round(3)
    with np.errstate(invalid="ignore"):
        for horizonte in (5, 10):
            chegou = simulado <= ANO_FINAL + horizonte
            por_sorteio_p = np.stack([chegou[sorteio == k].mean(axis=0) for k in range(sorteios)])
            tabela[f"prob_{horizonte}_anos"] = np.where(sem_registro, chegou.mean(axis=0), np.nan).round(3)
            tabela[f"prob_{horizonte}_anos_inf"] = np.where(sem_registro, np.percentile(por_sorteio_p, 5, axis=0), np.nan).round(3)
            tabela[f"prob_{horizonte}_anos_sup"] = np.where(sem_registro, np.percentile(por_sorteio_p, 95, axis=0), np.nan).round(3)
    tabela["limite_termico"] = np.select(
        [t.tmin < TEMPERATURA_LETAL, t.tmin < TEMPERATURA_SEM_ALIMENTACAO],
        ["abaixo da letal (10 °C)", "abaixo de 16,1 °C (para de se alimentar)"],
        default="acima de 16,1 °C",
    )
    tabela["regiao"] = ""
    for nome, mascara in regioes(t).items():  # a primeira região que contém a célula
        tabela.loc[mascara & (tabela["regiao"] == "").to_numpy(), "regiao"] = nome

    contagem = (np.isfinite(simulado) & sem_registro[None, :]).sum(axis=1)
    alcancada = (np.isfinite(simulado) | ~sem_registro[None, :]) & t.na_frente[None, :]
    frente_sim = np.where(alcancada, t.distancia_origem[None, :], 0.0).max(axis=1)
    resumo = {
        "forma": {"fracao_suscetivel": True, "temperatura": usa_temperatura},
        "parametros": _parametros(ajuste, dados_painel),
        "celulas_sem_registro": int(sem_registro.sum()),
        "novas_celulas_em_10_anos": {"mediana": float(np.median(contagem)), "p05": float(np.percentile(contagem, 5)), "p95": float(np.percentile(contagem, 95))},
        "frente_km_em_10_anos": {"mediana": float(np.median(frente_sim)), "p05": float(np.percentile(frente_sim, 5)), "p95": float(np.percentile(frente_sim, 95))},
        "celulas_com_prob_10_anos_acima_de_50": int((tabela["prob_10_anos"] >= 0.5).sum()),
        "celulas_com_prob_10_anos_acima_de_20": int((tabela["prob_10_anos"] >= 0.2).sum()),
        "regioes": {},
    }
    for nome, mascara in regioes(t).items():
        alvo = mascara & sem_registro
        if not alvo.any():
            resumo["regioes"][nome] = {"celulas": int(mascara.sum()), "celulas_sem_registro": 0}
            continue
        with np.errstate(invalid="ignore"):
            algum = {h: (simulado[:, alvo] <= ANO_FINAL + h).any(axis=1) for h in (5, 10)}
        por_sorteio_10 = np.array([algum[10][sorteio == k].mean() for k in range(sorteios)])
        resumo["regioes"][nome] = {
            "celulas": int(mascara.sum()),
            "celulas_sem_registro": int(alvo.sum()),
            "prob_de_algum_registro_novo_em_5_anos": float(algum[5].mean()),
            "prob_de_algum_registro_novo_em_10_anos": float(algum[10].mean()),
            "prob_10_anos_faixa": [float(np.percentile(por_sorteio_10, 5)), float(np.percentile(por_sorteio_10, 95))],
            "novas_celulas_esperadas_em_5_anos": float(tabela.loc[alvo, "prob_5_anos"].sum()),
            "novas_celulas_esperadas_em_10_anos": float(tabela.loc[alvo, "prob_10_anos"].sum()),
            "maior_prob_10_anos": float(tabela.loc[alvo, "prob_10_anos"].max()),
            "celulas_abaixo_de_16_1": int((t.tmin[alvo] < TEMPERATURA_SEM_ALIMENTACAO).sum()),
        }
    return tabela, resumo


def limite_termico(teatros: list[Teatro]) -> dict:
    """Temperatura do mês mais frio nas células com e sem registro, ao lado dos limites de laboratório."""
    saida = {"letal_c": TEMPERATURA_LETAL, "sem_alimentacao_c": TEMPERATURA_SEM_ALIMENTACAO}
    for t in teatros:
        tem = np.isfinite(t.primeiro)
        saida[t.chave] = {
            "com_registro": {
                "celulas": int(tem.sum()),
                "minima": float(t.tmin[tem].min()),
                "p05": float(np.percentile(t.tmin[tem], 5)),
                "mediana": float(np.median(t.tmin[tem])),
                "abaixo_de_16_1": int((t.tmin[tem] < TEMPERATURA_SEM_ALIMENTACAO).sum()),
                "abaixo_de_10": int((t.tmin[tem] < TEMPERATURA_LETAL).sum()),
            },
            "sem_registro": {
                "celulas": int((~tem).sum()),
                "abaixo_de_16_1": int((t.tmin[~tem] < TEMPERATURA_SEM_ALIMENTACAO).sum()),
                "abaixo_de_10": int((t.tmin[~tem] < TEMPERATURA_LETAL).sum()),
                "mediana": float(np.median(t.tmin[~tem])),
            },
        }
    return saida


# ---------------------------------------------------------------- cronologia: dados contra literatura

# (marco, teatro, lat sul, lat norte, lon oeste, lon leste, ano na literatura, fonte)
MARCOS = [
    ("Flórida, costa atlântica (Dania)", "atlantico", 25, 27, -81, -79, 1985, "Schofield 2009"),
    ("Bermudas", "atlantico", 31, 34, -66, -63, 2000, "Schofield 2009"),
    ("Bahamas", "atlantico", 21, 28, -79, -72, 2004, "Schofield 2009"),
    ("Mar do Caribe (Turks e Caicos, Cuba)", "atlantico", 9, 22.5, -88, -60, 2007, "Schofield 2009"),
    ("Golfo do México", "atlantico", 18, 31, -98, -83, 2009, "Schofield 2010"),
    ("Venezuela", "atlantico", 9.5, 13, -72, -61, 2009, "Schofield 2010"),
    ("Brasil, registro isolado (Arraial do Cabo)", "atlantico", -25, -20, -44, -40, 2014, "Ferreira et al. 2015"),
    ("Brasil, costa norte e Fernando de Noronha", "atlantico", -6, 4.6, -52, -32, 2020, "Luiz et al. 2021"),
    ("Brasil, Ceará e Piauí", "atlantico", -5, -2, -42, -37, 2022, "Soares et al. 2022"),
    ("Israel (primeiro do Mediterrâneo)", "mediterraneo", 31, 33.4, 34, 36, 1991, "Golani e Sonin 1992"),
    ("Líbano", "mediterraneo", 33, 35, 35, 36.5, 2012, "Bariche et al. 2013"),
    ("Itália (Sicília)", "mediterraneo", 36, 39, 12, 16, 2016, "Azzurro et al. 2017"),
    ("Croácia (Adriático)", "mediterraneo", 42, 46, 13, 18.5, 2021, "Dragičević et al. 2021"),
]


def cronologia(teatros: dict[str, Teatro]) -> pd.DataFrame:
    """Ano do primeiro registro nos dados públicos, em caixas aproximadas, contra o ano publicado.

    Duas colunas dos dados: o primeiro registro de qualquer tipo (bruto) e o primeiro corroborado.
    """
    linhas = []
    for marco, chave, sul, norte, oeste, leste, ano, fonte in MARCOS:
        t = teatros[chave]
        lat, lon = t.celulas["lat_c"].to_numpy(), t.celulas["lon_c"].to_numpy()
        dentro = (lat >= sul) & (lat < norte) & (lon >= oeste) & (lon < leste)
        bruto = t.celulas["ano_bruto"].astype(float).to_numpy()[dentro]
        corroborado = t.primeiro[dentro]
        linhas.append(
            {
                "marco": marco,
                "ano_na_literatura": ano,
                "fonte": fonte,
                "ano_bruto_nos_dados": int(np.nanmin(bruto)) if np.isfinite(bruto).any() else None,
                "ano_corroborado_nos_dados": int(np.nanmin(corroborado)) if np.isfinite(corroborado).any() else None,
            }
        )
    return pd.DataFrame(linhas)


def registros_que_contradizem(base: dict) -> dict:
    """Quantas células têm registro público mais antigo que o primeiro corroborado, e quantas só têm registro isolado."""
    c = base["celulas"]
    saida = {}
    for chave in TEATROS:
        parte = c[c["teatro"] == chave]
        bruto, bom = parte["ano_bruto"].astype(float), parte["ano_primeiro_registro"].astype(float)
        antecipadas = parte[(bruto < bom) | (bruto.notna() & bom.isna())]
        saida[chave] = {
            "celulas_com_registro_bruto": int(bruto.notna().sum()),
            "celulas_com_registro_corroborado": int(bom.notna().sum()),
            "celulas_em_que_o_bruto_e_mais_antigo": int((bruto < bom).sum()),
            "celulas_so_com_registro_isolado": int((bruto.notna() & bom.isna()).sum()),
            "ano_minimo_para_datar": ANO_MINIMO_PARA_DATAR[chave],
            "celulas_com_registro_bruto_antes_do_ano_minimo": int((bruto < ANO_MINIMO_PARA_DATAR[chave]).sum()),
            "mais_antigos": [
                {"celula": linha.celula, "ano_bruto": int(linha.ano_bruto), "ano_corroborado": None if pd.isna(linha.ano_primeiro_registro) else int(linha.ano_primeiro_registro)}
                for linha in antecipadas.sort_values("ano_bruto").head(8).itertuples()
            ],
        }
    return saida
