import html
import json
import math
import re
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import quote_plus, urlencode
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

try:
    from streamlit_geolocation import streamlit_geolocation
except ImportError:
    streamlit_geolocation = None

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


def avaliar_funcionamento(horario):
    """Interpreta horários cadastrados sem alegar confirmação em tempo real."""
    texto_horario = str(horario or "").strip()
    normalizado = normalizar_texto(texto_horario)

    if not texto_horario or "nao confirmado" in normalizado or "nao informado" in normalizado:
        return {
            "classe": "sf-status-unknown",
            "rotulo": "Horário não confirmado",
            "detalhe": "Não há horário suficiente para estimar o funcionamento.",
        }

    if "24h" in normalizado or "24 h" in normalizado:
        return {
            "classe": "sf-status-continuous",
            "rotulo": "Atendimento 24h informado",
            "detalhe": "Informação cadastral; confirme diretamente com a unidade.",
        }

    if "atendimento continuo" in normalizado or "plantao" in normalizado:
        return {
            "classe": "sf-status-continuous",
            "rotulo": "Atendimento contínuo informado",
            "detalhe": "Informação cadastral; confirme diretamente com a unidade.",
        }

    # Os horários cadastrados em formato interpretável seguem segunda a sexta.
    dias_validos = "segunda a sexta" in normalizado or "segunda a sexta feira" in normalizado
    if not dias_validos:
        return {
            "classe": "sf-status-unknown",
            "rotulo": "Consulte o horário cadastrado",
            "detalhe": "O formato do horário não permite estimar o funcionamento agora.",
        }

    padrao = re.compile(
        r"(\d{1,2})\s*h\s*(\d{2})?\s*às\s*(\d{1,2})\s*h\s*(\d{2})?"
    )
    intervalos = []
    for match in padrao.finditer(texto_horario):
        hora_inicio = int(match.group(1))
        minuto_inicio = int(match.group(2) or 0)
        hora_fim = int(match.group(3))
        minuto_fim = int(match.group(4) or 0)
        if hora_inicio <= 23 and hora_fim <= 24 and minuto_inicio < 60 and minuto_fim < 60:
            inicio = hora_inicio * 60 + minuto_inicio
            fim = hora_fim * 60 + minuto_fim
            if inicio < fim:
                intervalos.append((inicio, fim))

    if not intervalos:
        return {
            "classe": "sf-status-unknown",
            "rotulo": "Consulte o horário cadastrado",
            "detalhe": "O horário precisa ser conferido diretamente com a unidade.",
        }

    agora = datetime.now(ZoneInfo("America/Bahia"))
    minuto_atual = agora.hour * 60 + agora.minute
    dia_util = agora.weekday() < 5
    aberto = dia_util and any(inicio <= minuto_atual < fim for inicio, fim in intervalos)

    if aberto:
        return {
            "classe": "sf-status-open",
            "rotulo": "Aberto agora, conforme horário cadastrado",
            "detalhe": "Estimativa baseada no horário informado; não confirma disponibilidade de atendimento.",
        }

    return {
        "classe": "sf-status-closed",
        "rotulo": "Fechado agora, conforme horário cadastrado",
        "detalhe": "Estimativa baseada no horário informado; feriados e alterações podem não estar contemplados.",
    }


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

def distancia_metros(lat1, lon1, lat2, lon2):
    """Calcula a distância aproximada em linha reta entre duas coordenadas."""
    raio_terra = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * raio_terra * math.atan2(math.sqrt(a), math.sqrt(1 - a))


<<<<<<< HEAD
@st.cache_data(ttl=3600, show_spinner=False)
def consultar_pontos_onibus(unidades_consulta, raio=500):
=======
def categorizar_faixa_distancia(distancia):
    """Classifica cada parada em uma única faixa de proximidade."""
    if distancia <= 300:
        return "Até 300 m"
    if distancia <= 500:
        return "De 301 a 500 m"
    if distancia <= 1000:
        return "De 501 m a 1 km"
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def consultar_pontos_onibus(unidades_consulta, raio=1000):
>>>>>>> c23e0ef (Atualiza Saúde em Foco e configura ambiente Python)
    """Consulta pontos de ônibus no OpenStreetMap via Overpass API.

    Recebe somente unidades cujas coordenadas foram marcadas como confirmadas
    pela equipe. O cache reduz consultas repetidas ao serviço público.
    """
    if not unidades_consulta:
        return {"pontos": [], "erro": None}

    consultas = []
    for _, lat, lon in unidades_consulta:
        lat, lon = float(lat), float(lon)
        consultas.extend([
            f'node(around:{raio},{lat},{lon})["highway"="bus_stop"];',
            f'node(around:{raio},{lat},{lon})["public_transport"="platform"]["bus"!="no"];',
            f'way(around:{raio},{lat},{lon})["highway"="bus_stop"];',
            f'way(around:{raio},{lat},{lon})["public_transport"="platform"]["bus"!="no"];',
        ])
    consulta = "[out:json][timeout:45];(" + "".join(consultas) + ");out center tags;"
    requisicao = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urlencode({"data": consulta}).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "SaudeEmFoco-Juazeiro/1.0 (projeto academico)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(requisicao, timeout=55) as resposta:
            dados_osm = json.loads(resposta.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as erro:
        return {"pontos": [], "erro": str(erro)}

    pontos_unicos = {}
    for elemento in dados_osm.get("elements", []):
        tags = elemento.get("tags", {})
        lat = elemento.get("lat")
        lon = elemento.get("lon")
        if lat is None or lon is None:
            centro = elemento.get("center", {})
            lat, lon = centro.get("lat"), centro.get("lon")
        if lat is None or lon is None:
            continue
        identificador = f"{elemento.get('type')}:{elemento.get('id')}"
        pontos_unicos[identificador] = {
            "id": identificador,
            "latitude": float(lat),
            "longitude": float(lon),
<<<<<<< HEAD
            "nome": tags.get("name") or tags.get("ref") or "Ponto de ônibus sem nome no cadastro",
=======
            "nome": tags.get("name") or tags.get("ref") or "Parada sem identificação nominal",
>>>>>>> c23e0ef (Atualiza Saúde em Foco e configura ambiente Python)
            "operador": tags.get("operator", ""),
            "tipo": tags.get("highway") or tags.get("public_transport") or "parada",
        }

    pontos_atribuidos = []
    for ponto in pontos_unicos.values():
        proximidade = []
        for nome_unidade, lat_unidade, lon_unidade in unidades_consulta:
            distancia = distancia_metros(
                ponto["latitude"], ponto["longitude"], float(lat_unidade), float(lon_unidade)
            )
            if distancia <= raio:
                proximidade.append((distancia, nome_unidade))
        if proximidade:
            distancia, unidade_mais_proxima = min(proximidade, key=lambda item: item[0])
            ponto["unidade_proxima"] = unidade_mais_proxima
            ponto["distancia_metros"] = round(distancia)
<<<<<<< HEAD
            ponto["osm_url"] = f"https://www.openstreetmap.org/{ponto['id'].replace(':', '/') }"
            pontos_atribuidos.append(ponto)
=======
            ponto["faixa_distancia"] = categorizar_faixa_distancia(ponto["distancia_metros"])
            ponto["osm_url"] = f"https://www.openstreetmap.org/{ponto['id'].replace(':', '/') }"
            if ponto["faixa_distancia"]:
                pontos_atribuidos.append(ponto)
>>>>>>> c23e0ef (Atualiza Saúde em Foco e configura ambiente Python)

    pontos_atribuidos.sort(key=lambda item: (item["unidade_proxima"], item["distancia_metros"]))
    return {"pontos": pontos_atribuidos, "erro": None}



def geocodificar_endereco(endereco, chave_api):
    """Converte um endereço informado em coordenadas usando o Pelias da HeiGIT."""
    consulta = f"{endereco}, Juazeiro, Bahia, Brasil"
    parametros = urlencode({
        "text": consulta,
        "boundary.country": "BR",
        "size": 1,
        "layers": "address,venue,street,locality",
    })
    url = f"https://api.heigit.org/pelias/v1/search?{parametros}"
    requisicao = urllib.request.Request(
        url,
        headers={
            "Authorization": chave_api,
            "Accept": "application/json",
            "User-Agent": "SaudeEmFoco-Juazeiro/1.0 (projeto academico)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=25) as resposta:
            dados_geograficos = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        if erro.code in (401, 403):
            raise RuntimeError("A chave da HeiGIT não foi aceita ou não tem acesso à geocodificação. Confira a configuração nos Secrets.") from None
        if erro.code == 429:
            raise RuntimeError("O limite de consultas da HeiGIT foi atingido. Aguarde alguns minutos e tente novamente.") from None
        if erro.code >= 500:
            raise RuntimeError("O serviço de localização da HeiGIT está temporariamente instável. Tente novamente mais tarde.") from None
        raise RuntimeError(f"O serviço de localização retornou o erro HTTP {erro.code}.") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Não foi possível conectar ao serviço de localização. Verifique a internet e tente novamente.") from None
    except json.JSONDecodeError:
        raise RuntimeError("O serviço de localização retornou uma resposta que não pôde ser interpretada.") from None

    resultados = dados_geograficos.get("features", [])
    if not resultados:
        return None

    geometria = resultados[0].get("geometry", {})
    coordenadas = geometria.get("coordinates", [])
    if len(coordenadas) < 2:
        return None

    propriedades = resultados[0].get("properties", {})
    return {
        "longitude": float(coordenadas[0]),
        "latitude": float(coordenadas[1]),
        "rotulo": propriedades.get("label") or consulta,
    }


def calcular_rota_ors(origem, destino, perfil, chave_api):
    """Calcula uma rota e retorna geometria GeoJSON, distância e duração."""
    url = f"https://api.heigit.org/openrouteservice/v2/directions/{perfil}/geojson"
    payload = {
        "coordinates": [
            [float(origem["longitude"]), float(origem["latitude"])],
            [float(destino["longitude"]), float(destino["latitude"])],
        ],
        "instructions": False,
    }
    requisicao = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": chave_api,
            "Content-Type": "application/json",
            "Accept": "application/geo+json",
            "User-Agent": "SaudeEmFoco-Juazeiro/1.0 (projeto academico)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=40) as resposta:
            dados_rota = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        if erro.code in (401, 403):
            raise RuntimeError("A chave da HeiGIT não foi aceita ou não tem acesso ao serviço de rotas. Confira os Secrets e as permissões da chave.") from None
        if erro.code == 404:
            raise RuntimeError("O serviço de rotas não foi encontrado. Verifique a disponibilidade da API da HeiGIT e tente novamente.") from None
        if erro.code == 429:
            raise RuntimeError("O limite de consultas de rotas foi atingido. Aguarde alguns minutos e tente novamente.") from None
        if erro.code >= 500:
            raise RuntimeError("O serviço de rotas da HeiGIT está temporariamente instável. Tente novamente mais tarde.") from None
        raise RuntimeError(f"A API de rotas retornou o erro HTTP {erro.code}. Confira o endereço de origem e tente novamente.") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Não foi possível conectar ao serviço de rotas. Verifique a internet e tente novamente.") from None
    except json.JSONDecodeError:
        raise RuntimeError("O serviço de rotas retornou uma resposta que não pôde ser interpretada.") from None

    funcionalidades = dados_rota.get("features", [])
    if not funcionalidades:
        raise RuntimeError("Não foi possível encontrar um trajeto entre a origem e a unidade selecionada.")

    primeira = funcionalidades[0]
    geometria = primeira.get("geometry", {})
    coordenadas_rota = geometria.get("coordinates", [])
    resumo = primeira.get("properties", {}).get("summary", {})
    if len(coordenadas_rota) < 2 or not resumo:
        raise RuntimeError("A API não retornou informações suficientes para exibir este trajeto.")

    return {
        "coordenadas": coordenadas_rota,
        "distancia_metros": float(resumo.get("distance", 0)),
        "duracao_segundos": float(resumo.get("duration", 0)),
    }


def exibir_mapa_rota(origem, destino, coordenadas_rota):
    """Exibe o trajeto calculado no Leaflet, sem alterar o mapa principal do guia."""
    dados = json.dumps({
        "origem": origem,
        "destino": destino,
        "rota": coordenadas_rota,
    }, ensure_ascii=False).replace("</", "<\\/")
    html_rota = """<!DOCTYPE html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <style>
      html,body{margin:0;padding:0;background:transparent}
      #mapa-rota{height:500px;width:100%;border-radius:14px;background:#e8eeeb;z-index:1}
      .leaflet-popup-content-wrapper{border-radius:12px;color:#18332e}
      .leaflet-control-zoom{border:0!important;border-radius:10px!important;overflow:hidden;box-shadow:0 2px 12px #0c383a36}
    </style></head><body>
    <div id="mapa-rota" role="region" aria-label="Trajeto entre a origem informada e a unidade de saúde"></div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
      const dados=__DADOS__;
      const mapa=L.map('mapa-rota',{zoomControl:false});
      L.control.zoom({position:'bottomright'}).addTo(mapa);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
        attribution:'&copy; OpenStreetMap contributors',maxZoom:19
      }).addTo(mapa);
      const escaparHtml=(valor)=>String(valor).replace(/[&<>\"']/g,caractere=>({
        '&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'
      }[caractere]));
      const linha=L.geoJSON({type:'Feature',properties:{},geometry:{
        type:'LineString',coordinates:dados.rota
      }},{style:{color:'#087d74',weight:6,opacity:.88,lineCap:'round',lineJoin:'round'}}).addTo(mapa);
      const inicio=L.circleMarker([dados.origem.latitude,dados.origem.longitude],{
        radius:8,color:'#ffffff',weight:3,fillColor:'#1769aa',fillOpacity:1
      }).addTo(mapa).bindPopup('<strong>Origem</strong><br>'+escaparHtml(dados.origem.rotulo));
      const fim=L.circleMarker([dados.destino.latitude,dados.destino.longitude],{
        radius:9,color:'#ffffff',weight:3,fillColor:'#d97706',fillOpacity:1
      }).addTo(mapa).bindPopup('<strong>Destino</strong><br>'+escaparHtml(dados.destino.nome));
      const limites=L.featureGroup([linha,inicio,fim]).getBounds();
      mapa.fitBounds(limites,{padding:[30,30]});
    </script></body></html>""".replace("__DADOS__", dados)
    components.html(html_rota, height=520, scrolling=False)


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



def exibir_mapa_localizacao_usuario():
    """Mostra a posição atual do usuário no navegador, sem enviar coordenadas ao servidor."""
    html_localizacao = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <style>
      html,body{margin:0;padding:0;font-family:Arial,sans-serif;color:#183b35;background:transparent}
      .sf-location-wrap{border:1px solid #dce8e3;border-radius:14px;overflow:hidden;background:#fff}
      .sf-location-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px}
      .sf-location-toolbar button{border:0;border-radius:9px;background:#176b5e;color:#fff;padding:10px 14px;font-weight:700;cursor:pointer}
      .sf-location-toolbar button:disabled{opacity:.6;cursor:wait}
      #sf-location-status{font-size:13px;color:#526760;line-height:1.4;flex:1;min-width:180px}
      #sf-user-map{height:390px;width:100%;background:#eaf0ed}
      .sf-user-dot{width:18px;height:18px;border-radius:50%;background:#2878e8;border:3px solid #fff;box-shadow:0 0 0 7px #2878e833,0 2px 8px #0004}
      .leaflet-popup-content-wrapper{border-radius:10px}
    </style></head><body>
    <div class="sf-location-wrap">
      <div class="sf-location-toolbar">
        <button id="sf-start-location" type="button">Ativar minha localização</button>
        <button id="sf-center-location" type="button" disabled>Centralizar</button>
        <span id="sf-location-status" role="status" aria-live="polite">Autorize o acesso à localização para visualizar sua posição no mapa. A posição não será armazenada pelo Saúde em Foco.</span>
      </div>
      <div id="sf-user-map" role="region" aria-label="Mapa com a localização atual do usuário"></div>
    </div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
      const map=L.map('sf-user-map').setView([-9.416,-40.50],13);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
      let userMarker=null, accuracyCircle=null, watchId=null, firstFix=true, lastPosition=null;
      const status=document.getElementById('sf-location-status');
      const start=document.getElementById('sf-start-location');
      const center=document.getElementById('sf-center-location');
      function reportError(error){
        const messages={1:'Permissão negada. Libere a localização nas configurações do navegador e tente novamente.',2:'Não foi possível determinar sua posição. Verifique o GPS ou a conexão e tente novamente.',3:'A localização demorou para responder. Tente novamente.'};
        status.textContent=messages[error.code]||'Não foi possível acessar a localização neste momento.';
        start.disabled=false;
      }
      function updatePosition(position){
        const lat=position.coords.latitude, lon=position.coords.longitude, accuracy=position.coords.accuracy;
        lastPosition=[lat,lon];
        const point=[lat,lon];
        if(!userMarker){
          userMarker=L.marker(point,{icon:L.divIcon({className:'',html:'<div class="sf-user-dot"></div>',iconSize:[24,24],iconAnchor:[12,12]}),title:'Sua localização'}).addTo(map).bindPopup('Você está aqui');
          accuracyCircle=L.circle(point,{radius:accuracy,color:'#2878e8',weight:1,fillColor:'#2878e8',fillOpacity:.08}).addTo(map);
        }else{
          userMarker.setLatLng(point);
          accuracyCircle.setLatLng(point).setRadius(accuracy);
        }
        if(firstFix){map.setView(point,16);firstFix=false;}
        status.textContent='Localização atualizada. Precisão aproximada: '+Math.round(accuracy)+' m. A posição é atualizada enquanto esta página permanece aberta.';
        center.disabled=false;
        start.disabled=false;
        start.textContent='Atualizar localização';
      }
      start.addEventListener('click',function(){
        if(!('geolocation' in navigator)){status.textContent='Este navegador não oferece suporte à geolocalização.';return;}
        if(!window.isSecureContext){status.textContent='A localização exige uma conexão segura (HTTPS). Abra a versão publicada do aplicativo.';return;}
        start.disabled=true;status.textContent='Solicitando permissão e buscando sua posição…';
        if(watchId!==null)navigator.geolocation.clearWatch(watchId);
        firstFix=true;
        watchId=navigator.geolocation.watchPosition(updatePosition,reportError,{enableHighAccuracy:true,maximumAge:5000,timeout:20000});
      });
      center.addEventListener('click',function(){if(lastPosition)map.setView(lastPosition,17);});
    </script></body></html>"""
    components.html(html_localizacao, height=485, scrolling=False)


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

    status_funcionamento = avaliar_funcionamento(horario)

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
        + f'<p class="sf-opening-status {status_funcionamento["classe"]}">'
        + f'{icone_material("schedule")}<span>{texto(status_funcionamento["rotulo"])}'
        + f'<small>{texto(status_funcionamento["detalhe"])}</small></span></p>'
        + f'<p>{icone_material("medical_services")}<span><strong>Serviços:</strong> {texto(resumo)}</span></p>'
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

    # Cálculo de rota na própria área de pesquisa, usando a localização autorizada
    # pelo usuário no navegador. As coordenadas só são enviadas ao servidor quando
    # a pessoa solicita o cálculo do trajeto.
    destinos_pesquisa = {
        str(u.get("nome", "Unidade sem nome")): obter_coordenadas(u)
        for u in filtradas
        if obter_coordenadas(u) and u.get("localizacao_confirmada") is True
    }

    with st.container(key="sf_search_route"):
        st.html(
            '<div class="sf-results-heading"><h2>'
            + icone_material("near_me")
            + 'Calcule a distância a partir de você</h2></div>'
            '<p class="sf-muted">Descubra quanto tempo leva para chegar a uma unidade encontrada, '
            'a pé ou de carro, usando sua localização atual.</p>'
        )
        if streamlit_geolocation is None:
            st.warning(
                "O recurso de localização ainda não está instalado. Atualize as dependências "
                "do projeto para habilitar esta função."
            )
        elif not destinos_pesquisa:
            st.info(
                "Não há unidades com coordenadas confirmadas entre os resultados atuais. "
                "Amplie a pesquisa ou escolha outra categoria."
            )
        else:
            localizacao_capturada = streamlit_geolocation()
            if isinstance(localizacao_capturada, dict):
                try:
                    latitude_usuario = float(localizacao_capturada.get("latitude"))
                    longitude_usuario = float(localizacao_capturada.get("longitude"))
                    if -90 <= latitude_usuario <= 90 and -180 <= longitude_usuario <= 180:
                        st.session_state["sf_localizacao_para_rota"] = {
                            "latitude": latitude_usuario,
                            "longitude": longitude_usuario,
                            "rotulo": "Minha localização atual",
                            "precisao": localizacao_capturada.get("accuracy"),
                        }
                except (TypeError, ValueError):
                    pass

            origem_atual = st.session_state.get("sf_localizacao_para_rota")
            if origem_atual:
                precisao = origem_atual.get("precisao")
                precisao_texto = (
                    f" Precisão informada pelo dispositivo: aproximadamente {float(precisao):.0f} m."
                    if isinstance(precisao, (int, float)) else ""
                )
                st.success("Localização obtida com autorização do navegador." + precisao_texto)
                with st.form("formulario_rota_pesquisa"):
                    coluna_destino_rota, coluna_modo_rota = st.columns([3, 2], gap="medium")
                    with coluna_destino_rota:
                        destino_pesquisa = st.selectbox(
                            "Unidade de saúde",
                            options=list(destinos_pesquisa.keys()),
                            key="sf_destino_rota_pesquisa",
                        )
                    with coluna_modo_rota:
                        modo_pesquisa = st.radio(
                            "Como deseja chegar?",
                            options=["A pé", "Carro"],
                            horizontal=True,
                            key="sf_modo_rota_pesquisa",
                        )
                    enviar_rota_pesquisa = st.form_submit_button(
                        "Calcular distância e tempo",
                        type="primary",
                        icon=":material/route:",
                        width="stretch",
                    )

                if enviar_rota_pesquisa:
                    st.session_state.pop("sf_rota_pesquisa_calculada", None)
                    try:
                        chave_ors_pesquisa = str(
                            st.secrets.get("openrouteservice_api_key", "")
                        ).strip()
                    except Exception:
                        chave_ors_pesquisa = ""

                    if not chave_ors_pesquisa:
                        st.error(
                            "A chave da HeiGIT não foi encontrada. Confira `openrouteservice_api_key` "
                            "nos Secrets do Streamlit."
                        )
                    else:
                        destino_coords_pesquisa = destinos_pesquisa[destino_pesquisa]
                        perfil_pesquisa = "foot-walking" if modo_pesquisa == "A pé" else "driving-car"
                        with st.spinner("Calculando o trajeto a partir da sua localização..."):
                            try:
                                resultado_rota_pesquisa = calcular_rota_ors(
                                    origem_atual,
                                    destino_coords_pesquisa,
                                    perfil_pesquisa,
                                    chave_ors_pesquisa,
                                )
                                st.session_state["sf_rota_pesquisa_calculada"] = {
                                    "origem": origem_atual,
                                    "destino": {
                                        **destino_coords_pesquisa,
                                        "nome": destino_pesquisa,
                                    },
                                    "rota": resultado_rota_pesquisa["coordenadas"],
                                    "distancia_metros": resultado_rota_pesquisa["distancia_metros"],
                                    "duracao_segundos": resultado_rota_pesquisa["duracao_segundos"],
                                    "modo": modo_pesquisa,
                                }
                            except RuntimeError as erro:
                                st.error(str(erro))
                            except Exception:
                                st.error(
                                    "Não foi possível calcular o trajeto agora. "
                                    "Verifique sua conexão e tente novamente."
                                )

                rota_pesquisa_calculada = st.session_state.get("sf_rota_pesquisa_calculada")
                if rota_pesquisa_calculada:
                    distancia_rota = rota_pesquisa_calculada["distancia_metros"]
                    duracao_rota = rota_pesquisa_calculada["duracao_segundos"]
                    distancia_texto = (
                        f"{distancia_rota:.0f} m"
                        if distancia_rota < 1000
                        else f"{distancia_rota / 1000:.1f} km"
                    )
                    minutos_rota = round(duracao_rota / 60)
                    if minutos_rota < 60:
                        tempo_texto = f"{minutos_rota} min"
                    else:
                        horas_rota, minutos_restantes_rota = divmod(minutos_rota, 60)
                        tempo_texto = (
                            f"{horas_rota} h" if not minutos_restantes_rota
                            else f"{horas_rota} h {minutos_restantes_rota} min"
                        )
                    metrica_distancia, metrica_tempo, metrica_modo = st.columns(3)
                    metrica_distancia.metric("Distância pela rota", distancia_texto)
                    metrica_tempo.metric("Tempo estimado", tempo_texto)
                    metrica_modo.metric("Deslocamento", rota_pesquisa_calculada["modo"])
                    exibir_mapa_rota(
                        rota_pesquisa_calculada["origem"],
                        rota_pesquisa_calculada["destino"],
                        rota_pesquisa_calculada["rota"],
                    )
                    st.caption(
                        "Estimativa de percurso fornecida pela HeiGIT/OpenRouteService. "
                        "O tempo pode variar conforme as condições reais do trajeto e do trânsito. "
                        "A localização é usada para calcular a rota e não é salva no cadastro do projeto."
                    )
            else:
                st.caption(
                    "Clique no botão de localização exibido abaixo e autorize o navegador. "
                    "Depois, escolha uma unidade e o meio de deslocamento."
                )

    marcadores, sem_coordenadas = [], []
    for unidade in filtradas:
        coords = obter_coordenadas(unidade)
        nome = str(unidade.get("nome", "Unidade sem nome"))
        if not coords:
            sem_coordenadas.append(nome)
            continue
        confirmada = unidade.get("localizacao_confirmada") is True
        categoria = obter_categoria(unidade)
        status_mapa = avaliar_funcionamento(unidade.get("horario"))
        popup = (
            f"<strong>{html.escape(nome)}</strong><br>"
            f"{html.escape(categoria)} · {html.escape(str(unidade.get('bairro', 'Bairro não informado')))}<br>"
            f"<span class='{html.escape(status_mapa['classe'])}'><strong>{html.escape(status_mapa['rotulo'])}</strong></span><br>"
            f"<small>{html.escape(status_mapa['detalhe'])}</small><br>"
            f"<small>{'Localização validada' if confirmada else 'Coordenada cadastrada, ainda não validada'}</small>"
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
                st.caption(
                "Ao selecionar um marcador, o mapa apresenta uma estimativa de funcionamento baseada no horário cadastrado. "
                "Essa indicação não confirma a abertura real da unidade nem a disponibilidade de atendimento. "
                "Marcadores tracejados indicam localizações provisórias, ainda não confirmadas pela equipe."
            )
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
            "Identifique pontos de ônibus mapeados nas proximidades das unidades de saúde de Juazeiro.",
            "directions_bus",
        )
        st.link_button(
            "Abrir linhas e itinerários no Cittamobi",
            "https://linhas-preview.cittamobi.com.br/linhas/estado/bahia/juazeiro",
            type="primary",
            icon=":material/open_in_new:",
        )

    st.html(
        '<h2 class="sf-section-title">Sua localização no mapa</h2>'
        '<p>Ative a localização do navegador para acompanhar sua posição enquanto utiliza esta página. '
        'O acesso depende da sua autorização e de uma conexão segura.</p>'
    )
    exibir_mapa_localizacao_usuario()
    st.caption(
        "Privacidade: a posição é exibida no próprio navegador e não é enviada nem armazenada pelo Saúde em Foco. "
        "A precisão depende do dispositivo, das permissões e do sinal disponível."
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
    unidades_com_coordenadas_confirmadas = []
    for unidade in unidades:
        coordenadas = obter_coordenadas(unidade)
        if coordenadas and unidade.get("localizacao_confirmada") is True:
            unidades_com_coordenadas_confirmadas.append((
                str(unidade.get("nome", "Unidade sem nome")),
                coordenadas["latitude"],
                coordenadas["longitude"],
            ))

    # Rotas: somente unidades com coordenadas cadastradas e confirmadas pela equipe.
    destinos_rota = {
        nome: {"latitude": lat, "longitude": lon}
        for nome, lat, lon in unidades_com_coordenadas_confirmadas
    }

    st.html(
        '<h2 class="sf-section-title">Trace sua rota até uma unidade de saúde</h2>'
        '<p>Informe de onde você vai sair, escolha o estabelecimento e veja uma estimativa do trajeto no mapa.</p>'
    )
    if not destinos_rota:
        st.info("Ainda não há unidades com localização confirmada disponíveis para o cálculo de rotas.")
    else:
        with st.form("formulario_rota_saude_foco"):
            coluna_origem, coluna_destino = st.columns([1, 1], gap="medium")
            with coluna_origem:
                origem_digitada = st.text_input(
                    "Ponto de partida",
                    placeholder="Ex.: Praça da Bandeira, Centro",
                    help="Informe um endereço ou ponto de referência em Juazeiro (BA).",
                )
            with coluna_destino:
                destino_escolhido = st.selectbox(
                    "Unidade de saúde de destino",
                    options=list(destinos_rota.keys()),
                    help="A lista inclui apenas unidades com coordenadas confirmadas pela equipe.",
                )
            modo_deslocamento = st.radio(
                "Como você pretende chegar?",
                options=["A pé", "Carro"],
                horizontal=True,
            )
            calcular = st.form_submit_button(
                "Calcular rota", type="primary", icon=":material/route:", width="stretch"
            )

        if calcular:
            st.session_state.pop("rota_saude_foco", None)
            if not origem_digitada.strip():
                st.warning("Informe o ponto de partida para calcular o trajeto.")
            else:
                try:
                    chave_ors = str(st.secrets.get("openrouteservice_api_key", "")).strip()
                except Exception:
                    chave_ors = ""

                if not chave_ors:
                    st.error(
                        "A chave da HeiGIT não foi encontrada. Configure `openrouteservice_api_key` "
                        "nos Secrets locais e no Streamlit Cloud."
                    )
                else:
                    perfil = "foot-walking" if modo_deslocamento == "A pé" else "driving-car"
                    destino_coordenadas = destinos_rota[destino_escolhido]
                    with st.spinner("Localizando o endereço e calculando o trajeto..."):
                        try:
                            origem_geografica = geocodificar_endereco(origem_digitada.strip(), chave_ors)
                            if not origem_geografica:
                                st.warning(
                                    "Não encontramos esse ponto de partida. Tente informar o nome da rua, "
                                    "o bairro ou um ponto de referência de Juazeiro."
                                )
                            else:
                                dados_trajeto = calcular_rota_ors(
                                    origem_geografica, destino_coordenadas, perfil, chave_ors
                                )
                                st.session_state["rota_saude_foco"] = {
                                    "origem": origem_geografica,
                                    "destino": {
                                        **destino_coordenadas,
                                        "nome": destino_escolhido,
                                    },
                                    "rota": dados_trajeto["coordenadas"],
                                    "distancia_metros": dados_trajeto["distancia_metros"],
                                    "duracao_segundos": dados_trajeto["duracao_segundos"],
                                    "modo": modo_deslocamento,
                                }
                        except RuntimeError as erro:
                            st.error(str(erro))
                        except Exception:
                            st.error("Ocorreu um erro inesperado ao calcular a rota. Tente novamente.")

        rota_calculada = st.session_state.get("rota_saude_foco")
        if rota_calculada:
            distancia = rota_calculada["distancia_metros"]
            duracao = rota_calculada["duracao_segundos"]
            distancia_formatada = (
                f"{distancia:.0f} m" if distancia < 1000 else f"{distancia / 1000:.1f} km"
            )
            minutos = round(duracao / 60)
            if minutos < 60:
                duracao_formatada = f"{minutos} min"
            else:
                horas, minutos_restantes = divmod(minutos, 60)
                duracao_formatada = f"{horas} h" + (f" {minutos_restantes} min" if minutos_restantes else "")

            st.success(
                f"Trajeto encontrado: {rota_calculada['origem']['rotulo']} → {rota_calculada['destino']['nome']}"
            )
            metricas_rota = st.columns(3)
            metricas_rota[0].metric("Distância estimada", distancia_formatada)
            metricas_rota[1].metric("Tempo estimado", duracao_formatada)
            metricas_rota[2].metric("Deslocamento", rota_calculada["modo"])
            exibir_mapa_rota(
                rota_calculada["origem"],
                rota_calculada["destino"],
                rota_calculada["rota"],
            )
            st.caption(
                "Estimativa calculada pela OpenRouteService/HeiGIT. O tempo não considera "
                "condições de trânsito em tempo real. A origem é interpretada no contexto de Juazeiro (BA)."
            )

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
                f'<h2>{icone_material("location_on")}Pontos de ônibus próximos às unidades</h2>'
<<<<<<< HEAD
                '<p>O guia consulta pontos de parada cadastrados no OpenStreetMap em um raio de até 500 metros das unidades com coordenadas confirmadas pela equipe.</p>'
=======
                '<p>O guia consulta pontos de parada cadastrados no OpenStreetMap em um raio de até 1 km das unidades com coordenadas confirmadas pela equipe, organizando os resultados por faixas de distância.</p>'
>>>>>>> c23e0ef (Atualiza Saúde em Foco e configura ambiente Python)
                '<p>A proximidade de um ponto não comprova que uma linha específica atende à unidade. A associação entre ponto e linha depende de confirmação do itinerário.</p>'
                '</aside>'
            )

    st.html('<h2 class="sf-section-title">Acesso ao transporte nas proximidades</h2>')
    st.write(
        "Os dados abaixo são consultados na base colaborativa do OpenStreetMap por meio da Overpass API. "
        "A distância é aproximada, em linha reta, entre o ponto mapeado e a coordenada cadastrada da unidade."
    )
    if not unidades_com_coordenadas_confirmadas:
        st.info("Ainda não há unidades com coordenadas confirmadas disponíveis para esta consulta.")
    else:
        with st.spinner("Consultando pontos de ônibus mapeados em Juazeiro..."):
<<<<<<< HEAD
            resultado_mobilidade = consultar_pontos_onibus(tuple(unidades_com_coordenadas_confirmadas), 500)
=======
            resultado_mobilidade = consultar_pontos_onibus(tuple(unidades_com_coordenadas_confirmadas), 1000)
>>>>>>> c23e0ef (Atualiza Saúde em Foco e configura ambiente Python)

        if resultado_mobilidade["erro"]:
            st.warning(
                "Não foi possível consultar o serviço do OpenStreetMap neste momento. "
                "Isso pode ocorrer por instabilidade ou limite temporário de consultas. Tente novamente mais tarde."
            )
        else:
            pontos = resultado_mobilidade["pontos"]
            unidades_com_pontos = {}
            for ponto in pontos:
                unidades_com_pontos.setdefault(ponto["unidade_proxima"], []).append(ponto)

            st.html(
                '<div class="sf-metrics">'
                f'<div class="sf-metric">{icone_material("domain")}<div><strong>{len(unidades_com_coordenadas_confirmadas)}</strong><span>Unidades analisadas</span></div></div>'
<<<<<<< HEAD
                f'<div class="sf-metric">{icone_material("directions_bus")}<div><strong>{len(pontos)}</strong><span>Pontos encontrados</span></div></div>'
                f'<div class="sf-metric">{icone_material("location_on")}<div><strong>{len(unidades_com_pontos)}</strong><span>Unidades com ponto próximo</span></div></div>'
                '</div>'
            )
            if not pontos:
                st.info("A consulta não encontrou pontos de ônibus mapeados no raio de 500 metros das unidades analisadas. Isso não significa necessariamente ausência de transporte; o mapa colaborativo pode estar incompleto.")
            else:
                for nome_unidade, _, _ in unidades_com_coordenadas_confirmadas:
                    pontos_unidade = unidades_com_pontos.get(nome_unidade, [])
                    with st.expander(f"{nome_unidade} · {len(pontos_unidade)} ponto(s) encontrado(s)", expanded=bool(pontos_unidade)):
                        if not pontos_unidade:
                            st.write("Nenhum ponto mapeado foi encontrado no raio de 500 metros desta unidade.")
                        for ponto in pontos_unidade:
                            distancia = ponto["distancia_metros"]
                            distancia_texto = f"{distancia} m" if distancia < 1000 else f"{distancia / 1000:.1f} km"
                            st.markdown(
                                f"- **{html.escape(ponto['nome'])}** — aproximadamente {distancia_texto} "
                                f"([ver no OpenStreetMap]({ponto['osm_url']}))"
                            )
                            if ponto.get("operador"):
                                st.caption(f"Operador informado no mapa: {ponto['operador']}")

            st.caption("Fonte: OpenStreetMap contributors, consultado via Overpass API. Os dados são colaborativos, podem estar incompletos ou desatualizados e não substituem a confirmação com a operadora do transporte.")
=======
                f'<div class="sf-metric">{icone_material("directions_bus")}<div><strong>{len(pontos)}</strong><span>Paradas localizadas</span></div></div>'
                f'<div class="sf-metric">{icone_material("location_on")}<div><strong>{len(unidades_com_pontos)}</strong><span>Unidades com parada próxima</span></div></div>'
                '</div>'
            )
            if not pontos:
                st.info(
                    "Nenhuma parada localizada em um raio de até 1 km das unidades analisadas. "
                    "Isso não significa necessariamente ausência de transporte; o mapa colaborativo pode estar incompleto."
                )
            else:
                faixas_distancia = (
                    "Até 300 m",
                    "De 301 a 500 m",
                    "De 501 m a 1 km",
                )
                for nome_unidade, _, _ in unidades_com_coordenadas_confirmadas:
                    pontos_unidade = unidades_com_pontos.get(nome_unidade, [])
                    with st.expander(
                        f"{nome_unidade} · {len(pontos_unidade)} parada(s) localizada(s)",
                        expanded=bool(pontos_unidade),
                    ):
                        if not pontos_unidade:
                            st.info("Nenhuma parada localizada em um raio de até 1 km.")
                            continue

                        for faixa in faixas_distancia:
                            pontos_faixa = [
                                ponto for ponto in pontos_unidade
                                if ponto.get("faixa_distancia") == faixa
                            ]
                            # Faixas sem resultados não ocupam espaço na interface.
                            if not pontos_faixa:
                                continue

                            st.markdown(f"**{faixa} · {len(pontos_faixa)} parada(s)**")
                            for ponto in pontos_faixa:
                                distancia = ponto["distancia_metros"]
                                distancia_texto = f"{distancia} m" if distancia < 1000 else f"{distancia / 1000:.1f} km"
                                st.markdown(
                                    f"- **{html.escape(ponto['nome'])}** — aproximadamente {distancia_texto} "
                                    f"([ver no OpenStreetMap]({ponto['osm_url']}))"
                                )
                                if ponto.get("operador"):
                                    st.caption(f"Operador informado no mapa: {ponto['operador']}")

            st.caption("Fonte: OpenStreetMap contributors, consultado via Overpass API. Os dados são colaborativos, podem estar incompletos ou desatualizados e não substituem a confirmação com a operadora do transporte. As distâncias são estimativas em linha reta, não trajetos a pé.")
>>>>>>> c23e0ef (Atualiza Saúde em Foco e configura ambiente Python)

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
                ("Overpass API", "Interface de consulta aos dados colaborativos do OpenStreetMap para identificar pontos de ônibus próximos às unidades com localização confirmada."),
                ("OpenRouteService / HeiGIT + Pelias", "Serviços utilizados para localizar o ponto de partida informado e calcular estimativas de trajetos a pé ou de carro até unidades com coordenadas confirmadas."),
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