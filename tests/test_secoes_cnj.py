from flora_mcp.text import header, sections

TJSC = (
    "DIREITO CIVIL. APELAÇÃO CÍVEL. ALIMENTOS. RECURSO DESPROVIDO.\r\n"
    "I. CASO EM EXAME\r\n1. Apelação.\r\n"
    "II. QUESTÃO EM DISCUSSÃO\r\n2. Saber se.\r\n"
    "III. RAZÕES DE DECIDIR\r\n3. Porque.\r\n"
    "IV. DISPOSITIVO E TESE\r\n4. Recurso desprovido.\r\n"
    "Tese de julgamento: 1. A tese.\r\n"
    "Dispositivos relevantes citados: CC, art. 1.694.\r\n"
    "Jurisprudência relevante citada: STJ, REsp n. 1."
)
STJ = (
    "CIVIL. RECURSO ESPECIAL. AÇÃO\nDE ALIMENTOS. PRAZO DETERMINADO.\n"
    "I. Hipótese em exame\n1. Ação.\nII. Questão em discussão\n2. Saber.\n"
    "III. Razões de decidir\n3. Porque.\nIV. Dispositivo e tese\n4. Negado.\n"
    'Tese de julgamento: "1. Tese."\nDispositivos relevantes citados: CPC, art. 528.\n'
    "Jurisprudência relevante citada: STJ, HC n. 1."
)


def by_name(text):
    return {s["nome"]: text[s["inicio"] : s["fim"]] for s in sections(text)}


def test_crlf_ementa_is_divided_and_closing_lines_are_their_own_sections():
    parts = by_name(TJSC)
    assert list(parts) == [
        "cabecalho",
        "caso_em_exame",
        "questao_em_discussao",
        "razoes_de_decidir",
        "dispositivo_e_tese",
        "tese_na_ementa",
        "dispositivos_citados",
        "jurisprudencia_citada",
    ]
    assert parts["tese_na_ementa"].strip() == "Tese de julgamento: 1. A tese."
    assert parts["dispositivos_citados"].strip() == "Dispositivos relevantes citados: CC, art. 1.694."
    assert "".join(parts.values()) == TJSC


def test_stj_hypothesis_heading_and_offsets_rebuild_the_literal_text():
    spans = sections(STJ)
    assert [s["nome"] for s in spans][:2] == ["cabecalho", "caso_em_exame"]
    assert "Dispositivos" not in STJ[spans[-3]["inicio"] : spans[-3]["fim"]]
    assert "".join(STJ[s["inicio"] : s["fim"]] for s in spans) == STJ
    assert all(s["derivador"] == "ementa-secoes-2" and len(s["sha256_secao"]) == 64 for s in spans)


def test_repeated_heading_returns_nothing():
    assert sections("A.\nI. CASO EM EXAME\nx\nI. CASO EM EXAME\ny") == []


def test_header_takes_the_earliest_of_heading_and_numbered_paragraph():
    assert header(TJSC) == ("DIREITO CIVIL. APELAÇÃO CÍVEL. ALIMENTOS. RECURSO DESPROVIDO.", False)
    assert header(STJ) == ("CIVIL. RECURSO ESPECIAL. AÇÃO\nDE ALIMENTOS. PRAZO DETERMINADO.", False)
    only_thesis = "VERBETE LONGO.\r\n1. Corpo sem títulos.\r\nTese de julgamento: x."
    assert header(only_thesis) == ("VERBETE LONGO.", False)
