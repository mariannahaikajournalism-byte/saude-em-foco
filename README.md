# Saúde em Foco — Juazeiro (BA)

Guia digital acadêmico para consulta de informações sobre estabelecimentos públicos de saúde de Juazeiro, Bahia.

## Objetivo

Organizar em um só ambiente parte das informações públicas sobre unidades de saúde, facilitando a busca por nome, bairro, endereço e categoria, além da consulta cartográfica e de referências de mobilidade.

O projeto possui finalidade acadêmica e informativa. Não substitui os canais oficiais do SUS nem confirma disponibilidade de atendimento.

## Funcionalidades

- Busca e filtros por categoria (UBS, UPA e Hospital).
- Cadastro local de estabelecimentos em `unidades.json` e perguntas frequentes em `faq.json`.
- Mapa interativo com Leaflet e OpenStreetMap, com indicação do funcionamento estimado nos marcadores.
- Consulta de pontos de ônibus próximos por meio da Overpass API, limitada à área administrativa de Juazeiro.
- Estimativas de rotas e geocodificação com serviços HeiGIT/OpenRouteService e Pelias, conforme configuração.
- Formulário separado para avaliar a experiência com a unidade de saúde e com a plataforma, com encaminhamento via Google Apps Script para Google Sheets.

## Tecnologias utilizadas

Python, Streamlit, HTML, CSS, JavaScript, JSON, Leaflet, OpenStreetMap, Overpass API, HeiGIT/OpenRouteService, Pelias, Google Apps Script e Google Sheets.

## Estrutura do projeto

```text
saude-em-foco/
├── app.py
├── unidades.json
├── faq.json
├── interface.css
├── requirements.txt
├── README.md
└── static/
    └── hero.webp
```

## Como executar o projeto localmente

### 1. Pré-requisitos

- Python instalado no computador.
- Git instalado (ou possibilidade de baixar o projeto diretamente pelo GitHub).
- Conexão com a internet.

### 2. Baixar o projeto

Clone o repositório:

```bash
git clone https://github.com/mariannahaikajournalism-byte/saude-em-foco.git
```

Entre na pasta:

```bash
cd saude-em-foco
```

### 3. Criar um ambiente virtual

Windows:

```bash
py -m venv .venv
```

Ative o ambiente:

```bash
.venv\Scripts\activate
```

Linux ou macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Instalar as dependências

Com o ambiente virtual ativado, execute:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Executar a aplicação

Inicie o Streamlit:

```bash
streamlit run app.py
```

Após a inicialização, a aplicação poderá ser acessada pelo navegador, normalmente no endereço:

`http://localhost:8501`

Para encerrar a execução, pressione `Ctrl + C` no terminal.

## Configurações privadas

Chaves e tokens utilizados pelas integrações devem ser protegidos e não devem ser publicados no GitHub.

A integração de avaliação utiliza a seção `feedback`. Os recursos de roteamento e outros serviços externos podem depender da chave configurada para o serviço correspondente.

A ausência de determinadas credenciais pode limitar recursos específicos da aplicação.

## Dados, georreferenciamento e fontes

Os estabelecimentos e seus atributos são mantidos em `unidades.json`. O cadastro contém referências públicas e identificadores CNES quando disponíveis.

A cartografia e os pontos de ônibus são obtidos do OpenStreetMap. A consulta de elementos de transporte utiliza a Overpass API e restringe os resultados à área administrativa identificada como Juazeiro.

O estado de validação de cada coordenada é registrado individualmente no arquivo JSON. Coordenadas provisórias não devem ser apresentadas como validadas.

A USF Antônio Guilhermino permanece com coordenada de referência do CNES aguardando validação visual. USF CAJ e USF Campos permanecem sem coordenadas cadastradas.

As distâncias entre uma unidade de saúde e um ponto de ônibus são aproximações em linha reta, não distâncias de caminhada. A existência de uma parada próxima não comprova qual linha de ônibus passa pelo local.

Os horários exibidos são estimativas interpretadas a partir do cadastro, não dados em tempo real. As informações podem mudar e devem ser confirmadas diretamente com as unidades e os operadores responsáveis.

## Avaliações e integração com planilha

O formulário envia campos legados para manter compatibilidade básica com a integração existente e também encaminha novos campos separados:

- `unidade_saude`
- `atendimento_unidade`
- `acesso_unidade`
- `estrutura_unidade`
- `sugestao_unidade`
- `experiencia_plataforma`
- `sugestao_plataforma`

Para que todos os novos campos sejam registrados, o Google Apps Script e a planilha vinculada precisam estar configurados para receber essas colunas.

O código do Apps Script não faz parte deste repositório e não foi alterado neste projeto.

## Limitações

- O catálogo é uma seleção de estabelecimentos, não necessariamente a rede municipal completa.
- A qualidade e a atualidade dos dados dependem das fontes consultadas.
- A cobertura do OpenStreetMap pode ser incompleta.
- Rotas e tempos são estimativas e dependem da disponibilidade dos serviços externos.
- O projeto não realiza agendamento, regulação, diagnóstico ou confirmação de vagas.

## Aplicação publicada

[Saúde em Foco — Acessar aplicação no Streamlit](https://saude-em-foco-3pgmcospnjubktp5eshysd.streamlit.app/)

## Créditos

Projeto acadêmico desenvolvido no curso de Jornalismo em Multimeios da Universidade do Estado da Bahia (UNEB), campus Juazeiro (BA), 2026.