# Motion Studio — guia da equipe

Um sistema que trabalha junto com o Claude para levar um episódio do material bruto até o After
Effects: decupagem com troca de câmera, storyboard das animações e os projetos do After já
diagramados e animados, sempre no estilo de cada cliente.

Você conversa com o Claude em português; ele roda as ferramentas no seu PC e mostra o resultado
para você aprovar. Nada é publicado nem enviado sem você pedir.

---

## 1. Instalar num PC (uma vez)

Requisitos: Windows 10/11, Adobe After Effects e Premiere, conta no Claude com acesso ao Claude Code.
Placa NVIDIA é recomendada (sem ela a transcrição roda na CPU, bem mais devagar). Lista completa no [README](README.md#requisitos).

1. Instale o **app do Claude** (claude.ai/download) e entre com a sua conta.
2. Baixe o repositório:
   ```
   git clone https://github.com/MayconDouglasg/Studio-IOx.git C:\motion-studio
   ```
   (sem Git ainda? baixe em git-scm.com, ou baixe o .zip pela página do GitHub)
3. Abra o PowerShell na pasta e rode o instalador:
   ```
   cd C:\motion-studio
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```
   Ele instala Python, Node, Git e ffmpeg se faltarem, os pacotes, liga as skills e termina com um
   diagnóstico. Todas as linhas devem dizer `[OK]`.
4. No app do Claude: aba **Code** > abrir a pasta `C:\motion-studio`. Pronto.

Atualizar quando alguém melhorar o sistema: `git pull` na pasta (e `install.ps1` de novo se o
`requirements.txt` mudou).

---

## 2. Clientes

Cada cliente é uma **pasta própria**, fora do sistema (de preferência no drive partilhado da equipe,
para que todos usem o mesmo estilo e o mesmo registro de feedback):

```
<pasta do cliente>/
  STYLE.md        o estilo do cliente (o Claude lê antes de qualquer trabalho)
  client.json     cores, fontes, câmeras, números de corte e de animação
  brand/          fontes e logos
  refs/canal      vídeos do canal  ·  refs/inspiracao  inspirações
  projects/       um episódio por pasta
```

- **Cliente que já existe**: diga ao Claude
  *"registra o cliente nome-do-cliente, a pasta é D:\...\Nome do Cliente\motion"*
  (ou rode `python tools\studio.py add-client nome-do-cliente "<pasta>"`).
- **Cliente novo**: diga *"vamos configurar um cliente novo"*. O Claude pergunta o nome, onde guardar
  a pasta e quais câmeras ele usa, cria tudo e diz o que você precisa colocar (fontes, logos,
  3 a 6 vídeos do canal, inspirações). Depois ele estuda os vídeos e escreve o `STYLE.md`.
- **Vídeos de referência por link**: em vez de copiar os arquivos, passe os links ao Claude
  (*"baixa estes 5 vídeos do canal do nome-do-cliente: <links>"*) ou rode
  `python tools\studio.py refs nome-do-cliente <link> <link> ...` (`--inspiracao` para inspirações;
  `--playlist --max 5` para os 5 mais novos de um canal). Baixa em mp4 até 1080p, com o título como nome,
  e pula o que já está na pasta. Só vídeos do **próprio canal do cliente** ou referências que **o cliente
  mandou**, e só para estudo do estilo: nunca baixe vídeo de terceiros para usar dentro de um vídeo
  (imagens de apoio vêm só das fontes licenciadas da skill imagens-apoio).
- **Fontes**: instale as fontes de cada cliente em cada PC (botão direito > *Instalar para todos os
  usuários*). O After só enxerga fontes instaladas.

---

## 3. O fluxo de um episódio

Diga ao Claude em que etapa está; cada etapa tem uma skill (você pode chamar pelo nome com `/`).

| Etapa | O que você diz | O que você recebe |
|---|---|---|
| Começar | *"episódio novo do nome-do-cliente: ep07-nome"* | a pasta do episódio |
| **/decupagem** | *"decupa o bruto que está em D:\...\VIDEOS"* | XML para o Premiere: câmeras sincronizadas, silêncios e takes repetidos fora, bastidor fora, troca de câmera feita, trechos duvidosos marcados `REVER` |
| Edição | você edita no Premiere e exporta o XML final + um MP4 leve | — |
| **/imagens-apoio** | *"imagens de apoio para o V1: o XML final é ... e o roteiro está em MATERIAL"* | pasta `APOIO/<vídeo>/` com os clipes numerados pelo momento, `CREDITOS.md` e uma cópia do XML com uma marca por momento (você arrasta os clipes para as marcas) |
| **/storyboard** | *"o XML final e o vídeo estão aqui, vamos para as animações"* | página de storyboard para aprovar cena a cena (ok / ajustar / remover + nota) e depois a lista de assets para baixar |
| **/after-handoff** | *"storyboard aprovado, gera o After"* | `01_layout.aep` (tudo diagramado, sem keyframes) e `02_animado.aep` (câmera 3D, profundidade, texto animado) |
| **/sfx** | *"abre a revisão de SFX"* e depois *"faz o plano de SFX do <episódio>, o XML é ..."* | página para aprovar os sons de ouvido; `work/sfx_plan.json` e uma cópia do XML com os efeitos em faixas de áudio novas |
| **/estudo-final** | *"o vídeo foi finalizado: o Premiere é <projeto>, sequência <nome>; o After é <arquivo>"* | `final_study/ANALISE.md`: o que o editor usou, mudou e acrescentou; as lições ficam gravadas no estilo do cliente |

### Decupagem — o que ela faz
- Sincroniza as câmeras e a gravação de tela pelo áudio e transcreve no seu PC.
- Tira silêncios, respirações, takes repetidos (fica o último completo), claquetes e falas de
  bastidor ("corta", "câmera 1", "vou repetir").
- O Claude lê a transcrição do corte e tira o que as regras não pegam: falsos inícios, recomeços,
  segmentos refeitos, falas de espera. **Nada se perde**: tudo o que sai vai para a sequência
  `02_TAKES_DESCARTADOS`.
- Troca de câmera como o editor faz: frontal na maior parte, inserções curtas da lateral, nunca
  durante a tela. No Premiere, a inserção é um pedaço da frontal **desativado** (cor lavanda):
  reative-o para desfazer a troca.
- Num episódio longo de teste, o corte automático chegou a 11,5 min contra 11,3 min do corte final do editor.
- **Alucinações do Whisper filtradas.** Em trechos sem fala (teclado, mouse, ruído) o Whisper inventa frases-feitas
  ("Obrigado por assistir", "Acesse o site…", "Legenda por…") ou repete a lista de vocabulário do `episode.json`.
  A transcrição agora mede a voz real de cada trecho: o que não tem voz sai (fica listado em
  `work/transcript/sN.json`, campo `hallucinations`), e uma frase-feita dita mesmo com voz fica marcada para confirmar
  (`[FRASE-FEITA?]`). Num episódio longo saíram 161 frases inventadas sem perder nenhuma palavra do corte validado.
- **Verificar no Premiere (opcional).** Depois de você importar o XML à mão (Arquivo > Importar), pode pedir
  *"verifica no Premiere"*: o Claude usa o MCP `premiere` só para ler (sequências, buracos, número de clipes,
  duração contra o `report.md`, marcadores `REVER`, e um XML exportado pelo próprio Premiere para comparar).
  Não peça para ele importar o XML pelo MCP: abre um diálogo que trava o Premiere. A lista das ferramentas
  está na skill `decupagem`.

### Imagens de apoio — chaves das fontes
O Claude lê o roteiro e o corte final, escolhe os momentos que pedem imagem (coisas citadas, produtos, lugares,
ações, números) e busca nesta ordem: **pasta do cliente** (`APOIO`, `acervo` ou `broll` dentro da pasta do
cliente, ou a que você indicar), **Magnific**, **Pexels**, **Pixabay** e, por último, **geração por IA**.
Fonte sem chave é pulada sem erro. Cada PC precisa das próprias chaves (nunca vão para o git):

| Fonte | Como pegar a chave | Variável |
|---|---|---|
| Magnific (antigo Freepik) | entre na sua conta em magnific.com > painel de desenvolvedor / API > *Create API key*. A API de stock baixa até ~100 itens por dia nos planos Premium/Plus/Pro | `MAGNIFIC_API_KEY` |
| Pexels | crie uma conta grátis em pexels.com > *Image & Video API* (pexels.com/api) > *Your API Key* | `PEXELS_API_KEY` |
| Pixabay | crie uma conta grátis em pixabay.com > *API* (pixabay.com/api/docs) — a chave aparece na própria página, logado | `PIXABAY_API_KEY` |

Para gravar: rode `python tools\apoio.py chaves`, que cria o arquivo `C:\Users\<seu usuário>\.motion-studio\chaves.json`
(fica só neste PC, fora do git). Abra, cole cada chave entre as aspas e salve. Também valem as variáveis de
ambiente (`setx PEXELS_API_KEY "sua-chave"` no PowerShell) ou `"keys"` no `studio.config.json`.
Nunca cole a chave na conversa com o Claude: só no arquivo.
Confira com `python tools\apoio.py fontes` ou com o `doctor`. Os créditos de cada clipe (fonte, autor,
licença, link) ficam no `CREDITOS.md` da pasta; o Magnific conta cada download, e o sistema para no limite do dia.

### After Effects — como mexer sem brigar com keyframes
- Mover ou escalar um bloco: use a camada nula `POS · …` (não tem keyframes).
- Animação do texto: *Texto > Animadores* (`ENTRADA` / `SAÍDA`); câmera: camada `CÂMERA 3D`.
- Trocar um ícone: Alt + arrastar o novo arquivo sobre a camada `ícone animado (substituível)`.
- Se aparecer o aviso "Solucionar fontes" durante a montagem, o sistema fecha sozinho.

---

### Caminho do código — motion pronto em MP4 (sem After)
No storyboard, cada cena ganha um caminho: **after** (os dois .aep para o editor), **código** (HTML que vira MP4,
ou ProRes 4444 com transparência para pôr por cima do apresentador) ou **ia** (só fundo ou objeto realista, nunca
texto). O padrão de cada cliente fica no `client.json` (`caminho_padrao`), junto com `modo_apresentador`
(sobre / bolha / tela_dividida / so_voz), `ritmo` (calmo / dinamico) e `grade` (margem, alinhamento, hierarquia).
Passos do caminho do código (o Claude roda):
1. `python tools/codigo.py novo <pasta> --client <slug>` — copia o modelo "páginas + rota" com as cores e fontes do cliente.
2. `python tools/codigo.py palavras <pasta> <voz.wav>` — tempo de cada palavra; tudo na tela chega na palavra falada.
3. `node render.mjs --project <pasta> --timeline`, `python tools/codigo.py trilha <pasta>`, `python tools/codigo.py mix <pasta>`.
4. `node render.mjs --project <pasta> --contact` (folha de contato, conferir) e depois o render final (`--alpha` para ProRes 4444).
5. Motion por cima do apresentador: `codigo.py mix <pasta> --janelas 4.6-21.2,...` (trilha só enquanto o motion aparece) e
   `codigo.py compor <pasta> <vídeo do apresentador> --janelas ... --out <arquivo novo>` para a prévia montada.
Fontes: ponha os arquivos em `brand/fonts` do cliente (ou `fonts.<papel>.file` no client.json); sem eles o vídeo usa a fonte
instalada no PC e muda de um PC para outro.

### Sons dos motions (SFX da biblioteca)
O Claude escolhe os efeitos sonoros de cada movimento do motion (entrada de texto, pop, viagem de câmera, transição/whip,
glitch, clique, digitação, notificação, check, risco de marcador, papel, impacto em número, riser antes de uma revelação,
saída suave no fim, vinheta) **só entre os sons que você aprovou de ouvido**.
1. **Uma vez por PC**: diga onde está a biblioteca: `python tools\sfx.py biblioteca "D:\...\SFX_LIBRARY"` (fica no
   `studio.config.json` deste PC). Depois `python tools\sfx.py index`: mede cada som que pode servir a um movimento (duração,
   ataque, cauda, brilho, graves, volume) em poucos minutos. Rode de novo quando entrar som novo na biblioteca.
2. **Aprovar de ouvido**: `python tools\sfx.py revisar` abre `http://127.0.0.1:8767` com 6 a 10 sons por movimento. Toque,
   marque **ok** ou **não**. Na mesma página, diga se cada pack pode ir em vídeo de cliente (licença): pack com **não** nunca
   entra; com **?** entra com aviso. As marcas ficam em `_sistema\dados\sfx_motion.json`, dentro da biblioteca (valem para
   todos os clientes). Os sons, o catálogo e os seus favoritos nunca são alterados; favoritos e o que o editor usou sobem na lista.
3. **Plano do episódio**: `python tools\sfx.py plan <episódio> --xml "<XML do corte>"` grava `work\sfx_plan.json` e uma cópia
   nova do XML (`premiere\<nome>_sfx.xml`) com cada efeito na palavra, o mesmo som sempre na mesma faixa e o volume medido (a
   soma dos picos fica abaixo de -1 dBTP). Movimento sem som aprovado fica mudo. `--previa` preenche com os candidatos só para
   você ouvir no contexto (o arquivo diz PREVIA: não entregue). `--musica <arquivo>` põe uma trilha licenciada 20 dB abaixo da
   voz, terminando 2 s depois do último motion.
4. **Episódio finalizado**: depois do `/estudo-final`, `python tools\sfx.py aprender <episódio>` vê quais sons da biblioteca o
   editor usou e em qual movimento; eles sobem na lista (continuam precisando do seu ok).
Ficam fora por padrão: `80_Musica` (parte tem copyright e gera reivindicação no YouTube), memes/famosos, `98_Revisar`,
overlays/LUTs, terror e armas. No `client.json` do cliente, `sfx.intensidade` (auto / subtil / medio / forte; cliente que pede
"simples, nunca exagerado" = subtil), `sfx.excluir`, `sfx.incluir` (ex.: `"horror"`) e `sfx.ganho_db`. Colocar os sons direto na
timeline do Premiere virá depois; por enquanto você importa a cópia do XML.

## O Arsenal: tudo o que o sistema sabe fazer
Dois cliques no **`Arsenal.bat`** (na pasta do motion-studio) abrem o painel no navegador. Ele tem duas abas:
- **Cliente** — o trabalho deste PC. No topo você escolhe o cliente e o episódio: a página mostra em que
  etapa ele está, o **próximo passo** com o pedido já preenchido para colar numa conversa nova e os arquivos
  do episódio para abrir. Embaixo, os clientes com o estado do estilo, o doctor e os formulários para cadastrar
  clientes e criar episódios (sempre pedindo confirmação).
- **Geral** — o que vale para qualquer cliente: o caminho do episódio, as receitas, todas as skills por área
  (o que entra, o que sai, o pedido com os campos em aberto) e as ferramentas.

O painel abre em `http://127.0.0.1:8766` (a porta 8765 é do navegador da Biblioteca SFX, que pode ficar aberto ao mesmo tempo).
Sem o painel, `python tools\studio.py arsenal` gera a mesma página só para consulta.
Decupagem, storyboard e After continuam no Claude: copie o pedido.

**Regra:** toda skill ou agente novo ganha o bloco `arsenal:` no cabeçalho (skills externas: uma entrada
em `arsenal/extras.json`). Sem isso ela aparece na página como "sem ficha".

---

## 4. Gastar menos do limite do Claude
O custo vem de o Claude reler a conversa inteira a cada passo; quanto mais longa a conversa, mais
caro cada passo. Num episódio longo, só essa releitura foi quase metade do gasto.
- **Uma conversa nova para cada etapa** (decupagem, storyboard, After). Terminou e aprovou uma
  etapa? Abra uma conversa nova para a próxima: as skills e os arquivos guardam tudo.
- **Storyboard: todas as notas de uma vez.** Marque todas as cenas e escreva tudo antes de pedir a
  nova versão. Cada rodada a mais custa; com a identidade aprovada, 1 ou 2 rodadas bastam.
- **Reels em lote:** vários vídeos curtos do mesmo cliente na mesma conversa dividem o custo fixo.
- **Modelo:** Opus para as etapas mecânicas; o modelo mais forte só no storyboard, se quiser.
- **Melhorar o sistema é outra conversa**, nunca no meio de um episódio.
- Referência medida: um vídeo longo fica em torno de 20% do limite de 5 horas do plano Pro; um reel,
  uns 14% (uns 7% em lote).

## 5. Regras da equipe
- **Aprovou ou reprovou algo? Diga ao Claude.** Ele registra no `STYLE.md` do cliente e muda a
  regra, e no fim de cada etapa aprovada pergunta o que mais confirmar. É assim que o sistema aprende.
- **O que é de um cliente fica na pasta dele** (`STYLE.md`, `client.json`). O GitHub só recebe regras que
  servem para qualquer cliente, escritas sem nome de cliente, episódio, cores ou fontes.
- O sistema nunca sobrescreve uma entrega (um `.aep`, um XML que você já importou): testes vão para
  outra pasta ou outro nome.
- Os vídeos e projetos dos clientes **nunca** vão para o GitHub; só o sistema.
- Melhorias no sistema (ferramentas, skills, regras gerais): faça num ramo, abra um pull request e
  peça revisão antes de juntar, para não quebrar o trabalho dos colegas.

---

## 6. Problemas comuns
| Sintoma | O que fazer |
|---|---|
| `python tools\studio.py doctor` mostra `[!!]` | siga a dica da própria linha |
| GPU `[--]` nenhuma (com placa NVIDIA) | atualize o driver NVIDIA e rode `install.ps1` de novo; sem placa, a transcrição usa a CPU |
| Mudei uma ferramenta ou skill | `python tools\selfcheck.py` antes do commit (o GitHub roda o mesmo) |
| After não encontrado | `python tools\studio.py set-after "C:\...\Support Files\AfterFX.exe"` |
| Texto no After com fonte errada | a fonte do cliente não está instalada neste PC |
| O After não reage ao script | deixe o After aberto com um projeto; feche avisos pendentes |
| Cliente "não encontrado" | registe a pasta: `python tools\studio.py add-client <slug> "<pasta>"` |

---

## 7. Zero defeitos antes de mostrar (`tools/check.py`)
Antes de qualquer revisão de gosto (folha de contato, nota 8+), o Claude roda um portão que só **conta defeitos
medíveis**; ele nunca corrige nada. Só o que dá **0 defeitos** chega até você. Um defeito que o Claude decide manter
aparece no LEIA-ME com o tempo exato e marcado `REVER`.

| Comando | O que mede |
|---|---|
| `python tools\check.py decup <episódio>` | o XML da decupagem: buracos e sobreposições, clipes de 1–3 frames, ids repetidos, trechos sem vídeo, áudio dobrado, tamanho e fps da sequência e tela ligada/desligada como o `client.json` pede; cortes que caem com a voz ainda soando; e retranscreve o áudio que ficou para achar **a mesma frase duas vezes** (takes que sobraram ou que a transcrição juntou) e **palavras cortadas** na emenda |
| `python tools\check.py render <arquivo>` | codec, tamanho e fps contra a entrega esperada, preto depois de corte seco, imagem congelada, frames-relâmpago, loudness (alvo -14 LUFS), pico verdadeiro acima de -1 dBTP e áudio estourado |
| `python tools\check.py frames <pasta de frames ou vídeo>` | nos frames do motion: texto fora da área segura, contraste do texto com o fundo (WCAG) e áreas lisas em cores que não estão no `client.json` |

Cada um escreve um resumo curto e `<episódio>\work\check\check_<etapa>.json` com a lista completa (com `--out <pasta>`
tudo vai para essa pasta e o episódio só é lido). Os limites ficam no bloco `qa` do `client.json` do cliente
(loudness, entrega, área segura, contraste). Um corte com a voz ainda soando só conta como defeito quando a
retranscrição também ouve uma palavra fraca ali; emendas justas em fala corrida passam. Teste sempre numa cópia,
nunca num arquivo já entregue.
