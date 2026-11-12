import numpy as np
import pytest

from peixe_leao import geografia as geo


def test_haversine_de_um_grau_no_equador():
    assert geo.haversine_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)
    assert geo.haversine_km(10, 20, 10, 20) == 0.0


def test_teatro_do_ponto_separa_o_pacifico_e_a_area_nativa():
    pontos = {
        "Dania, Flórida": (-80.05, 26.05, "atlantico"),
        "Colón, lado caribenho do Panamá": (-79.9, 9.4, "atlantico"),
        "Cidade do Panamá, lado do Pacífico": (-79.5, 8.9, ""),
        "Golfo de Fonseca (Pacífico)": (-87.7, 13.2, ""),
        "Limón, Costa Rica (Caribe)": (-83.0, 10.0, "atlantico"),
        "Costa do Peru": (-77.1, -12.0, ""),
        "Fernando de Noronha": (-32.4, -3.85, "atlantico"),
        "Arraial do Cabo": (-42.0, -23.0, "atlantico"),
        "Chipre": (33.0, 34.6, "mediterraneo"),
        "Eilat, Mar Vermelho": (34.95, 29.5, ""),
        "Mar Negro": (31.0, 43.0, ""),
        "Golfo de Biscaia": (-3.0, 44.0, ""),
        "Cádis, Atlântico": (-6.3, 36.5, ""),
        "Indonésia (área nativa)": (110.5, -8.1, ""),
    }
    for nome, (lon, lat, esperado) in pontos.items():
        assert geo.teatro_do_ponto([lon], [lat])[0] == esperado, nome


def test_id_da_celula():
    assert geo.id_da_celula("atlantico", 25, -81) == "A_N25_W081"
    assert geo.id_da_celula("atlantico", -4, -33) == "A_S04_W033"
    assert geo.id_da_celula("mediterraneo", 34, 33) == "M_N34_E033"


def _malha(lat0, lat1, lon0, lon1, terra=None):
    lat, lon = np.meshgrid(np.arange(lat0, lat1 + 0.01, 0.5), np.arange(lon0, lon1 + 0.01, 0.5), indexing="ij")
    lat, lon = lat.ravel(), lon.ravel()
    if terra is not None:
        fica = ~terra(lat, lon)
        lat, lon = lat[fica], lon[fica]
    return lat, lon


def test_distancia_pelo_mar_em_mar_aberto_e_o_circulo_maximo():
    lat, lon = _malha(0, 10, 0, 10)
    d = geo.distancias_pelo_mar(lat, lon, np.array([0.0, 10.0, 0.0]), np.array([5.0, 5.0, 0.0]))
    assert d[0, 1] == pytest.approx(geo.haversine_km(0, 5, 10, 5), rel=1e-6)  # ao longo do meridiano
    assert d[0, 0] == 0.0
    assert np.allclose(d, d.T)
    # na diagonal, os degraus da malha erram pouco para mais
    direta = geo.haversine_km(10, 5, 0, 0)
    assert direta <= d[1, 2] <= 1.09 * direta


def test_distancia_pelo_mar_contorna_a_terra():
    """Uma península entre dois pontos obriga o caminho a dar a volta."""
    lat, lon = _malha(0, 10, 0, 10, terra=lambda la, lo: (np.abs(lo - 5.0) < 0.6) & (la >= 2.0))
    d = geo.distancias_pelo_mar(lat, lon, np.array([8.0, 8.0]), np.array([3.0, 7.0]))
    direta = geo.haversine_km(8, 3, 8, 7)
    assert d[0, 1] > 3 * direta  # desce até o sul da península e volta
    lat, lon = _malha(0, 10, 0, 10, terra=lambda la, lo: np.abs(lo - 5.0) < 0.6)  # barreira completa
    d = geo.distancias_pelo_mar(lat, lon, np.array([8.0, 8.0]), np.array([3.0, 7.0]))
    assert np.isinf(d[0, 1])
