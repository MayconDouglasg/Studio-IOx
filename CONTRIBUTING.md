# Contribuir com o motion-studio

Obrigado por querer melhorar o sistema. Três regras valem mais que todas as outras:

1. **Nada de cliente no repositório.** Nome, episódio, cores, fontes, números medidos ou gosto de um cliente vivem
   na pasta dele (`STYLE.md`, `client.json`), nunca em skills, ferramentas, `CLAUDE.md`, `GUIA.md` ou
   `clients/_template`. Uma lição de um cliente vira **regra geral** antes de entrar numa skill.
2. **Um ramo por melhoria, nunca no meio de um episódio.** Desenvolvimento acontece numa conversa própria e num
   ramo próprio (`git checkout -b melhoria/<assunto>`), com pull request e revisão antes de juntar.
3. **Nunca sobrescrever uma entrega.** Teste mudanças com `--out` / `--name` numa pasta de teste.

## Antes do pull request
```powershell
python tools/selfcheck.py
```
Confere: Python compila, `.mjs` passa no `node --check`, todo JSON abre, toda skill tem `name`, `description` e o
bloco `arsenal:` completo, nenhum dado de cliente ou mídia versionado e nenhum nome de cliente deste PC num arquivo
do repositório. O GitHub Actions roda o mesmo em cada pull request.

## Skills
- Uma skill por etapa em `.claude/skills/<nome>/SKILL.md`. A `description` é o que faz o Claude escolher a skill:
  diga o que ela faz e **quando** usar, com as palavras que o usuário diria.
- Toda skill ou agente novo ganha o bloco `arsenal:` no cabeçalho (formato em `tools/arsenal.py`). Uma skill
  externa ganha uma entrada em `arsenal/extras.json`.
- Mantenha o `SKILL.md` curto: os passos e as regras duras. Histórico de medições e lições longas vão para um
  arquivo ao lado (`references/…md`) que a skill manda ler só quando precisa — cada linha do `SKILL.md` é relida
  em toda chamada da etapa.
- Toda regra nova diz de onde veio (o que falhou, o que foi medido) — sem número inventado.

## Ferramentas
- Trabalho pesado roda local (ffmpeg, numpy, Whisper); o Claude lê só resumos curtos. Uma ferramenta nova imprime
  uma linha de resumo e grava os detalhes em arquivo.
- Sem chave de API no código: variáveis de ambiente, `~/.motion-studio/chaves.json` ou `studio.config.json`.
- Servidores locais escutam só em `127.0.0.1`.
- Render: cada filme é função pura do tempo (`window.seek(t)`), sem `Math.random`, sem transições CSS (ver `CLAUDE.md`).

## Skills de terceiros
Remotion e HyperFrames não são copiados para o repositório: as versões ficam fixadas em `skills-lock.json` e o
`install.ps1` as restaura (`npx skills experimental_install`). Para atualizar: `npx skills update` e commit do lock.
