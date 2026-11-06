import json
from pathlib import Path

import streamlit as st

# ==========================================
# CONFIGURAÇÕES DA PÁGINA
# ==========================================

st.set_page_config(
    page_title="Saúde em Foco",
    page_icon="🏥",
    layout="wide"
)

# ==========================================
# IDENTIDADE VISUAL
# ==========================================

st.markdown("""
<style>
    .stApp {
        background-color: #F3F7F5;
    }

    h1, h2, h3 {
        color: #174F45;
    }

    .cabecalho {
        background-color: #174F45;
        padding: 25px;
        border-radius: 12px;
        color: white;
        text-align: center;
        margin-bottom: 25px;
    }

    .cabecalho h1 {
        color: white;
        margin-bottom: 5px;
    }

    .cabecalho p {
        color: #E5F1ED;
        font-size: 17px;
        margin-bottom: 0;
    }

    .cartao {
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        border-left: 5px solid #25816D;
        margin-bottom: 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }

    .cartao h3 {
        margin-top: 0;
        color: #174F45;
    }

    .rodape {
        text-align: center;
        color: #55736B;
        padding: 25px;
        font-size: 13px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# LEITURA DOS DADOS DO ARQUIVO JSON
# ==========================================

caminho_json = Path(__file__).parent / "unidades.json"

try:
    with open(caminho_json, "r", encoding="utf-8") as arquivo:
        unidades = json.load(arquivo)

    if not isinstance(unidades, list):
        raise ValueError("O arquivo JSON precisa conter uma lista de unidades.")

except FileNotFoundError:
    st.error("Não foi encontrado o arquivo unidades.json. Verifique se ele está na mesma pasta do app.py.")
    st.stop()

except json.JSONDecodeError as erro:
    st.error(f"Não foi possível ler o unidades.json. Verifique a formatação do arquivo. Detalhe: {erro}")
    st.stop()

except ValueError as erro:
    st.error(str(erro))
    st.stop()

# ==========================================
# CABEÇALHO
# ==========================================

st.markdown("""
<div class="cabecalho">
    <h1>🏥 SAÚDE EM FOCO</h1>
    <p>Guia Digital de Serviços de Saúde</p>
</div>
""", unsafe_allow_html=True)

st.write(
    "Encontre informações sobre unidades de saúde, "
    "serviços disponíveis e localização em Juazeiro e Petrolina."
)

# ==========================================
# PESQUISA E FILTROS
# ==========================================

st.header("🔎 Encontre uma unidade de saúde")

pesquisa = st.text_input(
    "Pesquise pelo nome da unidade ou bairro:",
    placeholder="Digite o nome ou bairro..."
)

coluna1, coluna2 = st.columns(2)

with coluna1:
    filtro_cidade = st.selectbox(
        "Município:",
        ["Todas", "Juazeiro", "Petrolina"]
    )

with coluna2:
    filtro_categoria = st.selectbox(
        "Categoria:",
        ["Todos", "Hospital", "UPA", "UBS"]
    )

# ==========================================
# APLICAÇÃO DOS FILTROS
# ==========================================

unidades_filtradas = []

for unidade in unidades:
    nome = unidade.get("nome", "")
    bairro = unidade.get("bairro", "")
    cidade = unidade.get("municipio", unidade.get("cidade", ""))
    categoria = unidade.get("categoria", unidade.get("tipo", ""))

    corresponde_pesquisa = (
        pesquisa.lower() in nome.lower()
        or pesquisa.lower() in bairro.lower()
    )

    corresponde_cidade = (
        filtro_cidade == "Todas"
        or cidade == filtro_cidade
    )

    corresponde_categoria = (
        filtro_categoria == "Todos"
        or categoria == filtro_categoria
    )

    if (
        corresponde_pesquisa
        and corresponde_cidade
        and corresponde_categoria
    ):
        unidades_filtradas.append(unidade)

# ==========================================
# EXIBIÇÃO DOS RESULTADOS
# ==========================================

st.header("📍 Unidades cadastradas")

st.write(
    f"Encontramos **{len(unidades_filtradas)}** "
    "unidade(s) correspondente(s) à sua pesquisa."
)

if unidades_filtradas:
    for unidade in unidades_filtradas:
        nome = unidade.get("nome", "Nome não informado")
        categoria = unidade.get("categoria", unidade.get("tipo", "Não informada"))
        cidade = unidade.get("municipio", unidade.get("cidade", "Não informado"))
        bairro = unidade.get("bairro", "Não informado")
        endereco = unidade.get("endereco", "Não informado")
        contato = unidade.get("contato", "Não informado")
        horario = unidade.get("horario", "Não informado")

        st.markdown(f"""
        <div class="cartao">
            <h3>🏥 {nome}</h3>
            <p><b>Categoria:</b> {categoria}</p>
            <p><b>Município:</b> {cidade}</p>
            <p><b>Bairro:</b> {bairro}</p>
            <p><b>Endereço:</b> {endereco}</p>
            <p><b>Contato:</b> {contato}</p>
            <p><b>Horário:</b> {horario}</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("#### Serviços disponíveis")

        for servico in unidade.get("servicos", []):
            # Aceita tanto serviços em texto quanto objetos com categoria,
            # descrição e ícone, caso os dados sejam detalhados futuramente.
            if isinstance(servico, dict):
                icone = servico.get("icone", "🩺")
                titulo = servico.get("categoria", "Serviço")
                descricao = servico.get("descricao", "")
                st.markdown(f"**{icone} {titulo}**")
                if descricao:
                    st.write(descricao)
            else:
                st.markdown(f"🩺 **{servico}**")

        mapa = unidade.get("mapa", unidade.get("maps", ""))
        if mapa:
            st.markdown(f"[📍 Ver localização no Google Maps]({mapa})")

        fonte = unidade.get("fonte", "")
        if fonte:
            with st.expander("Consultar fonte das informações"):
                st.markdown(f"[Acessar fonte]({fonte})")

        st.divider()

else:
    st.warning(
        "Nenhuma unidade encontrada. "
        "Tente modificar sua pesquisa ou os filtros."
    )

# ==========================================
# RODAPÉ
# ==========================================

st.markdown("""
<div class="rodape">
    <p>🏥 Saúde em Foco — Guia Digital de Serviços de Saúde</p>
    <p>Informação e acessibilidade para aproximar a população dos serviços de saúde.</p>
</div>
""", unsafe_allow_html=True)
