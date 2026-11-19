from datetime import date

from openpyxl import Workbook

from core.perfil.feriados import FeriadoExtra, feriados_nacionais, ler_feriados_extras


def test_feriados_nacionais_2025():
    assert set(feriados_nacionais(2025)) == {
        date(2025, 1, 1),
        date(2025, 4, 18),
        date(2025, 4, 21),
        date(2025, 5, 1),
        date(2025, 9, 7),
        date(2025, 10, 12),
        date(2025, 11, 2),
        date(2025, 11, 15),
        date(2025, 11, 20),
        date(2025, 12, 25),
    }


def test_feriados_nacionais_2026():
    assert set(feriados_nacionais(2026)) == {
        date(2026, 1, 1),
        date(2026, 4, 3),
        date(2026, 4, 21),
        date(2026, 5, 1),
        date(2026, 9, 7),
        date(2026, 10, 12),
        date(2026, 11, 2),
        date(2026, 11, 15),
        date(2026, 11, 20),
        date(2026, 12, 25),
    }


def test_feriado_de_20_de_novembro_so_entra_desde_2024():
    assert date(2023, 11, 20) not in feriados_nacionais(2023)
    assert date(2024, 11, 20) in feriados_nacionais(2024)


def test_leitor_csv_retorna_erros_por_linha(tmp_path):
    caminho = tmp_path / "extras.csv"
    caminho.write_text(
        "data,nome\n"
        "20/01/2026,Aniversário municipal\n"
        "2026-02-30,Data impossível\n"
        "2026-03-19,Feriado local\n",
        encoding="utf-8",
    )

    resultado = ler_feriados_extras(caminho)

    assert resultado.feriados == (
        FeriadoExtra(date(2026, 1, 20), "Aniversário municipal"),
        FeriadoExtra(date(2026, 3, 19), "Feriado local"),
    )
    assert len(resultado.erros) == 1
    assert resultado.erros[0].linha == 3
    assert "data inválida" in resultado.erros[0].mensagem


def test_leitor_csv_aceita_separador_ponto_e_virgula(tmp_path):
    caminho = tmp_path / "extras.csv"
    caminho.write_text("data;nome\n01/05/2026;Feriado estadual\n", encoding="utf-8")

    resultado = ler_feriados_extras(caminho)

    assert resultado.feriados == (FeriadoExtra(date(2026, 5, 1), "Feriado estadual"),)
    assert resultado.erros == ()


def test_leitor_xlsx_aceita_data_excel_e_iso(tmp_path):
    caminho = tmp_path / "extras.xlsx"
    pasta = Workbook()
    planilha = pasta.active
    planilha.append(["data", "nome"])
    planilha.append([date(2026, 1, 20), "Aniversário municipal"])
    planilha.append(["2026-03-19", "Feriado local"])
    planilha.append(["31/02/2026", "Data inválida"])
    pasta.save(caminho)

    resultado = ler_feriados_extras(caminho)

    assert resultado.feriados == (
        FeriadoExtra(date(2026, 1, 20), "Aniversário municipal"),
        FeriadoExtra(date(2026, 3, 19), "Feriado local"),
    )
    assert len(resultado.erros) == 1
    assert resultado.erros[0].linha == 4
    assert "data inválida" in resultado.erros[0].mensagem


def test_leitor_nao_lanca_excecao_para_arquivo_inexistente(tmp_path):
    resultado = ler_feriados_extras(tmp_path / "nao-existe.csv")

    assert resultado.feriados == ()
    assert resultado.erros[0].linha == 0
    assert "Não foi possível ler" in resultado.erros[0].mensagem
