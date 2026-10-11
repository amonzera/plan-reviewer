#!/usr/bin/env python3
"""Teste de fumaça do hook, sem abrir o Claude Code. Usa o `claude` real (gasta um pouco do seu uso).

Rode DENTRO de um repositório onde o agente `plan-reviewer` esteja instalado:  python3 smoke_test.py
Envia ao hook um evento ExitPlanMode sintético: um pedido simples, e um plano que cita arquivos e funções
inexistentes. Esperado: o hook NEGA e devolve a revisão (veredito ALUCINADO).
Se aparecer "REVISÃO AUTOMÁTICA NÃO EXECUTADA", o hook funcionou mas o revisor não rodou: leia o motivo.
Para o teste gratuito, sem chamar o `claude`: python3 ../tests/test_hook.py
"""
import json
import os
import subprocess
import sys
import tempfile
import uuid

hook = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plan_review_hook.py")
sid = str(uuid.uuid4())
with tempfile.TemporaryDirectory(prefix="plan-review-smoke-") as td:
    transcript = os.path.join(td, "transcript.jsonl")
    with open(transcript, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user", "origin": {"kind": "human"}, "message": {"role": "user",
                 "content": "troque a mensagem de saudação por uma mais curta"}}) + "\n")
    event = {"session_id": sid, "transcript_path": transcript, "cwd": os.getcwd(), "hook_event_name": "PreToolUse",
             "tool_name": "ExitPlanMode", "tool_input": {"plan": "# Plano de teste\n"
             "1. Editar `src/inexistente/saudacao.py` e trocar o retorno de `utils.funcao_que_nao_existe()`.\n"
             "2. Rodar `pytest tests/test_saudacao_inexistente.py`.\n"}}
    r = subprocess.run([sys.executable, hook], input=json.dumps(event), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")

uid = os.getuid() if hasattr(os, "getuid") else "user"
log = os.path.join(tempfile.gettempdir(), f"plan-review-{uid}", "hook.log")
out = r.stdout.strip()
if not out:
    print("O hook LIBEROU sem revisar e sem avisar. Veja o log:\n  " + log)
    print(r.stderr[-500:])
    sys.exit(1)
try:
    j = json.loads(out)
except ValueError:
    print("Saída inesperada do hook:\n" + out[:500])
    sys.exit(1)
d = j.get("hookSpecificOutput", {})
print("Decisão:", d.get("permissionDecision", "nenhuma (liberou)"))
print("-" * 60)
print((d.get("permissionDecisionReason") or j.get("systemMessage") or "")[:1800])
print("-" * 60)
if d.get("permissionDecision") == "deny" and "NÃO EXECUTADA" in d.get("permissionDecisionReason", ""):
    print("Atenção: o hook funcionou, mas o revisor não rodou. Veja o motivo acima e o log:\n  " + log)
    sys.exit(1)
print("OK: o hook negou ExitPlanMode e devolveu a revisão." if d.get("permissionDecision") == "deny"
      else "Atenção: o hook liberou. O revisor considerou o plano ADEQUADO? Veja o log:\n  " + log)
