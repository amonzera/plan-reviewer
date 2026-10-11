# plan-review

Revisão automática de planos do Claude Code. Ao sair do plan mode, um revisor independente (contexto limpo, somente
leitura) confere o plano contra o repositório e contra o **pedido real do usuário**. Se o plano estiver alucinado,
excessivo ou incompleto, o agente corrige antes de o plano chegar a você.

| Peça | Arquivo (em `plan-review/`) | Função |
|---|---|---|
| Agente revisor | `agents/plan-reviewer.md` | Revisor somente leitura (Read, Grep, Glob), modelo `haiku`, contexto limpo |
| Hook automático | `hooks/plan_review_hook.py` | Ao sair do plan mode, roda o revisor com o pedido do usuário e devolve o relatório ao agente principal |
| Skill manual | `SKILL.md` + `scripts/check_paths.py` | `/plan-review` para revisar um plano sob demanda |
| Testes | `tests/` | Bateria offline (grátis), bateria ao vivo e simulação do laço (gastam uso do plano) |

Requisitos: Claude Code atual (testado na 2.1.295), `claude` e Python 3 no PATH. Sem dependências além da biblioteca
padrão do Python.

## 1. Instalar

```bash
git clone https://github.com/amonzera/plan-review.git
```

Os comandos abaixo supõem que você está na pasta **onde rodou o clone** (a pasta `plan-review/` do clone fica ao lado).

### Global (vale para todos os projetos)

**macOS, Linux, WSL, Git Bash**
```bash
mkdir -p ~/.claude/skills ~/.claude/agents
cp -r plan-review/plan-review ~/.claude/skills/
cp plan-review/plan-review/agents/plan-reviewer.md ~/.claude/agents/
```

**Windows (PowerShell)**
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills","$env:USERPROFILE\.claude\agents" | Out-Null
Copy-Item -Recurse plan-review\plan-review "$env:USERPROFILE\.claude\skills\"
Copy-Item plan-review\plan-review\agents\plan-reviewer.md "$env:USERPROFILE\.claude\agents\"
```

**Registrar o hook:** abra `~/.claude/settings.json` (crie com `{}` se não existir) e adicione o bloco de
`hooks/settings.snippet.json` (no Windows, `hooks/settings.windows.snippet.json`).

- Se o arquivo **já tem** a chave `"hooks"`, não duplique: acrescente o objeto `{ "matcher": "ExitPlanMode", ... }`
  dentro da lista `"PreToolUse"` existente (ou crie a lista, se ela não existir).
- Confira se o JSON continua válido: `python3 -m json.tool ~/.claude/settings.json`.

### Só em um projeto

Na raiz do projeto (troque `/caminho/do/clone` pela pasta do clone):
```bash
mkdir -p .claude/skills .claude/agents
cp -r /caminho/do/clone/plan-review .claude/skills/
cp .claude/skills/plan-review/agents/plan-reviewer.md .claude/agents/
```

Registrar o hook: este comando cria o `.claude/settings.json`; se o arquivo já existir, ele não sobrescreve, e você
acrescenta o bloco à mão (como na instalação global, mas com o `command` abaixo).
```bash
test -e .claude/settings.json && echo "settings.json já existe: acrescente o bloco à mão" || cat > .claude/settings.json <<'EOF'
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "ExitPlanMode",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/skills/plan-review/hooks/plan_review_hook.py\"",
            "timeout": 360,
            "statusMessage": "plan-review: revisando o plano (até ~1 min)..."
          }
        ]
      }
    ]
  }
}
EOF
```

Se for commitar no repositório do time, avise as pessoas: o hook executa um script e chama o `claude` a cada saída do
plan mode. Não instale nos dois níveis ao mesmo tempo, senão o hook roda duas vezes por plano.

### Reiniciar e verificar

Reinicie o Claude Code (hooks e um diretório `agents/` novo só carregam no início da sessão). Troque `~/.claude/` por
`.claude/` se instalou só no projeto.

1. **Testes offline** (grátis): `python3 ~/.claude/skills/plan-review/tests/test_hook.py`. Esperado: `FALHAS/ERROS=0`.
2. **Teste de fumaça** (dentro de um repositório; usa o `claude` real, menos de US$ 0,01):
   `python3 ~/.claude/skills/plan-review/hooks/smoke_test.py`. Esperado:
   `OK: o hook negou ExitPlanMode e devolveu a revisão.`
3. **Teste real**: abra o `claude`, entre no plan mode e peça um plano pequeno. O spinner mostra
   "plan-review: revisando o plano".

Só quer a revisão manual com `/plan-review`? Instale a skill e o agente e pule o registro do hook.

## 2. Uso no dia a dia

- **Nada a fazer.** Ao sair do plan mode, o hook revisa o plano sozinho (10 a 60 s).
- **Plano adequado:** o diálogo de aprovação aparece direto.
- **Senão**, o agente recebe o relatório (aparece na tela como "hook error": é esperado) e corrige, **corta** o excesso
  ou **pergunta a você** (a "pergunta de escopo", com a opção mais simples primeiro). São até 3 rodadas.
- **Avisos do agente** ("a revisão não rodou" ou "há achados bloqueantes em aberto"): leia e decida. O plano sempre
  chega à sua aprovação: o hook nunca aprova por você.
- **Desligar** numa sessão: `PLAN_REVIEW_DISABLE=1 claude`. **Revisar sob demanda:** `/plan-review`.

## 3. Ajustes

| O que | Como |
|---|---|
| Modelo do revisor | Linha `model:` em `agents/plan-reviewer.md` (`haiku`, `sonnet`, `opus` ou ID completo), ou `PLAN_REVIEW_MODEL`. Vale a partir da próxima revisão, sem reiniciar |
| Esforço de raciocínio | `PLAN_REVIEW_EFFORT` (padrão `high`; `low`, `medium`, `high`, `xhigh`, `max`; `off` não passa `--effort`). **O `effort:` do frontmatter é ignorado quando o agente roda como sessão principal (`claude --agent`), que é o caso do hook**: foi medido com o `effort.level` que o Claude Code entrega aos hooks (4 variantes do frontmatter, todas em `high`; `--effort low` foi respeitado). O frontmatter só vale na skill manual, que usa subagente. `CLAUDE_CODE_EFFORT_LEVEL`, se existir no ambiente, vence os dois |
| Nº de rodadas | `PLAN_REVIEW_MAX_ROUNDS` (padrão 3) |
| Tempo máximo do revisor | `PLAN_REVIEW_TIMEOUT` em segundos (padrão 300; o `timeout` do settings deve ser maior) |
| Plano novo na mesma sessão | `PLAN_REVIEW_RESET_MINUTES` (padrão 30). Um plano parecido com o anterior (mais de 55% de vocabulário em comum) continua as rodadas; um plano diferente recomeça do zero |
| Desligar temporariamente | `PLAN_REVIEW_DISABLE=1` no ambiente do terminal. `0`, `false`, `no`, `off` e vazio contam como desligado, ou seja, o hook continua **ligado** |
| Desligar de vez | Remova a entrada `ExitPlanMode` do settings |
| Outro agente revisor | `PLAN_REVIEW_AGENT=nome-do-agente` |
| Ver o que o revisor recebeu e respondeu | `PLAN_REVIEW_DEBUG_DIR=/caminho/absoluto`: grava `*.prompt.md` e `*.report.md` de cada rodada |

Variáveis de ambiente podem ser definidas no shell ou no bloco `"env"` do `settings.json`.

Atenção: a variável `CLAUDE_CODE_SUBAGENT_MODEL`, se definida, força o modelo de **todos** os subagentes
e ganha do `model` do frontmatter quando o revisor roda como subagente (skill manual). O hook não é afetado,
porque roda o revisor como sessão principal.

## 4. Atualizar e desinstalar

- Atualizar: `git pull` no clone e repita os comandos `cp` da instalação (guarde seu `model:` em `agents/plan-reviewer.md` se o mudou).
- Desinstalar: apague a pasta da skill, o agente e a entrada `ExitPlanMode` do `settings.json`.
- Estado e log ficam em `<tmp>/plan-review-<uid>/` e são podados sozinhos; podem ser apagados a qualquer momento.

## 5. Como o hook se comporta

1. `ExitPlanMode` é chamado → o hook lê o plano e o **pedido real do usuário** (mais as respostas às perguntas que o
   agente fez) no transcript da sessão, e roda `claude -p --agent plan-reviewer` com isso.
2. **ADEQUADO**: o hook não decide nada e o seu diálogo de aprovação aparece, sem volta extra do agente.
   **Qualquer outro veredito**: o hook **nega** a chamada com o relatório e instruções; o agente continua em plan
   mode, corrige e reapresenta.
3. **O que bloqueia.** Só achado `CRÍTICO` ou `ALTO` (o pedido não seria entregue, algo quebra, o plano afirma algo
   falso sobre o repo, desrespeita regra do repo ou decisão sua), excesso relevante ou alucinação. `MÉDIO` e `BAIXO`
   são opcionais. O hook ainda corrige incoerência do revisor: INCOMPLETO sem nenhum achado bloqueante vira ADEQUADO;
   ADEQUADO com achado bloqueante vira INCOMPLETO.
4. **Escopo.** O revisor declara o nível do pedido: MÍNIMO ("simples", "rápido", "mínimo"), PADRÃO ou ROBUSTO
   ("completo", "produção", "com testes"), e julga o plano contra esse nível. Sinais em conflito ("simples, mas com
   testes") valem pela instrução mais recente; sem ela, PADRÃO. Quando o plano é bem maior do que o pedido sugere, ele
   inclui uma **Pergunta de escopo**, e o agente a repassa a você (AskUserQuestion) com a opção mais simples primeiro.
5. **Rodadas que convergem.** A 1ª rodada é completa. Da 2ª em diante o revisor só *verifica*: confere se os achados
   bloqueantes foram resolvidos e se o diff criou problema novo; não procura defeitos novos no que já revisou. O texto
   que o agente recebe manda **cortar antes de acrescentar** e não ampliar o escopo. Se o plano cresce 25% ou mais
   (e pelo menos 8 linhas) desde a 1ª revisão, o hook avisa o agente.
6. **Liberações sem nova revisão**: plano inalterado desde a última revisão (só espaços diferentes também conta),
   limite de rodadas atingido, e qualquer **falha** (sem `claude` no PATH ou com o `claude` na raiz do repositório,
   timeout, erro ou limite de uso do CLI, saída que não é um relatório, erro interno do hook, plano que o Claude Code
   não enviou, plano com mais de 300 mil caracteres). O hook nunca aprova por você: só deixa de bloquear.
7. **Nada disso passa em silêncio.** No `ExitPlanMode` o Claude Code **não mostra ao usuário** texto de hook
   (`systemMessage`, `stderr` e `ask` ficam atrás do diálogo de aprovação; medido na 2.1.295). O único canal visível é o
   agente. Por isso, quando o hook libera algo que você deveria saber, ele nega **uma vez** e pede ao agente que avise
   você em uma linha: (a) a revisão não rodou (falha do revisor, erro interno do hook, plano ausente em
   `tool_input.plan`); (b) o plano segue com achados bloqueantes ainda em aberto (reenvio sem alterações ou limite de
   rodadas). No reenvio o plano passa. O texto do `deny` aparece na tela como "hook error". Ficam só no log: evento que
   não é de hook, plano vazio, e pasta de estado indisponível ou não gravável (sem estado o hook não consegue limitar o
   deny, então só libera).
8. **Plano novo na mesma sessão** recomeça as rodadas (comparação de vocabulário entre o plano novo e o anterior).
   O contador também zera sempre que o plano é entregue a você.

Por que o revisor recebe o pedido do usuário: antes, ele "deduzia o objetivo do próprio plano", e um plano que cresce
a cada rodada redefine o próprio objetivo, então o excesso ficava invisível e cada rodada pedia mais especificação.
Numa simulação do laço (agente autor + hook real, três pedidos "simples"), a versão anterior inchou o plano em 4 de 6
execuções (+75% a +162% de linhas, média de +77%; 3,3 tentativas em média; plano final revisado em 3 de 6; 143 s de
hook por plano). A atual não inchou nenhum dos 21 (de −67% a 0%, média de −13%; no máximo 2 tentativas, 1,4 em média;
44 s de hook por plano). A amostra é pequena e o autor é simulado: use `tests/loop_sim.py` para repetir a medição.

Limites conhecidos:
- Cada saída do plan mode gera uma sessão headless extra: de 10 a 55 s e menos de US$ 0,01 com `haiku` (medido: US$ 0,004
  a 0,009 por revisão). Ela não aparece no `/resume` (`--no-session-persistence`).
- O hook lê o pedido do usuário de `transcript_path`, que a documentação diz poder atrasar em relação à conversa. Se não
  der para ler, o revisor é avisado, **não deduz o objetivo do plano** e avalia só ancoragem e coerência.
- O hook lê o plano de `tool_input.plan` e, se ele faltar, do arquivo em `tool_input.planFilePath`. Se nenhum dos dois
  vier (versão do Claude Code diferente), ele avisa pelo agente e libera.
- Sem teto absoluto por sessão: um agente que reescreve o plano com menos de 55% de vocabulário em comum recomeça as
  rodadas (cada rodada custa uma revisão).
- Um revisor menor pode errar nos dois sentidos (marcar como inexistente algo que existe, ou deixar passar algo falso).
  Por isso o relatório exige evidência `arquivo:linha`: confira as evidências dos achados que importam.
- Arquivos fora do repositório podem ficar "não verificáveis" para o revisor (depende do seu modo de permissão).
- A regra de continuidade (plano parecido = mesmo plano) é uma heurística de vocabulário, calibrada em planos reais.

## 6. Solução de problemas

| Sintoma | Verifique |
|---|---|
| Nada acontece ao sair do plan mode | Hook registrado e Claude Code reiniciado? `claude --debug` mostra a execução. Log: `<tmp>/plan-review-<uid>/hook.log` (`python3 -c "import tempfile,os;print(os.path.join(tempfile.gettempdir(),'plan-review-%s'%os.getuid()))"`) |
| O agente disse que a revisão não rodou | O motivo está no texto e no log. Causas comuns: `claude` fora do PATH do ambiente que inicia o Claude Code (só entradas absolutas do PATH valem), limite de uso, agente `plan-reviewer` não instalado, versão do CLI sem `--effort` (use `PLAN_REVIEW_EFFORT=off`), versão do Claude Code que não envia `tool_input.plan` |
| "excedeu Ns" | Aumente `PLAN_REVIEW_TIMEOUT` e o `timeout` do settings, ou use um modelo mais rápido |
| Revisor ignora o `model` | `CLAUDE_CODE_SUBAGENT_MODEL` definido (skill manual), ou modelo bloqueado por `availableModels` da organização |
| Revisão rasa demais | Troque `haiku` por `sonnet` e rode de novo o teste do arquivo inexistente |
| Quero ver o que o revisor recebeu | `PLAN_REVIEW_DEBUG_DIR=/pasta` e leia `*.prompt.md` e `*.report.md` |
| O revisor parece cobrar demais (ou de menos) | Rode `tests/live_battery.py` e `tests/loop_sim.py` antes e depois de mexer em `agents/plan-reviewer.md` |
| Duas revisões seguidas | Skill manual e hook ativos juntos; a skill deve se abster quando o hook existe, mas você pode pedir explicitamente só uma |

## 7. Segurança

Hooks executam comandos com as suas permissões. O script usa só a biblioteca padrão do Python, não acessa a rede e
chama apenas o `claude` e o `check_paths.py`. Leia os dois antes de instalar. Medidas de proteção:

- **Pasta privada.** O plano, o estado e o log ficam em `<tmp>/plan-review-<uid>/` (modo 0700, recusada se for symlink
  ou de outro usuário; arquivos 0600). A cópia do plano para o revisor é apagada no fim.
- **Prompt pelo stdin, não pelo argv.** O pedido do usuário e o diff do plano não aparecem em `ps` nem em
  `/proc/<pid>/cmdline` (legíveis por outros usuários da máquina) e não passam pelo `cmd.exe` no Windows.
- **Nada do repositório revisado é executado.** O `check_paths.py` vem só da pasta do pacote (ou de
  `PLAN_REVIEW_CHECK_PATHS`) e roda em modo isolado (`python -I`). O `claude` é procurado só em entradas absolutas do
  PATH (um `.` ou entrada vazia, que apontaria para dentro do repositório, é ignorado) e é recusado se estiver na raiz
  do repositório, onde o Windows o procuraria primeiro.
- **O transcript não é confiável por inteiro.** Respostas e feedback só entram como "decisão do usuário" quando vêm de
  uma chamada real de `AskUserQuestion` ou `ExitPlanMode`; a mesma frase numa saída de Bash, arquivo ou web é ignorada.
  Só são lidos os últimos 3 MB, e só se for um arquivo regular.
- **Limites.** Entrada do hook até 8 MB, plano até 300 mil caracteres, diff omitido em planos de mais de 3000 linhas.
  Ao receber SIGTERM ou SIGINT (timeout, Esc), o hook encerra o revisor junto, sem deixá-lo órfão gastando uso; um
  SIGKILL não pode ser tratado.
- **Debug.** `PLAN_REVIEW_DEBUG_DIR` exige caminho absoluto, cria a pasta 0700, não segue symlink e não sobrescreve.
- **Revisor somente leitura.** Só tem Read, Grep e Glob, recebe acesso explícito ao repositório e à pasta da cópia do
  plano (`--add-dir`; fora disso vale o seu modo de permissão e as suas regras de `deny`, como `.env`) e trata plano,
  pedido e repositório como dados (tentativa de injeção de instrução vira achado).

A revisão de um modelo não substitui a sua leitura do plano antes de aprovar.

## 8. Testes

| Script | O que faz | Custo |
|---|---|---|
| `tests/test_hook.py` | Mais de 100 testes offline do hook (inclui os de segurança): entradas malformadas, interruptores, chamada ao revisor, leitura do veredito, rodadas e estado, pedido no transcript, modo verificação, coerência do veredito, falhas visíveis | grátis (~10 s) |
| `tests/live_battery.py` | 17 cenários com gabarito e o revisor real: plano bom, alucinado, excessivo, incompleto, injeção de instrução (no plano e no repo), pedido vago, dependência proibida, plano gigante, plano real que inchou | ~30 s de Haiku por cenário |
| `tests/loop_sim.py` | Simula o laço agente ↔ hook e mede se o plano cresce a cada rodada. Aceita `--arm nome=PASTA_DA_SKILL` para comparar versões | alto (Sonnet + Haiku, várias chamadas) |

Rode a bateria ao vivo depois de qualquer mudança em `agents/plan-reviewer.md` ou no hook: o revisor é um modelo, e só
a medição mostra se a calibração se manteve. A bateria usa o `agents/plan-reviewer.md` da pasta da skill.

## Licença

MIT. Veja [LICENSE](LICENSE).
