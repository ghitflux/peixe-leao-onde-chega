"""Geografia do estudo: os dois teatros da invasão, a grade de células e a distância pelo mar.

Tudo aqui é NumPy/SciPy, sem cartopy nem geopandas. A terra, o mar e a plataforma continental vêm
do relevo ETOPO1 (NOAA) amostrado a cada 0,1 grau: ponto com altitude negativa é mar; entre 0 e
-300 m é plataforma, a faixa de profundidade onde o peixe-leão vive.
"""

from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

RAIO_TERRA_KM = 6371.0088
PROFUNDIDADE_MAXIMA_M = 300  # limite de profundidade do habitat considerado
PASSO_NOS = 0.5  # resolução, em graus, da malha usada para medir distância pelo mar

# Caixas de cada teatro (lon oeste, lon leste, lat sul, lat norte). O recorte fino é `teatro_do_ponto`.
TEATROS = {
    "atlantico": {"lon": (-98.0, -30.0), "lat": (-40.0, 45.0), "nome": "Atlântico oeste"},
    "mediterraneo": {"lon": (-6.0, 37.0), "lat": (30.0, 46.0), "nome": "Mediterrâneo"},
}

# Ponto de introdução de cada teatro (lat, lon) e o ano em que a expansão é contada.
# Atlântico: Dania, Flórida, outubro de 1985 (Schofield 2009). Mediterrâneo: a entrada é o Canal de
# Suez; o ponto usado é a costa do Levante, onde estão os registros de 1991 (Israel) e 2012 (Líbano).
ORIGENS = {
    "atlantico": {"lat": 26.05, "lon": -80.05, "ano": 1985, "nome": "Dania, Flórida"},
    "mediterraneo": {"lat": 33.0, "lon": 34.6, "ano": 1991, "nome": "costa do Levante"},
}

# Linha que separa o Pacífico do Caribe na América Central: (lon, lat). Ao sul dela é Pacífico.
_DIVISOR = np.array(
    [
        (-98.0, 17.5), (-94.5, 17.3), (-92.0, 16.0), (-89.5, 14.6), (-87.5, 14.0), (-85.5, 12.3), (-84.5, 10.6),
        (-83.3, 9.3), (-82.0, 8.8), (-80.5, 8.7), (-79.5, 9.2), (-78.5, 9.0), (-77.6, 8.3), (-77.3, 7.5),
    ]
)  # fmt: skip


def teatro_do_ponto(lon, lat) -> np.ndarray:
    """Devolve, para cada ponto, 'atlantico', 'mediterraneo' ou '' (fora da área invadida).

    O Atlântico oeste exclui o Pacífico (ao sul da linha da América Central e a oeste dos Andes); o
    Mediterrâneo exclui o Atlântico a oeste de Gibraltar, o Golfo de Biscaia, o Mar Negro com o de
    Mármara e o Mar Vermelho (a área nativa de P. miles começa ali).
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    saida = np.full(lon.shape, "", dtype=object)

    a = TEATROS["atlantico"]
    na_caixa = (lon >= a["lon"][0]) & (lon < a["lon"][1]) & (lat >= a["lat"][0]) & (lat < a["lat"][1])
    limite = np.interp(lon, _DIVISOR[:, 0], _DIVISOR[:, 1])
    pacifico = ((lon <= _DIVISOR[-1, 0]) & (lat < limite)) | ((lat < 7.5) & (lon < -66.0))
    saida[na_caixa & ~pacifico] = "atlantico"

    m = TEATROS["mediterraneo"]
    na_caixa = (lon >= -5.5) & (lon < m["lon"][1]) & (lat >= m["lat"][0]) & (lat < m["lat"][1])
    biscaia = (lon < 1.0) & (lat > 41.5)
    negro = (lon > 26.8) & (lat > 40.0)
    saida[na_caixa & ~biscaia & ~negro] = "mediterraneo"
    return saida


def haversine_km(lat1, lon1, lat2, lon2):
    """Distância de círculo máximo, em km."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * RAIO_TERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def id_da_celula(teatro: str, lat_sul: int, lon_oeste: int) -> str:
    """Identificador legível da célula de 1 grau: 'A_N25_W081' é a célula de 25°N a 26°N, 81°O a 80°O."""
    ns = "N" if lat_sul >= 0 else "S"
    lo = "E" if lon_oeste >= 0 else "W"
    return f"{teatro[0].upper()}_{ns}{abs(int(lat_sul)):02d}_{lo}{abs(int(lon_oeste)):03d}"


def grafo_do_mar(lat_nos: np.ndarray, lon_nos: np.ndarray, passo: float = PASSO_NOS):
    """Grafo de vizinhança (8 vizinhos) entre nós de mar de uma malha regular; peso = distância em km.

    Andar só por nós de mar é o que faz a distância contornar a terra. Em direções que não são nem
    retas nem diagonais, o caminho em degraus superestima a distância em até uns 8%.
    """
    i = np.rint(np.asarray(lat_nos) / passo).astype(np.int64)
    j = np.rint(np.asarray(lon_nos) / passo).astype(np.int64)
    indice = {(a, b): k for k, (a, b) in enumerate(zip(i.tolist(), j.tolist()))}
    origem, destino = [], []
    for k, (a, b) in enumerate(zip(i.tolist(), j.tolist())):
        for da, db in ((0, 1), (1, 0), (1, 1), (1, -1)):
            vizinho = indice.get((a + da, b + db))
            if vizinho is not None:
                origem.append(k)
                destino.append(vizinho)
    origem, destino = np.array(origem, dtype=int), np.array(destino, dtype=int)
    pesos = haversine_km(lat_nos[origem], lon_nos[origem], lat_nos[destino], lon_nos[destino])
    n = len(lat_nos)
    return coo_matrix((pesos, (origem, destino)), shape=(n, n)).tocsr()


def no_mais_proximo(lat_nos, lon_nos, lat, lon) -> np.ndarray:
    """Índice do nó de mar mais próximo de cada ponto (em graus, com a longitude encolhida pelo cosseno)."""
    lat_nos, lon_nos = np.asarray(lat_nos, dtype=float), np.asarray(lon_nos, dtype=float)
    lat, lon = np.atleast_1d(np.asarray(lat, dtype=float)), np.atleast_1d(np.asarray(lon, dtype=float))
    fator = np.cos(np.radians(np.mean(lat_nos)))
    arvore = cKDTree(np.column_stack([lat_nos, lon_nos * fator]))
    return arvore.query(np.column_stack([lat, lon * fator]))[1]


def distancias_pelo_mar(lat_nos, lon_nos, lat_pontos, lon_pontos, passo: float = PASSO_NOS) -> np.ndarray:
    """Matriz de distâncias pelo mar (km) entre pontos, cada um preso ao nó de mar mais próximo.

    A distância de um ponto a ele mesmo é zero; entre pontos presos ao mesmo nó, usa-se o círculo
    máximo. Pontos sem ligação pelo mar ficam com infinito.
    """
    lat_nos, lon_nos = np.asarray(lat_nos, dtype=float), np.asarray(lon_nos, dtype=float)
    lat_pontos, lon_pontos = np.asarray(lat_pontos, dtype=float), np.asarray(lon_pontos, dtype=float)
    grafo = grafo_do_mar(lat_nos, lon_nos, passo)
    nos = no_mais_proximo(lat_nos, lon_nos, lat_pontos, lon_pontos)
    unicos, inverso = np.unique(nos, return_inverse=True)
    entre_nos = dijkstra(grafo, directed=False, indices=unicos)[:, unicos]
    matriz = entre_nos[np.ix_(inverso, inverso)]
    # trecho do ponto até o seu nó, nas duas pontas
    ate_o_no = haversine_km(lat_pontos, lon_pontos, lat_nos[nos], lon_nos[nos])
    matriz = matriz + ate_o_no[:, None] + ate_o_no[None, :]
    direta = haversine_km(lat_pontos[:, None], lon_pontos[:, None], lat_pontos[None, :], lon_pontos[None, :])
    mesmo_no = nos[:, None] == nos[None, :]
    matriz = np.where(mesmo_no, direta, np.maximum(matriz, direta))
    np.fill_diagonal(matriz, 0.0)
    return matriz
