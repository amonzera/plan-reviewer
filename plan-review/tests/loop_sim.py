#!/usr/bin/env python3
"""Simula o laço autor <-> hook para medir CONVERGÊNCIA e CRESCIMENTO do plano (o problema da "inflação").

Um agente "autor" (claude -p, Sonnet) faz o papel do agente principal: escreve o plano a partir do pedido e, a cada
`deny` do hook, revisa o plano seguindo a mensagem. O hook roda de verdade (com o revisor real). Mede, por execução:
rodadas, tamanho do plano a cada tentativa, veredito, achados e tempo.

GASTA USO DO SEU PLANO (Sonnet como autor + Haiku como revisor, várias chamadas por execução). Serve para comparar
versões: rode com a skill atual e com uma cópia modificada e compare crescimento e número de rodadas.

Uso (na pasta da skill):
    python3 tests/loop_sim.py [--arm nome=PASTA_DA_SKILL ...] [--scenario C1,C2] [--repeat 2] [--jobs 3] [--out DIR]
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_battery as lb  # noqa: E402

SCENARIOS = {
    "C1_calculadora": ("empty", "crie um app simples de calculadora"),
    "C2_json": ("todo", "adicione ao todo uma flag simples --json no comando list"),
    "C3_contagem": ("todo", "crie um comando simples que mostra quantas tarefas estão concluídas"),
}

AUTHOR_FIRST = """Você é o agente principal do Claude Code, em plan mode (somente leitura). O usuário pediu:

> {request}

Explore o repositório (somente leitura) e escreva o plano de implementação em Markdown, em português, do jeito que você
apresentaria ao usuário para aprovação. Responda SOMENTE com o plano, sem comentários antes ou depois."""

AUTHOR_REVISE = """Você é o agente principal do Claude Code, em plan mode. O usuário pediu:

> {request}

Este é o seu plano atual:

<plano>
{plan}
</plano>

Ao tentar sair do plan mode (ExitPlanMode), o hook de revisão bloqueou a chamada e devolveu esta mensagem para você:

<mensagem_do_hook>
{reason}
</mensagem_do_hook>

Faça o que a mensagem pede. Se ela exigir uma decisão do usuário, e você não puder perguntar agora, assuma a resposta
que o usuário provavelmente daria considerando o pedido original dele. Responda SOMENTE com o plano revisado completo
(Markdown), sem comentários antes ou depois."""


def claude_text(prompt, cwd, model="sonnet"):
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "json", "--no-session-persistence",
           "--allowedTools", "Read,Grep,Glob", "--permission-mode", "dontAsk"]
    p = subprocess.run(cmd, cwd=cwd, env=dict(os.environ, PLAN_REVIEW_ACTIVE="1"), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900, stdin=subprocess.DEVNULL)
    try:
        j = json.loads(p.stdout)
        text = str(j.get("result") or "")
    except ValueError:
        text = p.stdout
    text = text.strip()
    m = re.match(r"^```(?:markdown|md)?\n(.*)\n```$", text, re.S)
    return (m.group(1) if m else text).strip()


def run_hook(hook, repo, sid, transcript, plan, tmp, dbg):
    ev = {"session_id": sid, "transcript_path": transcript, "cwd": repo, "permission_mode": "plan",
          "hook_event_name": "PreToolUse", "tool_name": "ExitPlanMode", "tool_input": {"plan": plan}}
    env = {k: v for k, v in os.environ.items() if not k.startswith("PLAN_REVIEW_")}
    env.update({"TMPDIR": tmp, "PLAN_REVIEW_DEBUG_DIR": dbg})
    t0 = time.time()
    p = subprocess.run([sys.executable, hook], input=json.dumps(ev), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, cwd=repo, timeout=900)
    secs = round(time.time() - t0, 1)
    reason, sysmsg, decision = "", "", "allow"
    if p.stdout.strip():
        j = json.loads(p.stdout)
        hs = j.get("hookSpecificOutput", {})
        decision = hs.get("permissionDecision") or "allow"
        reason, sysmsg = hs.get("permissionDecisionReason", ""), j.get("systemMessage", "")
    return decision, reason, sysmsg, secs, p.stderr[-300:]


def one(arm, project, name, n, workdir, max_iter):
    repo_kind, request = SCENARIOS[name]
    root = os.path.join(workdir, f"{arm}.{name}.{n}")
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    for rel, content in lb.REPOS[repo_kind].items():
        pth = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(pth), exist_ok=True)
        with open(pth, "w", encoding="utf-8") as fh:
            fh.write(content)
    lb.materialize_claude(repo, project)
    sid = str(uuid.uuid4())
    transcript = os.path.join(root, "transcript.jsonl")
    lb.write_transcript(transcript, sid, request, None, repo)
    hook = os.path.join(repo, ".claude", "skills", "plan-review", "hooks", "plan_review_hook.py")
    tmp, dbg = os.path.join(root, "tmp"), os.path.join(root, "debug")
    os.makedirs(tmp)

    trace, attempts = [], []
    plan = claude_text(AUTHOR_FIRST.format(request=request), repo)
    for i in range(1, max_iter + 1):
        decision, reason, sysmsg, secs, err = run_hook(hook, repo, sid, transcript, plan, tmp, dbg)
        verdict, counts = lb.parse_report(reason + "\n" + sysmsg)
        attempts.append({"i": i, "chars": len(plan), "lines": len(plan.splitlines()), "decision": decision,
                         "verdict": verdict, "findings": counts, "hook_secs": secs, "sysmsg": sysmsg[:200]})
        trace.append(f"\n\n######## TENTATIVA {i}: plano ({len(plan)} chars, {len(plan.splitlines())} linhas), decisão={decision}\n{plan}\n"
                     f"\n---- hook ----\n{reason or sysmsg}\n[stderr] {err}")
        if decision != "deny":
            break
        plan = claude_text(AUTHOR_REVISE.format(request=request, plan=plan, reason=reason), repo)
        if not plan:
            break
    with open(os.path.join(root, "trace.md"), "w", encoding="utf-8") as fh:
        fh.write("".join(trace))
    first, last = attempts[0], attempts[-1]
    return {"arm": arm, "scenario": name, "n": n, "tries": len(attempts), "denies": sum(a["decision"] == "deny" for a in attempts),
            "first_lines": first["lines"], "final_lines": last["lines"], "growth_lines": round(last["lines"] / max(1, first["lines"]) - 1, 2),
            "first_chars": first["chars"], "final_chars": last["chars"], "final_decision": last["decision"],
            "verdicts": [a["verdict"] for a in attempts], "hook_secs": round(sum(a["hook_secs"] for a in attempts), 1),
            "attempts": attempts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="append", default=[], help="nome=PASTA_DA_SKILL (repetível; padrão: esta skill)")
    ap.add_argument("--scenario", default="")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--max-iter", type=int, default=6)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    names = [s for s in SCENARIOS if not a.scenario or any(s.startswith(x) for x in a.scenario.split(","))]
    workdir = a.out or tempfile.mkdtemp(prefix="plan-review-loop-")
    os.makedirs(workdir, exist_ok=True)
    arms = dict(x.split("=", 1) for x in a.arm) or {"atual": os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")}
    arms = {k: os.path.abspath(v) for k, v in arms.items()}
    print(f"saída={workdir} | braços={list(arms)} | cenários={names} x{a.repeat}\n", flush=True)
    results = []
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(one, arm, proj, nm, n, workdir, a.max_iter) for nm in names for n in range(1, a.repeat + 1) for arm, proj in arms.items()]
        for f in cf.as_completed(futs):
            try:
                r = f.result()
            except Exception as e:  # noqa: BLE001
                print("ERRO", repr(e), flush=True)
                continue
            results.append(r)
            print(f"{r['arm']:4} {r['scenario']:15} n={r['n']} tentativas={r['tries']} negadas={r['denies']} linhas {r['first_lines']}->{r['final_lines']} "
                  f"({r['growth_lines']:+.0%}) chars {r['first_chars']}->{r['final_chars']} vereditos={r['verdicts']} final={r['final_decision']} hook={r['hook_secs']}s", flush=True)
    with open(os.path.join(workdir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
