# Roadmap — revisão de 2026-11

Resultado de uma revisão completa do repositório (código, skills, instalação, preparação para abrir ao público).
Ordem = valor ÷ custo. Nada aqui exige serviço pago novo.

## Corrigido nesta revisão
| Falha | O que mudou |
|---|---|
| Transcrição só funcionava com placa NVIDIA (`decupagem`, `imagens-apoio` quebravam sem CUDA) e `_cuda_dlls` quebrava fora do Windows | `decup_stage2.whisper_model()`: GPU quando há, CPU quando não; `MOTION_STUDIO_WHISPER_DEVICE=cpu` força; o `doctor` mostra GPU como opcional |
| 504 arquivos de skills de terceiros versionados (`.agents/skills`), as do Remotion sem licença de redistribuição, e `media-use` já divergia do `skills-lock.json` | `.agents/` fora do git; o `install.ps1` restaura as versões fixadas (`npx skills experimental_install`) |
| README de 10 linhas, desatualizado (citava 5 das 8 skills), sem requisitos | README completo: o que faz, requisitos por etapa, instalação automática e manual, custos, estrutura, limitações |
| Nenhuma checagem automática do repositório | `tools/selfcheck.py` + GitHub Actions: sintaxe, JSON, front matter das skills, bloco `arsenal:`, dado de cliente versionado, nome de cliente deste PC em arquivo do repositório |
| `package.json` com campos padrão do `npm init` (`main`, licença ISC, script de teste que falha) | `private`, descrição e scripts `doctor` / `render` / `check` |
| Fontes do repositório sem arquivo de licença | `fonts/OFL-*.txt` |
| `GUIA.md` falava em "repositório privado" e tratava a falta de GPU como erro | atualizado |
| Portão de QA objetivo (`check.py`) abandonado num ramo | terminado: `decup`, `render`, `frames`; as skills mandam rodar antes de mostrar (item 1 abaixo) |
| `decupagem`, `storyboard`, `after-handoff` com ~5–6 mil tokens cada | ~3 mil cada; histórico em `references/` de cada skill (item 2) |
| Imagens de conferência entrando na conversa principal | agente `conferir-frames` (`.claude/agents/`) olha as imagens e devolve texto (item 3) |

## Decisões tomadas para abrir
- **Licença MIT**: uso livre, inclusive comercial, mantendo o aviso de copyright.
- **Repositório público novo, nascido de um commit limpo.** O histórico antigo (com as cópias das skills do Remotion,
  que não têm licença de redistribuição) fica no repositório privado anterior, arquivado; a equipe passa a trabalhar
  no público. Dados de cliente nunca entram no repositório, então não há o que separar entre os dois.
- Os números das skills vêm de episódios reais ("um episódio longo"), sem citar cliente.

## Próximas melhorias (baratas)
### 1. Terminar o `check.py` — portão objetivo antes do gosto (ramo `claude/qa-check`, ~770 linhas prontas)
Conta defeitos mensuráveis sem IA: buracos e sobreposições no XML, cortes com a voz soando, frase repetida no áudio
mantido, codec / fps / loudness / pico do render, quadro preto ou congelado, texto fora da área segura, contraste
WCAG, cor fora da paleta. Só "0 defeitos" vai para a revisão de gosto. **Por que vale:** cada rodada de storyboard
custa ~US$ 1; pegar cor errada ou texto fora da área antes da rodada economiza rodadas.

### 2. Skills mais curtas (economia de tokens em toda chamada)
`decupagem`, `storyboard` e `after-handoff` têm ~5–6 mil tokens cada e são relidas em toda chamada da etapa.
Metade é histórico de medições e lições. Mover isso para `references/licoes.md` (lido só quando a skill manda)
deixa cada uma em ~2,5–3 mil. Num episódio de ~150 chamadas, ~3 mil tokens a menos por chamada é ~450 mil tokens
de cache a menos por etapa.

### 3. Subagentes para conferir imagens (`.claude/agents/`)
Folhas de contato e frames do After ficam no contexto de todas as chamadas seguintes (CLAUDE.md, regra 5).
Um agente `conferir-frames` (modelo mais barato, ex. Sonnet/Haiku) recebe a pasta de frames e o checklist, olha as
imagens no **próprio** contexto e devolve só "S04: texto fora da área a 2,3 s". A conversa principal nunca carrega
as imagens. Mesmo padrão para `ler-transcricao` na passagem semântica longa.

### 4. Hooks que garantem as regras em vez de lembrar delas (`.claude/settings.json`)
- `PreToolUse` bloqueia escrever por cima de um `.aep` / XML já entregue (hoje é só regra escrita).
- Gancho de `pre-commit` que roda `selfcheck.py` (nome de cliente nunca chega ao commit).
Determinístico, custo zero de tokens.

### 5. Legendas a partir do que já existe
`study/final_words.json` já tem o tempo de cada palavra do corte final (0 ms de erro). Exportar `.srt` e legenda
estilizada (código / ProRes com alpha) é uma ferramenta pequena e evita pagar transcrição de legenda fora.

### 6. Cortes / reels a partir do episódio longo
Ler `final_transcript.md`, propor 3–5 trechos de 30–60 s com gancho, e gerar um XML vertical 9:16 (o `decup.py xml`
já sabe tamanho de sequência e escala). Usa o mesmo lote de reels da regra 4 de economia.

### 7. Manutenção do código
- `decup_stage2.py` (1,1 mil linhas) e `sfx.py` (1,1 mil) misturam CLI, análise e escrita de XML: separar em módulos
  quando a próxima mudança grande passar por eles.
- Testes pequenos com áudio sintético para `cut` / `settle` / filtro de alucinação (rodam no CI, sem GPU).
- macOS: a parte em Python e Node é portável; falta trocar `ae_run.ps1` por `osascript` para o After.
