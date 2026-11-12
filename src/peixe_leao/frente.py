"""Velocidade da frente de invasão: estimadores, bootstrap e uma invasão simulada para conferi-los.

O dado é um par por célula: distância pelo mar até o ponto de introdução (km) e ano do primeiro
registro. Dois problemas separam o primeiro registro da chegada:

- a frente é o registro mais distante de cada época, não a média: atrás dela as células vão sendo
  preenchidas por anos, e a média mistura as duas coisas;
- o primeiro registro vem depois da chegada, e o atraso é maior onde há menos gente olhando. O
  erro é sempre para o mesmo lado (mais tarde), o que favorece estimadores de envelope.

A regressão de quantis é resolvida aqui como o programa linear que a define.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog


def minimos_quadrados(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Coeficientes de mínimos quadrados; X já com a coluna de uns."""
    return np.linalg.lstsq(X, y, rcond=None)[0]


def regressao_quantilica(X: np.ndarray, y: np.ndarray, tau: float) -> np.ndarray:
    """Regressão de quantis escrita como o programa linear que a define.

    Minimiza a soma de tau * u+ + (1 - tau) * u-, com y = X b + u+ - u-, u+ e u- não negativos e b
    livre. Com tau = 0,5 e só a constante, a solução é a mediana.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, p = X.shape
    custo = np.concatenate([np.zeros(p), np.full(n, tau), np.full(n, 1 - tau)])
    igualdade = np.hstack([X, np.eye(n), -np.eye(n)])
    limites = [(None, None)] * p + [(0, None)] * (2 * n)
    solucao = linprog(custo, A_eq=igualdade, b_eq=y, bounds=limites, method="highs")
    if not solucao.success:
        raise RuntimeError(f"regressão de quantis não convergiu: {solucao.message}")
    return solucao.x[:p]


def _desenho(*colunas: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(colunas[0])), *colunas])


def velocidade_media(distancia, ano) -> float:
    """Distância contra ano, por mínimos quadrados: 'avança X km por ano em média'. É a linha de base."""
    return float(minimos_quadrados(_desenho(ano), np.asarray(distancia, float))[1])


def velocidade_media_inversa(distancia, ano) -> float:
    """Ano contra distância, por mínimos quadrados; a velocidade é o inverso da inclinação.

    O atraso de detecção é ruído no ano. Posto como resposta, ele não achata a inclinação.
    """
    return float(1.0 / minimos_quadrados(_desenho(distancia), np.asarray(ano, float))[1])


def velocidade_quantil_distancia(distancia, ano, tau: float = 0.90) -> float:
    """Quantil alto da distância em cada ano: a frente é quem foi mais longe."""
    return float(regressao_quantilica(_desenho(ano), np.asarray(distancia, float), tau)[1])


def velocidade_quantil_ano(distancia, ano, tau: float = 0.10) -> float:
    """Quantil baixo do ano em cada distância: a frente é o registro mais cedo naquela distância."""
    return float(1.0 / regressao_quantilica(_desenho(distancia), np.asarray(ano, float), tau)[1])


def envelope(distancia, ano) -> tuple[np.ndarray, np.ndarray]:
    """Maior distância registrada até cada ano (só os anos em que o recorde avança)."""
    distancia, ano = np.asarray(distancia, float), np.asarray(ano, float)
    anos = np.unique(ano)
    maximo = np.array([distancia[ano <= a].max() for a in anos])
    avanca = np.concatenate([[True], np.diff(maximo) > 0])
    return anos[avanca], maximo[avanca]


def velocidade_envelope(distancia, ano) -> float:
    """Reta ajustada aos recordes de distância. Depende de poucos pontos e do registro mais extremo."""
    anos, maximo = envelope(distancia, ano)
    if len(anos) < 3:
        return float("nan")
    return float(minimos_quadrados(_desenho(anos), maximo)[1])


def velocidade_com_esforco(distancia, ano, esforco) -> float:
    """Ano contra distância e log do esforço de observação; velocidade = inverso do coeficiente da distância.

    Controla o caso em que as células distantes são também as menos observadas.
    """
    X = _desenho(np.asarray(distancia, float), np.log1p(np.asarray(esforco, float)))
    return float(1.0 / minimos_quadrados(X, np.asarray(ano, float))[1])


ESTIMADORES = {
    "Média: distância contra ano (linha de base)": lambda d, a, e: velocidade_media(d, a),
    "Média: ano contra distância": lambda d, a, e: velocidade_media_inversa(d, a),
    "Média: ano contra distância, com esforço": velocidade_com_esforco,
    "Frente: quantil 0,90 da distância": lambda d, a, e: velocidade_quantil_distancia(d, a),
    "Frente: quantil 0,10 do ano": lambda d, a, e: velocidade_quantil_ano(d, a),
    "Frente: envelope dos recordes": lambda d, a, e: velocidade_envelope(d, a),
}


def bootstrap(distancia, ano, esforco, estimador, repeticoes: int = 500, semente: int = 0) -> tuple[float, float]:
    """Intervalo de 95% por bootstrap de células (percentis)."""
    gerador = np.random.default_rng(semente)
    distancia, ano, esforco = (np.asarray(v, float) for v in (distancia, ano, esforco))
    n = len(distancia)
    valores = []
    for _ in range(repeticoes):
        k = gerador.integers(0, n, n)
        try:
            valores.append(estimador(distancia[k], ano[k], esforco[k]))
        except (RuntimeError, np.linalg.LinAlgError, ZeroDivisionError):
            continue
    valores = np.array(valores)
    valores = valores[np.isfinite(valores)]
    inferior, superior = np.percentile(valores, [2.5, 97.5])
    return float(inferior), float(superior)


def simular_invasao(
    velocidade: float,
    gerador: np.random.Generator,
    celulas: int = 250,
    distancia_maxima: float = 6000.0,
    anos: int = 25,
    preenchimento: float = 0.0,
    deteccao: float | None = None,
    gradiente: float = 0.0,
) -> dict:
    """Invasão de velocidade conhecida numa costa reta, com detecção imperfeita.

    - A frente parte da origem no ano 0 e anda `velocidade` km por ano. A célula à distância d é
      alcançada em d / velocidade, mais um tempo de preenchimento (exponencial, média `preenchimento`
      anos): a frente passa e as células atrás dela vão sendo ocupadas depois.
    - O esforço de observação de cada célula é log-normal; com `gradiente` > 0, cai com a distância
      (quanto mais longe da origem, menos gente olhando).
    - A cada ano depois da chegada, a célula ocupada é registrada com probabilidade
      1 - exp(-deteccao * esforço). `deteccao=None` é detecção perfeita.
    - A observação termina no ano `anos`: célula ainda não registrada fica sem dado.
    """
    distancia = gerador.uniform(0, distancia_maxima, celulas)
    chegada = distancia / velocidade
    if preenchimento > 0:
        chegada = chegada + gerador.exponential(preenchimento, celulas)
    esforco = gerador.lognormal(0.0, 1.0, celulas) * np.exp(-gradiente * distancia / distancia_maxima)
    ano_chegada = np.ceil(chegada)
    if deteccao is None:
        registro = ano_chegada
    else:
        p = 1 - np.exp(-deteccao * esforco)
        registro = ano_chegada + gerador.geometric(np.clip(p, 1e-9, 1.0)) - 1
    visto = registro <= anos
    return {"distancia": distancia[visto], "ano": registro[visto], "esforco": esforco[visto] * 100, "celulas_vistas": int(visto.sum())}


CENARIOS = {
    "Detecção perfeita, sem preenchimento": {},
    "Preenchimento atrás da frente": {"preenchimento": 3.0},
    "Preenchimento e detecção imperfeita": {"preenchimento": 3.0, "deteccao": 0.5},
    "Idem, com menos esforço longe da origem": {"preenchimento": 3.0, "deteccao": 0.5, "gradiente": 2.5},
}


def comparar_estimadores(velocidade: float = 250.0, repeticoes: int = 200, semente: int = 0) -> list[dict]:
    """Roda cada estimador em invasões simuladas de velocidade conhecida e mede o quanto cada um erra."""
    linhas = []
    for cenario, opcoes in CENARIOS.items():
        gerador = np.random.default_rng(semente)
        estimativas = {nome: [] for nome in ESTIMADORES}
        for _ in range(repeticoes):
            s = simular_invasao(velocidade, gerador, **opcoes)
            for nome, funcao in ESTIMADORES.items():
                try:
                    estimativas[nome].append(funcao(s["distancia"], s["ano"], s["esforco"]))
                except (RuntimeError, np.linalg.LinAlgError, ZeroDivisionError):
                    estimativas[nome].append(np.nan)
        for nome, valores in estimativas.items():
            v = np.array(valores)
            v = v[np.isfinite(v)]
            linhas.append(
                {
                    "cenario": cenario,
                    "estimador": nome,
                    "velocidade_real": velocidade,
                    "media": float(v.mean()),
                    "erro_relativo": float(v.mean() / velocidade - 1),
                    "p05": float(np.percentile(v, 5)),
                    "p95": float(np.percentile(v, 95)),
                    "reqm_relativo": float(np.sqrt(np.mean((v / velocidade - 1) ** 2))),
                }
            )
    return linhas
