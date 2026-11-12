"""Modelo de espalhamento entre células, as linhas de base e as métricas de validação.

O que o modelo descreve é o **primeiro registro**, não a chegada: é isso que existe para conferir.
A cada ano, a célula suscetível e ainda sem registro passa a ter um com probabilidade
1 - exp(-risco), e

    risco = (fundo + contagio * pressão) * (1 + esforço) ** elasticidade
    pressão = soma, nas células já com registro, de exp(-distância pelo mar / alcance)

- `pressão`: quanto mais células ocupadas por perto, maior a chance de a célula ser a próxima;
- `fundo`: saltos longos e novas introduções, que nenhuma vizinhança explica;
- `esforço`: registros de outros peixes recifais na célula naquele ano, porque sem observador não
  há registro.

Nem toda célula de plataforma pode vir a ter registro: há fundo de lama sem recife, água fria e
costa em que ninguém mergulha. Por isso o modelo completo tem uma **fração suscetível** (o mesmo
desenho dos modelos de "cura" da análise de sobrevivência): cada célula é suscetível com
probabilidade

    suscetível = logística(a + b * habitat) * aptidão térmica

em que `habitat` é o log dos registros de peixes recifais acumulados na célula e a aptidão
térmica (opcional) é uma logística da temperatura do mês mais frio. Uma célula que passa anos
cercada de vizinhas ocupadas sem ter registro vai ficando, para o modelo, provavelmente não
suscetível. Sem esse termo, toda célula acaba colonizada.

Os parâmetros saem por máxima verossimilhança; a incerteza, da matriz hessiana no ótimo.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import rankdata

NOMES = ["log_contagio", "log_alcance_km", "elasticidade_esforco", "log_fundo"]
LIMITES = [(-16.0, 4.0), (np.log(20.0), np.log(4000.0)), (-0.5, 2.0), (-20.0, -2.0)]
LIMITES_SUSCETIVEL = [(-8.0, 8.0), (-3.0, 3.0)]
LIMITE_TERMICO = (4.0, 26.0)
LARGURA_TERMICA_C = 1.0  # largura fixa da transição da aptidão térmica, em graus


@dataclass(frozen=True)
class Forma:
    """Quais termos opcionais o modelo tem. A ordem dos parâmetros é: os 4 do risco, (a, b), limite térmico."""

    suscetivel: bool = True
    termico: bool = False

    @property
    def parametros(self) -> int:
        return 4 + 2 * self.suscetivel + self.termico

    def limites(self) -> list[tuple[float, float]]:
        return LIMITES + (LIMITES_SUSCETIVEL if self.suscetivel else []) + ([LIMITE_TERMICO] if self.termico else [])

    def partidas(self) -> list[list[float]]:
        resto = ([1.0, 0.3] if self.suscetivel else []) + ([14.0] if self.termico else [])
        return [[-6.0, np.log(300.0), 0.3, -9.0] + resto, [-4.0, np.log(100.0), 0.1, -7.0] + resto]


@dataclass
class Painel:
    """O que o modelo precisa de um teatro: uma linha por ano em risco, uma coluna por célula."""

    anos: np.ndarray  # anos em que as células estão em risco de primeiro registro
    distancias: np.ndarray  # matriz célula x célula, km pelo mar
    primeiro: np.ndarray  # ano do primeiro registro por célula (nan = sem registro)
    esforco: np.ndarray  # [ano, célula]: registros de peixes recifais (média dos três anos até o ano)
    habitat: np.ndarray | None = None  # por célula: log(1 + registros recifais acumulados)
    tmin: np.ndarray | None = None  # temperatura do mês mais frio por célula
    fonte: np.ndarray | None = None  # células que contam como fonte de pressão (padrão: todas)

    def ocupada(self) -> np.ndarray:
        """[ano, célula]: a célula já tinha registro antes do ano (e conta como fonte)."""
        antes = self.primeiro[None, :] < self.anos[:, None]
        return antes if self.fonte is None else antes & self.fonte[None, :]

    def em_risco(self) -> np.ndarray:
        return ~(self.primeiro[None, :] < self.anos[:, None])

    def evento(self) -> np.ndarray:
        return self.primeiro[None, :] == self.anos[:, None]

    @cached_property
    def partes(self) -> dict:
        """O que não muda entre avaliações da verossimilhança, calculado uma vez.

        Só as células que chegam a ser fonte entram na conta da pressão, o que encolhe a matriz.
        """
        ocupada = self.ocupada()
        fontes = ocupada.any(axis=0)
        em_risco, evento = self.em_risco(), self.evento()
        return {
            "ocupada": ocupada[:, fontes].astype(float),
            "distancias": self.distancias[fontes],
            "sem_evento": (em_risco & ~evento).astype(float),
            "evento": evento.astype(float),
            "teve_evento": evento.any(axis=0),
            "so_em_risco": em_risco.any(axis=0) & ~evento.any(axis=0),
            "um_mais_esforco": 1.0 + self.esforco,
        }


def aptidao_termica(tmin: np.ndarray, limite: float) -> np.ndarray:
    return expit((np.asarray(tmin, float) - limite) / LARGURA_TERMICA_C)


def suscetibilidade(theta: np.ndarray, forma: Forma, habitat, tmin, celulas: int) -> np.ndarray:
    """Probabilidade, antes de olhar a história, de cada célula poder vir a ter registro."""
    valor = np.ones(celulas)
    if forma.suscetivel:
        valor = expit(theta[4] + theta[5] * np.asarray(habitat, float))
    if forma.termico:
        valor = valor * aptidao_termica(tmin, theta[forma.parametros - 1])
    return valor


def risco(theta: np.ndarray, distancias, ocupada, esforco) -> np.ndarray:
    """Risco anual de primeiro registro numa célula suscetível, [ano, célula]."""
    contagio, alcance, elasticidade, fundo = np.exp(theta[0]), np.exp(theta[1]), theta[2], np.exp(theta[3])
    pressao = np.asarray(ocupada, float) @ np.exp(-np.asarray(distancias) / alcance)
    return (fundo + contagio * pressao) * (1.0 + np.asarray(esforco)) ** elasticidade


def _risco_do_painel(theta: np.ndarray, painel: Painel) -> np.ndarray:
    p = painel.partes
    contagio, alcance, elasticidade, fundo = np.exp(theta[0]), np.exp(theta[1]), theta[2], np.exp(theta[3])
    pressao = p["ocupada"] @ np.exp(-p["distancias"] / alcance)
    return np.maximum((fundo + contagio * pressao) * p["um_mais_esforco"] ** elasticidade, 1e-300)


def log_verossimilhanca(theta: np.ndarray, painel: Painel, forma: Forma = Forma(suscetivel=False)) -> float:
    """Verossimilhança do painel.

    Para a célula com registro no ano y: suscetível, sobreviveu aos anos anteriores e foi
    registrada em y. Para a célula sem registro: ou não é suscetível, ou é e sobreviveu a todos os
    anos em risco.
    """
    p = painel.partes
    h = _risco_do_painel(theta, painel)
    acumulado = (h * p["sem_evento"]).sum(axis=0)  # risco somado nos anos em risco sem registro
    no_evento = (h * p["evento"]).sum(axis=0)
    pi = np.clip(suscetibilidade(theta, forma, painel.habitat, painel.tmin, h.shape[1]), 1e-12, 1.0)
    com = p["teve_evento"]
    sem = p["so_em_risco"]
    registradas = np.log(pi[com]) - acumulado[com] + np.log(-np.expm1(-no_evento[com]))
    sem_registro = np.log(np.maximum((1.0 - pi[sem]) + pi[sem] * np.exp(-acumulado[sem]), 1e-300))
    return float(registradas.sum() + sem_registro.sum())


def suscetibilidade_atualizada(theta: np.ndarray, painel: Painel, forma: Forma) -> np.ndarray:
    """Probabilidade de cada célula ser suscetível **depois** de ver a história do painel (regra de Bayes).

    Célula com registro: 1. Célula sem registro: pi * S / (1 - pi + pi * S), com S a chance de uma
    célula suscetível ter passado por aqueles anos sem registro.
    """
    p = painel.partes
    h = _risco_do_painel(theta, painel)
    sobrevivencia = np.exp(-(h * p["sem_evento"]).sum(axis=0))
    pi = suscetibilidade(theta, forma, painel.habitat, painel.tmin, h.shape[1])
    atualizada = pi * sobrevivencia / np.maximum(1.0 - pi + pi * sobrevivencia, 1e-300)
    return np.where(np.isfinite(painel.primeiro), 1.0, atualizada)


def hessiana_numerica(funcao, x: np.ndarray, passo: float = 1e-3) -> np.ndarray:
    """Hessiana por diferenças centrais."""
    n = len(x)
    H = np.zeros((n, n))
    for i in range(n):
        for j in range(i, n):
            ei, ej = np.eye(n)[i] * passo, np.eye(n)[j] * passo
            H[i, j] = H[j, i] = (funcao(x + ei + ej) - funcao(x + ei - ej) - funcao(x - ei + ej) + funcao(x - ei - ej)) / (4 * passo**2)
    return H


def ajustar(painel: Painel, forma: Forma = Forma(suscetivel=False)) -> dict:
    """Máxima verossimilhança por L-BFGS-B, de dois pontos de partida; covariância pela hessiana."""
    limites = forma.limites()
    melhor = None
    for partida in forma.partidas():
        resultado = minimize(lambda t: -log_verossimilhanca(t, painel, forma), np.array(partida), method="L-BFGS-B", bounds=limites)
        if melhor is None or resultado.fun < melhor.fun:
            melhor = resultado
    theta = melhor.x
    H = hessiana_numerica(lambda t: -log_verossimilhanca(t, painel, forma), theta)
    # parâmetro encostado no limite não tem curvatura confiável: fica fixo nos sorteios
    livre = np.array([lo + 1e-4 < v < hi - 1e-4 for v, (lo, hi) in zip(theta, limites)])
    covariancia = np.zeros_like(H)
    if livre.any():
        sub = H[np.ix_(livre, livre)]
        autovalores, autovetores = np.linalg.eigh((sub + sub.T) / 2)
        autovalores = np.maximum(autovalores, 1e-6 * max(autovalores.max(), 1e-6))
        covariancia[np.ix_(livre, livre)] = (autovetores / autovalores) @ autovetores.T
    return {
        "theta": theta,
        "forma": forma,
        "covariancia": covariancia,
        "log_verossimilhanca": float(-melhor.fun),
        "aic": float(2 * len(theta) + 2 * melhor.fun),
        "limites": limites,
        "eventos": int(painel.evento().sum()),
        "celulas_ano_em_risco": int(painel.em_risco().sum()),
    }


def sortear_parametros(ajuste: dict, quantos: int, gerador: np.random.Generator) -> np.ndarray:
    """Sorteios da aproximação normal em torno do ótimo, presos aos limites."""
    sorteios = gerador.multivariate_normal(ajuste["theta"], ajuste["covariancia"], size=quantos, method="eigh")
    for k, (lo, hi) in enumerate(ajuste["limites"]):
        sorteios[:, k] = np.clip(sorteios[:, k], lo, hi)
    return sorteios


def simular(
    theta: np.ndarray,
    distancias: np.ndarray,
    com_registro: np.ndarray,
    esforco: np.ndarray,
    anos: np.ndarray,
    simulacoes: int,
    gerador: np.random.Generator,
    suscetivel: np.ndarray | None = None,
    fonte: np.ndarray | None = None,
) -> np.ndarray:
    """Simula os anos seguintes. Devolve [simulação, célula] com o ano do primeiro registro (nan = não houve).

    `com_registro` marca as células que já têm registro na partida; `esforco` é o esforço por célula,
    mantido constante no futuro (o último valor conhecido no corte, para não vazar informação);
    `suscetivel` é a probabilidade de cada célula ser suscetível (padrão: todas são), sorteada uma
    vez por simulação.
    """
    contagio, alcance, elasticidade, fundo = np.exp(theta[0]), np.exp(theta[1]), theta[2], np.exp(theta[3])
    nucleo = np.exp(-distancias / alcance).astype(np.float32)
    fator = (1.0 + esforco) ** elasticidade
    registrada = np.tile(np.asarray(com_registro, bool), (simulacoes, 1))
    pode = np.ones(registrada.shape, bool) if suscetivel is None else gerador.random(registrada.shape) < np.asarray(suscetivel)[None, :]
    conta = np.ones(distancias.shape[0], bool) if fonte is None else np.asarray(fonte, bool)
    primeiro = np.full(registrada.shape, np.nan)
    pressao = (registrada & conta[None, :]).astype(np.float32) @ nucleo
    for ano in anos:
        p = -np.expm1(-(fundo + contagio * pressao) * fator[None, :])
        nova = ~registrada & pode & (gerador.random(registrada.shape) < p)
        primeiro[nova] = ano
        registrada |= nova
        # a pressão do ano seguinte só muda pelo que as células novas acrescentam
        qual_simulacao, qual_celula = np.nonzero(nova & conta[None, :])  # já vem ordenado por simulação
        if len(qual_simulacao):
            inicio = np.flatnonzero(np.diff(qual_simulacao, prepend=-1))
            pressao[qual_simulacao[inicio]] += np.add.reduceat(nucleo[qual_celula], inicio, axis=0)
    return primeiro


# ---------------------------------------------------------------- linhas de base


def base_velocidade_constante(distancia_origem, com_registro, velocidade: float, corte: int) -> np.ndarray:
    """'Avança X km por ano': ano previsto de chegada a cada célula ainda sem registro.

    A frente no corte é a maior distância já registrada; daí em diante anda `velocidade` km por
    ano. Célula atrás da frente é dada como alcançada no ano seguinte ao corte.
    """
    distancia_origem = np.asarray(distancia_origem, float)
    frente = distancia_origem[np.asarray(com_registro, bool)].max()
    return corte + np.maximum(1.0, np.ceil((distancia_origem - frente) / max(velocidade, 1e-9)))


def base_vizinha(distancias, com_registro, corte: int, passo_km: float = 160.0) -> np.ndarray:
    """'A vizinha da última ocupada é a próxima': uma célula por ano a partir da célula com registro mais próxima.

    160 km cobre a vizinha na diagonal de uma grade de 1 grau.
    """
    mais_proxima = np.asarray(distancias)[:, np.asarray(com_registro, bool)].min(axis=1)
    return corte + np.maximum(1.0, np.ceil(mais_proxima / passo_km))


# ---------------------------------------------------------------- métricas


def auc(aconteceu, nota) -> float:
    """Área sob a curva ROC pela estatística de Mann-Whitney (empates valem meio)."""
    aconteceu = np.asarray(aconteceu, bool)
    positivos, negativos = aconteceu.sum(), (~aconteceu).sum()
    if positivos == 0 or negativos == 0:
        return float("nan")
    postos = rankdata(nota)
    return float((postos[aconteceu].sum() - positivos * (positivos + 1) / 2) / (positivos * negativos))


def brier(aconteceu, probabilidade) -> float:
    return float(np.mean((np.asarray(probabilidade, float) - np.asarray(aconteceu, float)) ** 2))


def calibracao(aconteceu, probabilidade, cortes=(0.0, 0.1, 0.3, 0.6, 1.0)) -> list[dict]:
    """Por faixa de probabilidade prevista: quantas células, a média prevista e a fração que aconteceu."""
    aconteceu, probabilidade = np.asarray(aconteceu, float), np.asarray(probabilidade, float)
    linhas = []
    for k in range(len(cortes) - 1):
        ultimo = k == len(cortes) - 2
        dentro = (probabilidade >= cortes[k]) & ((probabilidade <= cortes[k + 1]) if ultimo else (probabilidade < cortes[k + 1]))
        if dentro.any():
            linhas.append(
                {
                    "faixa": f"{cortes[k]:.0%} a {cortes[k + 1]:.0%}",
                    "celulas": int(dentro.sum()),
                    "previsto": float(probabilidade[dentro].mean()),
                    "observado": float(aconteceu[dentro].mean()),
                }
            )
    return linhas


def bootstrap_metrica(metrica, aconteceu, nota, repeticoes: int = 1000, semente: int = 0) -> tuple[float, float]:
    """Intervalo de 95% de uma métrica por bootstrap de células."""
    gerador = np.random.default_rng(semente)
    aconteceu, nota = np.asarray(aconteceu), np.asarray(nota)
    n, valores = len(aconteceu), []
    for _ in range(repeticoes):
        k = gerador.integers(0, n, n)
        valor = metrica(aconteceu[k], nota[k])
        if np.isfinite(valor):
            valores.append(valor)
    return tuple(float(v) for v in np.percentile(valores, [2.5, 97.5]))
