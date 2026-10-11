---
name: plan-review
description: Revisão independente de um plano de implementação contra o repositório atual, antes de escrever código. Diz se o plano é ADEQUADO (ancorado no repo e mínimo), EXCESSIVO (faz mais que o necessário ou reinventa o que existe), INCOMPLETO ou ALUCINADO (cita arquivos, funções, APIs ou dependências que não existem). Use sempre que o usuário pedir para revisar, validar, criticar ou dar uma segunda opinião num plano, spec ou abordagem, ou perguntar se o plano "faz sentido para o repo", "é o mínimo" ou "está alucinado". Não rode por conta própria ao fim do plan mode se o hook plan_review_hook.py estiver instalado (ele já revisa automaticamente). Triggers - "revise esse plano", "plan review", "review this plan", "esse plano é adequado?", "valide a abordagem".
---

# Plan Review

Um plano escrito por quem vai implementá-lo costuma confirmar as próprias suposições, e agentes
inventam com facilidade arquivos, funções e APIs que "deveriam existir". Esta skill coloca um
revisor com **contexto limpo** e **acesso somente leitura ao repositório** entre o plano e o código.
Ele confere o plano contra o que realmente existe **e** contra o que o usuário pediu, no nível de esforço que
ele pediu. O revisor existe para barrar o que impede entregar o pedido ou excede o pedido, não para deixar o
plano perfeito: revisar sem essa trava faz o plano crescer a cada rodada.

## Vereditos

| Veredito | Significado | O que fazer |
|---|---|---|
| ADEQUADO | Ancorado no repo e proporcional ao pedido, sem achado CRÍTICO/ALTO (MÉDIO e BAIXO são opcionais) | Seguir para a implementação |
| EXCESSIVO | Faz bem mais que o pedido exige no nível pretendido, reinventa algo existente ou viola regra do repo | **Cortar** o excesso (não trocar por outro) |
| INCOMPLETO | Ancorado e proporcional, mas com lacuna CRÍTICA/ALTA | Resolver só os bloqueantes, do jeito mais barato |
| ALUCINADO | Afirmações centrais sobre o repo são falsas ou divergentes | Bloquear até corrigir ou o usuário sobrescrever |

## Quando usar

- Quando o usuário pedir uma revisão (plano em arquivo, colado na conversa ou vindo de outra ferramenta).
- **Não** use por conta própria ao fim do plan mode se o hook `plan_review_hook.py` estiver registrado em
  `~/.claude/settings.json` ou `.claude/settings.json`: a revisão já é automática e rodar as duas revisaria duas vezes.

## Fluxo

### 1. Localizar o plano

Procure, nesta ordem: o arquivo de plano indicado no contexto do sistema (plan mode), um arquivo que o usuário
citou (`PLAN.md`, `docs/spec.md`...), um plano colado na conversa. Se houver mais de um candidato ou nenhum,
peça ao usuário que confirme qual é o plano. Não adivinhe.

Se o plano só existe na conversa, grave-o num arquivo **fora do repositório** (diretório temporário do
sistema, por exemplo via `mktemp`, ou `$env:TEMP` no Windows) para o revisor poder lê-lo. Não suje o repo.
Se o plan mode impedir a gravação, peça ao usuário para sair do plan mode ou para indicar o arquivo do plano.

Anote também o **pedido original do usuário**, nas palavras dele (não o resumo que o plano faz dele), e as
decisões que ele já tomou na conversa (respostas a perguntas, opções escolhidas). O revisor usa isso para medir
escopo e proporção: sem o pedido ele não tem como saber se o plano está inchado, e "simples" no pedido muda o que
conta como excesso. Se o pedido não estiver claro, pergunte uma vez.

### 2. Checagem barata de caminhos (opcional, recomendada)

Se houver Python 3 disponível, rode na raiz do repo:

```
python3 <diretório desta skill>/scripts/check_paths.py <arquivo-do-plano> --root <raiz-do-repo>
```

Ele lista os caminhos citados no plano que existem, que estão em outro lugar e que não foram encontrados.
É só heurística: "não encontrado" pode ser algo que o plano vai criar. Entregue a saída ao revisor como
ponto de partida. Se o script falhar ou não houver Python, siga sem ele.

### 3. Chamar o revisor com contexto limpo

Use a ferramenta de subagentes (Task/Agent) com o agente `plan-reviewer`. Passe **apenas**:

- o caminho do plano e a raiz do repositório;
- o **modo**: COMPLETO na 1ª rodada, VERIFICAÇÃO da 2ª em diante;
- o pedido do usuário e as decisões dele (passo 1), citados sem resumir;
- a saída do passo 2, se houver;
- na VERIFICAÇÃO: os achados bloqueantes da rodada anterior e o diff do plano (o revisor só confere o que mudou).

Rode o revisor em primeiro plano e espere o relatório completo antes de seguir; não continue com resultado parcial.
O modelo do revisor vem do campo `model` do agente (haiku por padrão): não passe outro modelo na chamada,
a menos que o usuário peça.

Não passe histórico da conversa, justificativas nem a sua opinião sobre o plano. O contexto limpo é o que
dá independência à revisão. Não limite o revisor a uma lista fixa de arquivos: ele precisa poder buscar no
repo para checar o que o plano afirma e para achar código que já faz o que o plano quer criar.

Se o agente `plan-reviewer` não estiver instalado, leia `agents/plan-reviewer.md` (na pasta desta skill),
ignore o bloco de frontmatter e passe o restante como prompt a um subagente genérico, avisando que ele
**não pode editar arquivos**. Se a plataforma não tiver subagentes, avise o usuário: uma revisão feita
na mesma sessão que escreveu o plano perde a independência. Faça-a como checklist manual seguindo
`agents/plan-reviewer.md` e diga isso claramente no resultado.

### 4. Tratar o resultado

Mostre o relatório do revisor ao usuário sem reescrevê-lo e leia a linha final `Veredito:`.

- **ADEQUADO**: resuma em 2 ou 3 linhas e siga para a implementação. Achados MÉDIO e BAIXO são opcionais.
- **EXCESSIVO / INCOMPLETO**: corrija **só** os achados CRÍTICO e ALTO e rode de novo (passo 3, revisor novo).
- **ALUCINADO**: não implemente. Corrija cada afirmação falsa verificando no repo, e rode de novo.
  Só avance se o veredito virar ADEQUADO ou se o usuário sobrescrever explicitamente.

Ao corrigir o plano:
- **Prefira cortar a acrescentar.** Para cada achado, nesta ordem: (a) remova do plano a parte que gera o
  problema; (b) fixe em UMA linha o comportamento mais simples; (c) só acrescente algo novo se o pedido do usuário exigir.
- Não amplie o escopo: nada de funcionalidade, regra, teste, documentação ou arquivo que o usuário não pediu.
  Não cole o relatório dentro do plano.
- Se o relatório trouxer uma "Pergunta de escopo", faça-a ao usuário antes de mexer no plano e siga a resposta.
- Se um achado exigir decisão de escopo ou de design, pergunte ao usuário em vez de decidir sozinho.
- Mostre ao usuário o que mudou entre as rodadas.
- Não aceite um achado só para agradar nem o descarte só por conveniência. Se discordar de um achado bloqueante,
  diga por quê em uma linha, com evidência do repo.

### 5. Limites

- No máximo **3 rodadas**. A 1ª é completa; da 2ª em diante o revisor só **verifica** se os achados bloqueantes foram
  resolvidos e se as mudanças criaram problema novo, sem procurar defeitos novos no que já foi revisado. Se o plano
  cresceu mais de ~25% entre as rodadas sem que um achado bloqueante ou o usuário tenha pedido, isso é inchaço:
  remova. Se ainda não houver ADEQUADO ao fim, pare e entregue ao usuário o último relatório e os pontos em aberto.
- Cada rodada usa um revisor novo; nunca reaproveite o anterior.
- Sobrescrita do usuário: registre `Plan review: SOBRESCRITO pelo usuário (veredito X) - motivo: ...`.
- Aprovação: registre `Plan review: ADEQUADO (rodada N) - resumo de uma linha do que foi verificado`.

### 6. Limpeza

Apague os arquivos temporários criados no passo 1 (nunca o plano original do usuário).

## O que esta skill não faz

- Não implementa nada nem edita o plano por conta própria sem mostrar as mudanças.
- Não avalia gosto de design nem estilo de escrita do plano; só o que afeta materialmente a implementação.
- Um veredito ADEQUADO reduz o risco, mas não o elimina. O revisor lista em "Limites desta revisão" o que não conseguiu verificar (comportamento em runtime, APIs externas) e isso continua sendo responsabilidade de quem implementa.
