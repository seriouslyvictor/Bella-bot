# Base de Conhecimento — Report Generator 9000 (`report_generator9000`)

O **Report Generator 9000** é uma aplicação web voltada para a geração automatizada do **RELATÓRIO TÉCNICO FINAL** das consultorias do **SEBRAETEC**. O relatório é um documento contratual que o representante legal do cliente assina, portanto cada afirmação contida nele deve ser rastreável a fatos observados ou entradas explicitamente fornecidas.

---

## 1. Visão Geral e Arquitetura

- **Objetivo**: Gerar relatórios técnicos finais sem necessidade de interação manual durante o pipeline: o usuário envia a planilha de controle (.xlsx), seleciona o atendimento/demanda, revisa as páginas do PDF certificado gerado e faz o download dos arquivos finais `.docx` e `.pdf`.
- **Uso de IA**: O modelo Gemini é utilizado estritamente para os campos de prosa permitidos (como síntese do briefing). Capturas de tela, substituições de tokens, rastreamento de proveniência e validações contratuais são estritamente determinísticos.
- **Renderização**:
  - Word Masters (`MASTER.docx` para WebSite e `MASTER-LOJA-VIRTUAL.docx` para Loja Virtual) contendo layout, estilos e tokens.
  - O Chromium (via **Playwright**) executa a navegação, captura de tela de páginas e elementos visuais.
  - O **LibreOffice headless** converte o documento Word montado em um PDF certificado e gera as imagens de prévia página a página.

---

## 2. Conceitos Fundamentais e Vocabulário Canônico

- **Demanda**: Identificador do atendimento emitido pelo SEBRAETEC (ex: `013292/2026`). Consta na capa do relatório.
- **Pasta**: Número da pasta que identifica o atendimento (ex: `115-2026`). Dá nome ao diretório de saída no volume `/app/data` e aos arquivos gerados. Um atendimento pode ter múltiplos Runs; uma nova execução sobrescreve os artefatos anteriores da mesma pasta.
- **Tema**: Tipo de serviço contratado, obtido exatamente da planilha de controle:
  1. `Inserção digital - Desenvolvimento de WebSite` (utiliza `MASTER.docx`).
  2. `Implantação de Loja Virtual` (utiliza `MASTER-LOJA-VIRTUAL.docx`).
- **Unsupported Row**: Linha da planilha cujo Tema ainda não possui Master aprovado. Fica visível na listagem de atendimentos porém desabilitada para seleção; nunca é ignorada em silêncio.
- **Especialista**: Consultor responsável pelo atendimento, cujo nome consta na capa do relatório.
- **Run & Stages**: Cada geração passa por uma sequência fixa e ordenada de 9 etapas (Stages). Uma execução que não complete todas as 9 etapas em ordem é rejeitada.
- **Tokens e Slots**:
  - **Token**: Marcador de texto no Master no formato `{{NOME}}`, substituído por dados do atendimento ou prosa aprovada.
  - **Slot**: Posição de dimensões fixas no Master destinada a imagens (screenshots ou paleta).
- **Block**: Parágrafo de título vinculado ao parágrafo da imagem capturada (não possui parágrafos vazios intermediários para evitar quebra de página indevida).
- **Lista de Páginas**:
  - **Página Principal**: Páginas acessíveis pelo menu principal (exibidas como `SEÇÃO <LABEL>`, exceto a página inicial que é `PÁGINA HOME`).
  - **Área Legal**: Páginas de políticas acessíveis pelo rodapé (ex: Política de Privacidade, Termos de Uso).
  - **Elemento Transversal**: Cabeçalho e Rodapé, capturados em separado.
- **Origem de Captura (Capture Origin)**: URL pública navegada e capturada pelo Playwright (frequentemente domínio temporário de preview, ex: Hostinger).
- **Domínio Publicado**: Domínio final oficial do cliente e base para acesso ao `/wp-admin`. Fornecido como entrada gated; nunca deduzido da URL de preview.
- **Gated Drop Folder**: Diretório (`.data/gated` ou `/app/data/gated`) onde o consultor insere evidências privadas ou dados sob autenticação antes da execução.
- **Placeholders e Pendências**:
  - `GATED`: Conteúdo protegido por login/senha que não pôde ser capturado automaticamente; exige inserção manual pelo consultor. Não é considerado defeito de sistema.
  - `TOOL_BLOCKED`: Falha técnica da automação ao tentar capturar página pública. Representa um defeito a ser investigado.
  - `UNDECLARED`: O site não declara paleta de cores legível por máquina e tem menos de duas cores identificáveis; esperado em minoria de sites.
  - `REVIEW`: Conteúdo derivado gerado que requer validação do consultor.
  - **Pendência**: Item pendente registrado em `PENDENCIAS.md` e `pendencias.json`. Um relatório com pendências é gerado como rascunho (draft) e nunca marcado como pronto para entrega.

---

## 3. Fluxo de Trabalho (Pipeline)

1. **Upload da Planilha**: O usuário faz o upload da planilha de controle `.xlsx`. O sistema valida as colunas obrigatórias e lista os atendimentos.
2. **Seleção do Atendimento**: O usuário seleciona a Pasta/Demanda suportada.
3. **Execução das 9 Etapas**:
   - Leitura e validação dos dados da linha da planilha.
   - Verificação de Gated Inputs na pasta drop folder.
   - Navegação e rastreamento de links via Playwright.
   - Captura de telas da Página Home, Seções, Áreas Legais, Cabeçalho e Rodapé.
   - Derivação e auditoria da paleta de cores.
   - Clonagem do Master (.docx) correspondente ao Tema.
   - Substituição estrita de tokens e preenchimento dos slots com imagens e placeholders.
   - Conversão headless via LibreOffice para `.pdf` certificado e extração de páginas de visualização.
   - Geração do manifesto de proveniência e relatório de pendências.
4. **Revisão e Download**: Visualização das páginas no navegador e download dos arquivos `.docx` e `.pdf`.

---

## 4. Problemas Comuns e Solução de Dúvidas (Troubleshooting)

- **Erro de formatação ou colunas ausentes na planilha**: A planilha deve manter o cabeçalho e colunas padrão do SEBRAETEC (Demanda, Pasta, Tema, Razão Social, CNPJ, Especialista, etc.). Linhas sem Demanda ou com Tema não suportado não podem ser geradas.
- **Timeout na captura de tela do site**: Ocorre quando o site do cliente está fora do ar, instável ou com bloqueios (Cloudflare/CAPTCHA). Isso gera um placeholder `TOOL_BLOCKED` para as páginas afetadas.
- **Pendência de Loja Virtual (carrinho/checkout)**: Para o tema `Implantação de Loja Virtual`, se a loja ainda não possuir fluxo de checkout ou carrinho publicado para captura pública, o sistema gera o relatório como rascunho apontando a pendência correspondente.
- **Cores não identificadas no site**: Se o site não declara cores via CSS/tokens e não há contraste suficiente, o relatório aplica o placeholder `UNDECLARED`, o que não é um erro de software, bastando o consultor complementar a informação se necessário.
- **Relatório travado ou com erro no PDF**: Verificar se o LibreOffice headless e as dependências do Chromium estão ativos no contêiner.

---

## 5. Execução em Contêiner e Portas

- **Execução em Produção**:
  ```bash
  docker run --rm --publish 8000:8000 --env-file .env -v /caminho/dados:/app/data report-generator9000
  ```
  - Interface e API disponíveis em `http://localhost:8000`.
  - O volume `/app/data` armazena os drop folders e os relatórios gerados (com retenção padrão de 7 dias).
- **Ambiente de Desenvolvimento**:
  ```bash
  docker compose -f compose.dev.yaml up --build
  ```
  - Frontend (Vite): `http://localhost:5173` (encaminha chamadas `/api` para a porta 8000).
  - Backend (FastAPI): `http://localhost:8000`.
  - Dados locais e Gated Drop Folders ficam mapeados em `.data/`.
