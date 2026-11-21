import html
import json
import re
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import quote_plus
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Saúde em Foco | Juazeiro",
    page_icon=":material/local_hospital:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.html(Path(__file__).with_name("interface.css"))


def normalizar_texto(valor):
    texto = str(valor or "").casefold().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9 ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def obter_categoria(unidade):
    categoria = normalizar_texto(unidade.get("categoria", unidade.get("tipo", "")))
    if "hospital" in categoria:
        return "Hospital"
    if "upa" in categoria:
        return "UPA"
    if "ubs" in categoria or "usf" in categoria:
        return "UBS"
    return categoria.title() if categoria else "Não informada"


def obter_coordenadas(unidade):
    """Aceita tanto latitude/longitude na raiz quanto o objeto coordenadas antigo."""
    coordenadas = unidade.get("coordenadas", {})
    if not isinstance(coordenadas, dict):
        coordenadas = {}
    lat = unidade.get("latitude", coordenadas.get("latitude", coordenadas.get("lat")))
    lon = unidade.get(
        "longitude",
        coordenadas.get("longitude", coordenadas.get("lon", coordenadas.get("lng"))),
    )
    try:
        if lat is None or lon is None:
            return None
        lat, lon = float(lat), float(lon)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        return {"latitude": lat, "longitude": lon}
    except (TypeError, ValueError):
        return None


def link_valido(url):
    url = str(url or "").strip()
    return url if url.startswith(("https://", "http://")) else ""


def link_pesquisa_google_maps(unidade):
    """Gera uma pesquisa pelo nome e endereço, em vez de abrir apenas as coordenadas."""
    nome = str(unidade.get("nome", "")).strip()
    endereco = str(unidade.get("endereco", "")).strip()
    bairro = str(unidade.get("bairro", "")).strip()
    partes = [parte for parte in [nome, endereco, bairro, "Juazeiro - BA"] if parte]
    consulta = ", ".join(dict.fromkeys(partes))
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(consulta)}" if consulta else ""


def link_coordenadas_google_maps(unidade):
    """Abre o ponto geográfico cadastrado, quando houver coordenadas válidas."""
    coordenadas = obter_coordenadas(unidade)
    if not coordenadas:
        return ""
    consulta = f"{coordenadas['latitude']},{coordenadas['longitude']}"
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(consulta)}"


# Leitura e validação básica da base de dados.
arquivo_dados = Path(__file__).with_name("unidades.json")
try:
    with arquivo_dados.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    if not isinstance(dados, list):
        raise ValueError("A estrutura principal precisa ser uma lista.")
    unidades = [u for u in dados if isinstance(u, dict) and u.get("nome")]
except FileNotFoundError:
    st.error("Não encontrei o arquivo unidades.json. Ele precisa ficar na mesma pasta do app.py.")
    st.stop()
except (json.JSONDecodeError, ValueError) as erro:
    st.error(f"Não foi possível ler unidades.json: {erro}")
    st.stop()


# Leitura da base de perguntas frequentes.
arquivo_faq = Path(__file__).with_name("faq.json")
try:
    with arquivo_faq.open("r", encoding="utf-8") as arquivo:
        perguntas_frequentes = json.load(arquivo)
    if not isinstance(perguntas_frequentes, list):
        raise ValueError("A estrutura principal precisa ser uma lista.")
    perguntas_frequentes = [
        item for item in perguntas_frequentes
        if isinstance(item, dict) and item.get("pergunta") and item.get("resposta")
    ]
except FileNotFoundError:
    st.error("Não encontrei o arquivo faq.json. Ele precisa ficar na mesma pasta do app.py.")
    st.stop()
except (json.JSONDecodeError, ValueError) as erro:
    st.error(f"Não foi possível ler faq.json: {erro}")
    st.stop()

# O escopo do projeto permanece restrito a Juazeiro (BA).
unidades = [
    u for u in unidades
    if normalizar_texto(u.get("municipio", "juazeiro")) in ("juazeiro", "juazeiro ba", "")
]

paginas_menu = [
    ("Início", "Unidades", "local_hospital"),
    ("Perguntas frequentes", "Perguntas frequentes", "help"),
    ("Mobilidade", "Mobilidade", "directions_bus"),
    ("Sobre o projeto", "Sobre", "info"),
    ("Avaliar", "Avaliar", "star"),
]
if st.session_state.get("pagina") not in {p[0] for p in paginas_menu}:
    st.session_state.pagina = "Início"

pagina = st.session_state.pagina


def icone_material(nome):
    return f'<span class="sf-icon" aria-hidden="true">{html.escape(nome)}</span>'


def cabecalho_pagina(titulo, descricao, icone):
    st.html(
        '<div class="sf-page-banner">'
        f'<div class="sf-page-icon">{icone_material(icone)}</div>'
        f'<div><h1>{html.escape(titulo)}</h1><p>{html.escape(descricao)}</p></div></div>'
    )


icones_categoria = {"UBS": "medical_services", "UPA": "local_hospital", "Hospital": "apartment"}
classes_categoria = {"UBS": "ubs", "UPA": "upa", "Hospital": "hospital"}
icones_servicos = {
    "stethoscope", "home", "pregnant_woman", "add", "computer", "science", "child_care",
    "ambulance", "radiology", "local_hospital", "health_and_safety", "breastfeeding", "bed", "orthopedics",
}

def exibir_mapa(marcadores):
    dados_mapa = json.dumps(marcadores, ensure_ascii=False).replace("</", "<\\/")
    html_mapa = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>
    html,body{margin:0;padding:0;background:transparent}#mapa{height:100vh;width:100%;border-radius:13px;z-index:1;background:#e8eeeb}
    .legenda{display:flex;flex-wrap:wrap;gap:9px;font:12px Arial,sans-serif;padding:8px 10px;background:white;color:#26352f;border-radius:9px;box-shadow:0 1px 6px #0002}
    .ponto{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
    .leaflet-tile-pane{filter:saturate(.76) brightness(1.035)}
    .leaflet-popup-content-wrapper{border-radius:13px;color:#142a33;box-shadow:0 5px 20px #0c383a35}
    .leaflet-popup-content{line-height:1.55;margin:13px 21px}
    .leaflet-popup-content strong{font-size:1.12em}
    .leaflet-control-zoom{border:0!important;border-radius:10px!important;overflow:hidden;box-shadow:0 2px 12px #0c383a36}
    .sf-pin{width:29px;height:34px;display:grid;place-items:center;padding-bottom:4px;color:white;
      background:var(--pin);border:2px solid white;border-radius:55% 55% 56% 56% / 48% 48% 72% 72%;
      box-shadow:0 3px 7px #0b383f55;font:900 20px/1 Arial,sans-serif;box-sizing:border-box}
    .sf-pin.provisorio{border-style:dashed;background:#fff;color:var(--pin);border-color:var(--pin)}
    </style></head><body><div id="mapa" role="region" aria-label="Localização das unidades de saúde"></div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
    const dados=__DADOS__;
    const mapa=L.map('mapa',{zoomControl:false});
    L.control.zoom({position:'bottomright',zoomInTitle:'Ampliar',zoomOutTitle:'Reduzir'}).addTo(mapa);
    const cores={'UBS':'#087d74','UPA':'#166b5d','Hospital':'#0668a8'};
    const letras={'UBS':'+','UPA':'U','Hospital':'H'};
    const pontos=[];
    dados.forEach(u=>{const p=[u.latitude,u.longitude], cor=cores[u.categoria]||'#087d74';
          const icone=L.divIcon({className:'',iconSize:[29,34],iconAnchor:[14,33],popupAnchor:[0,-30],
            html:'<span class="sf-pin'+(u.confirmada?'':' provisorio')+'" style="--pin:'+cor+'">'+(letras[u.categoria]||'+')+'</span>'});
          L.marker(p,{icon:icone,title:u.nome,alt:u.nome}).addTo(mapa).bindPopup(u.popup);
          pontos.push(p);});
    if(pontos.length>1)mapa.fitBounds(pontos,{padding:[28,28]});else mapa.setView(pontos[0],15);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap contributors',maxZoom:19}).addTo(mapa);
    const legenda=L.control({position:'bottomleft'});legenda.onAdd=function(){const d=L.DomUtil.create('div','legenda');d.innerHTML=
      '<span><span class="ponto" style="background:#087d74"></span>UBS</span>' +
      '<span><span class="ponto" style="background:#166b5d"></span>UPA</span>' +
      '<span><span class="ponto" style="background:#0668a8"></span>Hospital</span>';return d;};legenda.addTo(mapa);
    </script></body></html>""".replace("__DADOS__", dados_mapa)
    components.html(html_mapa, height=534, scrolling=False)


def cartao_unidade(unidade):
    nome = str(unidade.get("nome", "Nome não informado"))
    categoria = obter_categoria(unidade)
    bairro = unidade.get("bairro") or "Bairro não informado"
    endereco = unidade.get("endereco") or "Endereço não informado"
    local = endereco
    if unidade.get("bairro") and normalizar_texto(bairro) not in normalizar_texto(endereco):
        local = f"{endereco} · {bairro}"
    contato = unidade.get("contato") or "Contato não informado"
    horario = unidade.get("horario") or "Horário não informado"
    servicos = unidade.get("servicos")
    if not isinstance(servicos, list):
        servicos = []

    def texto(valor):
        return html.escape(str(valor))

    def link(rotulo, url, classe=""):
        return f'<a class="{classe}" href="{texto(url)}" target="_blank" rel="noopener noreferrer">{rotulo}</a>'

    rotulos_servicos = [
        servico.get("categoria", "Serviço") if isinstance(servico, dict) else servico
        for servico in servicos
    ]
    resumo = ", ".join(map(str, rotulos_servicos[:3])) or "Consulte a unidade"
    if len(servicos) > 3:
        resumo += f" e mais {len(servicos) - 3}"
    servicos_html = []
    for rotulo, servico in zip(rotulos_servicos, servicos):
        descricao = servico.get("descricao") if isinstance(servico, dict) else ""
        icone = servico.get("icone") if isinstance(servico, dict) else None
        if not isinstance(icone, str) or icone not in icones_servicos:
            icone = "medical_services"
        servicos_html.append(
            f'<li>{icone_material(icone)}<strong>{texto(rotulo)}</strong>'
            + (f' — {texto(descricao)}' if descricao else "") + '</li>'
        )
    detalhes_servicos = (
        "<ul>" + "".join(servicos_html) + "</ul>" if servicos
        else "<p>Serviços específicos ainda não cadastrados. Confirme a oferta diretamente com o estabelecimento.</p>"
    )

    fontes = [
        ("Ver coordenadas", link_coordenadas_google_maps(unidade)),
        ("Consultar fonte", link_valido(unidade.get("fonte"))),
    ]
    fontes_adicionais = unidade.get("fontes_adicionais")
    if isinstance(fontes_adicionais, list):
        for fonte in fontes_adicionais:
            if isinstance(fonte, dict):
                fontes.append((fonte.get("nome", "Fonte complementar"), link_valido(fonte.get("url"))))
            else:
                fontes.append(("Fonte complementar", link_valido(fonte)))
    links = "".join(f'<li>{link(texto(rotulo), url)}</li>' for rotulo, url in fontes if url)

    return (
        f'<article class="sf-card sf-card-{classes_categoria.get(categoria, "outra")}">'
        '<div class="sf-card-main">'
        f'<div class="sf-card-symbol">{icone_material(icones_categoria.get(categoria, "medical_services"))}</div>'
        '<div class="sf-card-info">'
        f'<div class="sf-card-heading"><h3>{texto(nome)}</h3>'
        f'<span class="sf-badge">{texto(categoria)}</span></div>'
        f'<p>{icone_material("location_on")}<span>{texto(local)}</span></p>'
        f'<p>{icone_material("call")}<span>{texto(contato)}</span></p>'
        f'<p>{icone_material("medical_services")}<span><strong>Serviços:</strong> {texto(resumo)}</span></p>'
        '</div></div>'
        '<div class="sf-card-actions">'
        f'<details class="sf-details"><summary class="sf-action">{icone_material("info")}Ver detalhes</summary>'
        '<div class="sf-details-body"><dl>'
        f'<dt>Horário informado</dt><dd>{texto(horario)}</dd>'
        f'<dt>CNES</dt><dd>{texto(unidade.get("cnes") or "Não informado")}</dd>'
        f'<dt>Esfera de gestão</dt><dd>{texto(unidade.get("esfera_gestao") or "Não informada")}</dd>'
        f'</dl><h4>Serviços disponíveis</h4>{detalhes_servicos}'
        + (f'<h4>Fontes e localização no mapa</h4><ul>{links}</ul>' if links else "")
        + '</div></details>'
        + link(f'{icone_material("near_me")}Encontrar unidade', link_pesquisa_google_maps(unidade), "sf-action sf-action-primary")
        + '</div></article>'
    )


with st.container(key="sf_header"):
    marca, menu = st.columns([4, 6], vertical_alignment="center")
    with marca:
        st.html(
            '<div class="sf-brand">'
            f'<span class="sf-brand-mark" aria-hidden="true">{icone_material("favorite")}</span>'
            '<span class="sf-brand-name">Saúde em Foco</span>'
            f'<span class="sf-city">{icone_material("location_on")}Juazeiro · Bahia</span>'
            '</div>'
        )
    with menu:
        for coluna, (destino, rotulo, icone) in zip(st.columns([1.05, 1.8, 1.2, .85, .9]), paginas_menu):
            coluna.button(
                rotulo,
                icon=f":material/{icone}:",
                key=f"menu_{destino}",
                type="primary" if pagina == destino else "tertiary",
                width="stretch",
                on_click=lambda destino=destino: st.session_state.update(pagina=destino),
            )

if pagina == "Início":
    with st.container(key="sf_hero"):
        st.html(
            '<div class="sf-intro">'
            '<h1>Encontre atendimento <em>perto de você</em></h1>'
            '<p>Pesquise unidades de saúde em Juazeiro – BA pelo nome, bairro ou endereço. '
            'Confira os serviços cadastrados, horários e a localização no mapa.</p>'
            '</div>'
        )
        col_busca, col_mapa = st.columns([7, 3], vertical_alignment="center")
        with col_busca:
            pesquisa = st.text_input(
                "Pesquise por bairro, endereço ou unidade",
                placeholder="Digite seu bairro, endereço ou unidade...",
                icon=":material/search:",
                label_visibility="collapsed",
                key="pesquisa_unidade",
            )
        with col_mapa:
            st.html(
                '<a class="sf-action sf-action-primary sf-map-cta" href="#mapa-das-unidades" target="_self">'
                f'{icone_material("location_on")}Consultar localização</a>'
            )

        rotulos_categoria = {
            "Todas": "Todas",
            "UBS": ":material/medical_services: UBS",
            "UPA": ":material/local_hospital: UPA",
            "Hospital": ":material/apartment: Hospitais",
        }
        filtro_categoria = st.radio(
            "Filtrar por tipo de atendimento:",
            ["Todas", "UBS", "UPA", "Hospital"],
            format_func=rotulos_categoria.__getitem__,
            horizontal=True,
            key="filtro_categoria",
        )

    termo = normalizar_texto(pesquisa)
    filtradas = []
    for unidade in unidades:
        campos = " ".join(str(unidade.get(campo, "")) for campo in ("nome", "bairro", "endereco"))
        corresponde_texto = not termo or termo in normalizar_texto(campos)
        corresponde_categoria = filtro_categoria == "Todas" or obter_categoria(unidade) == filtro_categoria
        if corresponde_texto and corresponde_categoria:
            filtradas.append(unidade)

    marcadores, sem_coordenadas = [], []
    for unidade in filtradas:
        coords = obter_coordenadas(unidade)
        nome = str(unidade.get("nome", "Unidade sem nome"))
        if not coords:
            sem_coordenadas.append(nome)
            continue
        confirmada = unidade.get("localizacao_confirmada") is True
        categoria = obter_categoria(unidade)
        popup = (
            f"<strong>{html.escape(nome)}</strong><br>"
            f"{html.escape(categoria)} · {html.escape(str(unidade.get('bairro', 'Bairro não informado')))}<br>"
            f"{'Localização validada' if confirmada else 'Coordenada cadastrada, ainda não validada'}"
        )
        marcadores.append({
            "latitude": coords["latitude"], "longitude": coords["longitude"],
            "popup": popup, "categoria": categoria, "confirmada": confirmada, "nome": nome,
        })

    with st.container(key="sf_results"):
        col_lista, col_localizacao = st.columns([43, 55], gap="medium")
        with col_lista:
            quantidade = len(filtradas)
            legenda_resultados = "resultado" if quantidade == 1 else "resultados"
            st.html(
                '<div class="sf-results-heading">'
                f'<h2>{icone_material("domain")}Unidades encontradas</h2>'
                f'<span>{quantidade} {legenda_resultados}</span></div>'
            )
            if not filtradas:
                st.warning("Nenhuma unidade encontrada. Tente outro termo ou categoria.")
            for unidade in filtradas:
                st.html(cartao_unidade(unidade))

        with col_localizacao:
            st.html('<h2 id="mapa-das-unidades" class="sf-visually-hidden" tabindex="-1">Mapa das unidades</h2>')
            if marcadores:
                exibir_mapa(marcadores)
            else:
                st.info("Nenhuma das unidades encontradas possui coordenadas cadastradas para exibição no mapa.")

            indicadores = [
                ("domain", len(unidades), "Unidades no guia"),
                ("category", len({obter_categoria(u) for u in unidades}), "Categorias"),
                ("location_on", sum(obter_coordenadas(u) is not None for u in unidades), "Com coordenadas"),
            ]
            st.html(
                '<div class="sf-metrics">' + "".join(
                    f'<div class="sf-metric">{icone_material(icone)}'
                    f'<div><strong>{valor}</strong><span>{rotulo}</span></div></div>'
                    for icone, valor, rotulo in indicadores
                ) + '</div>'
            )
            if marcadores:
                st.caption("Marcadores tracejados indicam localizações provisórias, ainda não confirmadas pela equipe.")
            if sem_coordenadas:
                with st.expander(f"Unidades sem coordenadas ({len(sem_coordenadas)})"):
                    st.write(" · ".join(sem_coordenadas))
            st.caption("O guia reúne uma seleção de estabelecimentos da rede municipal.")

elif pagina == "Perguntas frequentes":
    with st.container(key="sf_page_intro"):
        cabecalho_pagina(
            "Perguntas frequentes",
            "Pesquise por uma palavra-chave ou escolha uma das perguntas sugeridas para entender como utilizar o Saúde em Foco.",
            "help",
        )
        termo_faq = st.text_input(
            "O que você deseja saber?",
            placeholder="Ex.: UBS, vacinação, endereço, ônibus, agendamento...",
            icon=":material/search:",
            key="pesquisa_faq",
        )
    termo_normalizado = normalizar_texto(termo_faq)

    if termo_normalizado:
        palavras_busca = termo_normalizado.split()
        resultados_faq = []
        for item in perguntas_frequentes:
            texto_item = normalizar_texto(" ".join([
                str(item.get("pergunta", "")),
                str(item.get("resposta", "")),
                " ".join(item.get("palavras_chave", []))
                    if isinstance(item.get("palavras_chave", []), list)
                    else str(item.get("palavras_chave", "")),
                str(item.get("categoria", "")),
            ]))
            if all(palavra in texto_item for palavra in palavras_busca):
                resultados_faq.append(item)
    else:
        resultados_faq = perguntas_frequentes

    with st.container(key="sf_faq"):
        quantidade = len(resultados_faq)
        legenda = "pergunta encontrada" if quantidade == 1 else "perguntas encontradas"
        st.html(
            '<div class="sf-results-heading"><h2>Dúvidas por assunto</h2>'
            f'<span>{quantidade} {legenda}</span></div>'
        )
        if not resultados_faq:
            st.info(
                "Não encontramos uma pergunta com esses termos. "
                "Tente palavras mais simples, como “UBS”, “mapa” ou “horário”.",
                icon=":material/info:",
            )

        categorias_faq = {}
        for item in resultados_faq:
            categoria = item.get("categoria", "Outras dúvidas")
            categorias_faq.setdefault(categoria, []).append(item)
        for indice, (categoria, itens) in enumerate(categorias_faq.items()):
            with st.container(key=f"sf_faq_group_{indice}"):
                st.html(f'<h3 class="sf-faq-topic">{html.escape(categoria)}</h3>')
                for item in itens:
                    with st.expander(item["pergunta"]):
                        st.write(item["resposta"])
                        if item.get("observacao"):
                            st.caption(item["observacao"])

        st.caption(
            "As respostas têm caráter informativo. Para confirmar horários, serviços "
            "e condições de atendimento, consulte diretamente o estabelecimento ou "
            "os canais oficiais de saúde."
        )

elif pagina == "Mobilidade":
    with st.container(key="sf_page_intro"):
        cabecalho_pagina(
            "Mobilidade e transporte público",
            "Consulte linhas, itinerários e pontos de parada do transporte coletivo de Juazeiro.",
            "directions_bus",
        )
        st.link_button(
            "Abrir linhas e itinerários no Cittamobi",
            "https://linhas-preview.cittamobi.com.br/linhas/estado/bahia/juazeiro",
            type="primary",
            icon=":material/open_in_new:",
        )

    linhas = [
        ("102", "João Paulo II / Piranga"),
        ("106", "Piranga / Centro"),
        ("200", "Dom José Rodrigues / Piranga"),
        ("202", "Humberto Martins"),
        ("203", "Kidé"),
        ("204", "Itaberaba / Circular"),
        ("207", "Rua São Francisco / Humberto Martins / Piranga"),
    ]
    with st.container(key="sf_mobility"):
        principal, apoio = st.columns([7, 4], gap="large")
        with principal:
            st.html(
                '<h2 class="sf-section-title">Linhas identificadas na pesquisa</h2>'
                '<ul class="sf-line-list">'
                + "".join(
                    f'<li><span class="sf-line-number">{icone_material("directions_bus")}Linha {codigo}</span>'
                    f'<span>{html.escape(nome)}</span></li>'
                    for codigo, nome in linhas
                )
                + '</ul>'
            )
            st.caption("Relação inicial, não necessariamente completa. Confira o itinerário atualizado na plataforma antes de viajar.")
        with apoio:
            st.html(
                '<aside class="sf-aside">'
                f'<h2>{icone_material("schedule")}Consulta de itinerários</h2>'
                '<p>As linhas e os horários podem sofrer alterações. A consulta atualizada deve ser feita diretamente na plataforma de transporte.</p>'
                f'<h2>{icone_material("location_on")}Integração com as unidades de saúde</h2>'
                '<p>Uma linha só será associada a uma unidade quando houver confirmação de pontos de parada próximos ao endereço. '
                'O guia ainda não indica linhas específicas para cada estabelecimento.</p>'
                '</aside>'
            )

elif pagina == "Sobre o projeto":
    with st.container(key="sf_page_intro"):
        cabecalho_pagina(
            "Sobre o Saúde em Foco",
            "O Saúde em Foco é um guia digital acadêmico que reúne informações sobre estabelecimentos públicos de saúde de Juazeiro – Bahia, "
            "facilitando a consulta de endereços, contatos, horários, serviços cadastrados e localização.",
            "info",
        )

    with st.container(key="sf_about"):
        principal, equipe_col = st.columns([7, 4], gap="large")
        with principal:
            st.html(
                '<section class="sf-about-copy">'
                '<h2 class="sf-section-title">Objetivo</h2>'
                '<p>Facilitar o acesso a informações organizadas sobre unidades públicas de saúde do município, '
                'contribuindo para que a população encontre e localize esses serviços.</p>'
                '<h2 class="sf-section-title">Como funciona</h2>'
                '<p>A aplicação utiliza uma base de dados em JSON, permite pesquisar estabelecimentos pelo nome, bairro ou endereço, '
                'filtrar por categoria e visualizar no mapa os registros com coordenadas cadastradas.</p>'
                '</section>'
            )
            st.info(
                "A base representa uma seleção de estabelecimentos e não deve ser interpretada como a relação completa da rede municipal. "
                "Dados cadastrais, horários e serviços podem mudar; confirme informações diretamente com a unidade.",
                icon=":material/info:",
            )
        with equipe_col:
            equipe = [
                "Ana Julia Alves de Lima Silva", "Emilly Kauany M. Silva",
                "Marianna Haika da Silva Oliveira", "Rebeca Fonseca da Silva",
                "Sophia Santos Araujo", "Valentina Santana Queiroz",
            ]
            st.html(
                '<aside class="sf-aside">'
                f'<h2>{icone_material("school")}Créditos acadêmicos</h2>'
                '<dl class="sf-creditos">'
                '<dt>Universidade</dt><dd>Universidade do Estado da Bahia – UNEB</dd>'
                '<dt>Curso</dt><dd>Jornalismo em Multimeios</dd>'
                '<dt>Professor orientador</dt><dd>Cecílio Bastos</dd>'
                '<dt>Local e ano</dt><dd>Juazeiro – Bahia · 2026</dd>'
                '</dl>'
                f'<h2>{icone_material("groups")}Equipe desenvolvedora</h2>'
                '<ul class="sf-equipe">'
                + "".join(f'<li>{html.escape(nome)}</li>' for nome in equipe)
                + '</ul></aside>'
            )
        st.html('<h2 class="sf-section-title">Tecnologias e ferramentas</h2>')
        st.write("O projeto combina ferramentas de desenvolvimento web, organização de dados, mapas digitais e registro de avaliações.")

        grupos_tecnologias = [
            ("code", "Desenvolvimento da aplicação", [
                ("Python", "Linguagem de programação utilizada na lógica e no funcionamento do sistema."),
                ("Streamlit", "Framework utilizado para construir e disponibilizar a aplicação web."),
            ]),
            ("database", "Interface e organização de dados", [
                ("HTML, CSS e JavaScript", "Tecnologias utilizadas na estrutura, apresentação visual e interações de componentes da interface e do mapa."),
                ("JSON", "Formato de arquivo estruturado utilizado para organizar os dados das unidades e as perguntas frequentes."),
            ]),
            ("map", "Mapas e integração", [
                ("Leaflet + OpenStreetMap", "Biblioteca de mapas interativos e base cartográfica utilizada na visualização geográfica."),
                ("Google Apps Script", "Serviço utilizado para intermediar o envio das avaliações preenchidas na aplicação."),
                ("Google Sheets", "Planilha utilizada para receber e organizar as respostas da avaliação, conforme a configuração da integração."),
            ]),
        ]
        st.html(
            '<div class="sf-tech-grid">'
            + "".join(
                f'<section class="sf-tech"><h3>{icone_material(icone)}{titulo}</h3><dl>'
                + "".join(f'<dt>{nome}</dt><dd>{detalhe}</dd>' for nome, detalhe in tecnologias)
                + '</dl></section>'
                for icone, titulo, tecnologias in grupos_tecnologias
            )
            + '</div>'
        )
        st.caption("O registro das avaliações depende da configuração do endereço e da chave de acesso da integração nos segredos da aplicação.")
        st.caption("Mapa: © OpenStreetMap contributors.")

else:  # Avaliar
    with st.container(key="sf_page_intro"):
        cabecalho_pagina(
            "Avalie sua experiência",
            "Sua opinião ajuda a equipe a avaliar a facilidade de uso do guia.",
            "star",
        )

    with st.container(key="sf_feedback"):
        formulario, apoio = st.columns([7, 4], gap="large")
        with formulario, st.form("formulario_avaliacao", clear_on_submit=True):
            st.html('<h2 class="sf-section-title">Questionário</h2>')
            primeira, segunda = st.columns(2)
            avaliacao = primeira.radio(
                "1. Como você avalia sua experiência geral?",
                ["Muito boa", "Boa", "Regular", "Ruim"],
                index=None,
            )
            utilidade = segunda.radio(
                "2. As informações encontradas foram úteis?",
                ["Sim", "Parcialmente", "Não"],
                index=None,
            )
            terceira, quarta = st.columns(2)
            localizacao = terceira.radio(
                "3. Você conseguiu localizar uma unidade de saúde?",
                ["Sim", "Não", "Não tentei localizar"],
                index=None,
            )
            navegacao = quarta.radio(
                "4. Como foi navegar pelo Saúde em Foco?",
                ["Muito fácil", "Fácil", "Regular", "Difícil"],
                index=None,
            )
            sugestao = st.text_area(
                "5. Deixe uma sugestão ou comentário (opcional)",
                max_chars=1000,
                placeholder="Conte o que funcionou bem ou o que podemos melhorar...",
            )
            recomendacao = st.radio(
                "6. Você recomendaria este guia a outra pessoa?",
                ["Sim", "Não", "Talvez"],
                index=None,
                horizontal=True,
            )
            enviar = st.form_submit_button(
                "Enviar avaliação", type="primary", icon=":material/send:", width="stretch"
            )
        with apoio:
            st.html(
                '<aside class="sf-aside">'
                f'<h2>{icone_material("lock")}Privacidade da avaliação</h2>'
                '<p>O formulário não solicita nome, e-mail ou informações de saúde.</p>'
                '<p>As respostas serão armazenadas em uma planilha para avaliação acadêmica do projeto. '
                'Não inclua dados pessoais ou informações sensíveis no campo de sugestão.</p>'
                '</aside>'
            )

    with formulario:
        if enviar:
            campos_obrigatorios = [avaliacao, utilidade, localizacao, navegacao, recomendacao]
            if any(campo is None for campo in campos_obrigatorios):
                st.warning("Responda às perguntas obrigatórias antes de enviar. A sugestão é opcional.", icon=":material/warning:")
            else:
                try:
                    configuracao = st.secrets["feedback"]
                    url_script = str(configuracao["url"]).strip()
                    token = str(configuracao["token"]).strip()

                    if not url_script.startswith("https://script.google.com/"):
                        raise ValueError("A URL de integração não está configurada corretamente.")
                    if not token:
                        raise ValueError("O token de segurança não foi configurado.")

                    payload = {
                        "token": token,
                        "avaliacao": avaliacao,
                        "utilidade": utilidade,
                        "localizacao": localizacao,
                        "navegacao": navegacao,
                        "sugestao": sugestao.strip(),
                        "recomendacao": recomendacao,
                    }
                    requisicao = urllib.request.Request(
                        url_script,
                        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(requisicao, timeout=25) as resposta_http:
                        retorno = json.loads(resposta_http.read().decode("utf-8"))

                    if retorno.get("sucesso") is True:
                        st.success("Avaliação enviada com sucesso! Obrigado por contribuir com o Saúde em Foco.", icon=":material/check_circle:")
                    else:
                        st.error(
                            "Não foi possível registrar a avaliação. "
                            + str(retorno.get("mensagem", "Verifique a configuração da integração."))
                        )
                except KeyError:
                    st.error(
                        "A integração ainda não foi configurada nos Secrets do Streamlit Cloud. "
                        "Adicione as configurações indicadas pela equipe do projeto."
                    )
                except urllib.error.HTTPError as erro:
                    st.error(f"O serviço de avaliação retornou um erro HTTP ({erro.code}). Tente novamente mais tarde.")
                except urllib.error.URLError:
                    st.error("Não foi possível conectar à planilha. Verifique a internet e tente novamente.")
                except (TimeoutError, json.JSONDecodeError, ValueError) as erro:
                    st.error(f"Não foi possível concluir o envio: {erro}")
                except Exception:
                    st.error("Ocorreu um erro inesperado ao enviar sua avaliação. Tente novamente.")


st.html(
    f'<footer class="sf-footer"><strong>{icone_material("local_hospital")}Saúde em Foco</strong><br>'
    'Guia Digital de Serviços de Saúde · Juazeiro – Bahia · 2026</footer>'
)
