import numpy as np
import pandas as pd

from peixe_leao import coleta, dados


def _relevo_sintetico() -> dict:
    """Caixa do Atlântico de 20°N a 24°N e 70°O a 64°O: terra a oeste de 68°O, plataforma até 66°O, fundo depois.

    Uma depressão em terra (abaixo do nível do mar, sem ligação com o oceano) fica em 69,5°O.
    """
    lat = np.round(np.arange(20.0, 23.95, 0.1), 1)
    lon = np.round(np.arange(-70.0, -64.05, 0.1), 1)
    lon2, _ = np.meshgrid(lon, lat)
    altitude = np.where(lon2 < -68.0, 50.0, np.where(lon2 < -66.0, -40.0, -3000.0))
    altitude[(np.abs(lon2 + 69.5) < 0.15)] = -100.0
    return {"lat": lat, "lon": lon, "altitude": altitude}


def test_grade_so_tem_celulas_de_plataforma_ligadas_ao_mar():
    grade, nos = dados.montar_grade("atlantico", _relevo_sintetico())
    assert set(grade["lon_oeste"]) == {-68, -67}  # as duas colunas de plataforma; a depressão em terra fica fora
    assert set(grade["lat_sul"]) == {20, 21, 22, 23}
    assert (grade["pontos_plataforma"] == 100).all()
    assert grade["celula"].iloc[0].startswith("A_N2")
    assert nos["lon"].min() >= -68.5  # nenhum nó dentro da depressão


def test_em_terra_olha_o_ponto_e_os_vizinhos():
    relevo = _relevo_sintetico()
    terra = dados.em_terra(relevo, lat=np.array([22.0, 22.0, 22.0]), lon=np.array([-69.0, -68.05, -67.0]))
    assert terra.tolist() == [True, False, False]  # o ponto a 5 km da costa tem vizinho no mar


def test_atribuir_celula_usa_a_vizinha_de_plataforma_mais_proxima():
    grade, _ = dados.montar_grade("atlantico", _relevo_sintetico())
    celulas = dados.atribuir_celula(grade, np.array([22.5, 22.5, 22.5]), np.array([-67.5, -65.9, -64.5]))
    assert celulas[0] == "A_N22_W068"
    assert celulas[1] == "A_N22_W067"  # mar fundo colado à plataforma: fica na vizinha
    assert celulas[2] is None  # longe demais de qualquer plataforma


def _registro(**campos) -> dict:
    padrao = {
        "fonte": "GBIF", "id": "1", "conjunto": "x", "lat": 22.5, "lon": -67.5, "ano": 2010.0, "mes": 6.0, "dia": 1.0,
        "base": "HUMAN_OBSERVATION", "ocorrencia": None, "situacao": "",
    }  # fmt: skip
    return {**padrao, **campos}


def test_remover_duplicatas_entre_fontes():
    registros = pd.DataFrame(
        [
            _registro(fonte="NAS", id="n1"),
            _registro(fonte="GBIF", id="g1"),  # mesma coordenada e data do NAS
            _registro(fonte="GBIF", id="g2", conjunto=coleta.CONJUNTO_NAS_NO_GBIF, lat=23.1),  # o NAS dentro do GBIF
            _registro(fonte="GBIF", id="g3", lat=21.2, ocorrencia="https://www.inaturalist.org/observations/1"),
            _registro(fonte="OBIS", id="o1", lat=21.9, ocorrencia="https://www.inaturalist.org/observations/1"),
            _registro(fonte="OBIS", id="o2", lat=20.4, mes=np.nan, dia=np.nan),
            _registro(fonte="OBIS", id="o3", lat=20.4, mes=7.0, dia=2.0),  # outra data: não é duplicata
        ]
    )
    limpo = dados.remover_duplicatas(registros)
    assert sorted(limpo["id"]) == ["g3", "n1", "o2", "o3"]


def test_registro_sozinho_nao_data_a_chegada():
    grade, _ = dados.montar_grade("atlantico", _relevo_sintetico())
    registros = pd.DataFrame(
        [
            {"celula": "A_N20_W068", "ano": 1996.0},  # sozinho: o seguinte por perto é de 2009
            {"celula": "A_N20_W068", "ano": 2009.0},  # corroborado pelo de 2010 na célula vizinha
            {"celula": "A_N21_W067", "ano": 2010.0},  # sem sucessor, mas...
            {"celula": "A_N21_W067", "ano": 2010.0},  # ...há outro registro no mesmo ano
            {"celula": "A_N23_W068", "ano": 2010.0},  # longe dos outros (duas células de distância) e sozinho
        ]
    )
    assert dados.marcar_corroborados(registros, grade).tolist() == [False, True, True, True, False]
    # com ano mínimo, registro antigo nem data a chegada nem corrobora outro
    cedo = pd.DataFrame([{"celula": "A_N20_W068", "ano": 2008.0}, {"celula": "A_N20_W068", "ano": 2008.0}, {"celula": "A_N20_W068", "ano": 2012.0}])
    assert dados.marcar_corroborados(cedo, grade, ano_minimo=2012).tolist() == [False, False, False]
    assert dados.marcar_corroborados(cedo, grade).tolist() == [True, True, False]


def test_limpar_registros_conta_cada_filtro():
    relevo = _relevo_sintetico()
    grade, _ = dados.montar_grade("atlantico", relevo)
    registros = pd.DataFrame(
        [
            _registro(id="ok"),
            _registro(id="sem_ano", ano=np.nan),
            _registro(id="nativo", lat=-8.1, lon=110.5),
            _registro(id="aquario", base="LIVING_SPECIMEN"),
            _registro(id="antigo", ano=1970.0),
            _registro(id="terra", lon=-69.0),
            _registro(id="fundo", lon=-64.5),
        ]
    )
    limpo, funil = dados.limpar_registros(registros, {"atlantico": grade}, {"atlantico": relevo})
    assert limpo["id"].tolist() == ["ok"]
    assert limpo["celula"].tolist() == ["A_N22_W068"]
    assert [linha["total"] for linha in funil] == [7, 6, 5, 4, 3, 3, 2, 1]
