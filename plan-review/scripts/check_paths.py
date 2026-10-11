#!/usr/bin/env python3
"""Verifica quais caminhos citados em um plano existem no repositório.

Uso:
    python3 check_paths.py PLANO.md [--root RAIZ_DO_REPO]

É uma checagem HEURÍSTICA e barata, usada como ponto de partida para o revisor.
Ausente NÃO significa alucinação (o plano pode criar o arquivo) e existente NÃO
significa que o plano está certo sobre o conteúdo dele. Quem julga é o revisor.
"""
import argparse
import os
import re
import sys

IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", ".next", ".cache", ".idea", ".vscode", "coverage", ".tox",
}
EXTS = {
    "py", "js", "ts", "tsx", "jsx", "mjs", "cjs", "json", "yaml", "yml", "toml",
    "md", "txt", "sh", "go", "rs", "java", "kt", "rb", "php", "c", "h", "cpp",
    "cs", "sql", "html", "css", "scss", "vue", "svelte", "ini", "cfg", "lock",
    "env", "gradle", "xml", "ps1", "tf", "proto", "swift", "dart", "ex", "exs",
}
# Nomes de frameworks que parecem arquivos (Next.js, Node.js...) e geram ruído.
NOT_FILES = {
    "next.js", "node.js", "vue.js", "nuxt.js", "express.js", "react.js",
    "three.js", "d3.js", "chart.js", "socket.io", "alpine.js", "ember.js",
    "backbone.js", "nest.js", "deno.js", "bun.js",
}
MAX_FILES_SCANNED = 200_000


def walk_repo(root):
    """Retorna (basename -> [caminhos relativos], set de diretórios de 1º nível)."""
    by_name, count = {}, 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for f in filenames:
            count += 1
            if count > MAX_FILES_SCANNED:
                return by_name
            rel = os.path.relpath(os.path.join(dirpath, f), root)
            by_name.setdefault(f, []).append(rel.replace(os.sep, "/"))
    return by_name


def clean(token):
    lead, trail = "`'\"“”‘’([<", "`'\"“”‘’)]>.,;:!?"
    prev = None
    while prev != token:                                # remove aspas/pontuação até estabilizar
        prev = token
        token = token.strip().lstrip(lead).rstrip(trail)
    token = re.sub(r"#L\d+(-L?\d+)?$", "", token)       # arquivo.py#L10-L20
    token = re.sub(r":\d+(-\d+)?$", "", token)          # arquivo.py:123
    token = re.sub(r"\(\)$", "", token)                 # arquivo.py()
    if token.startswith("./"):
        token = token[2:]
    return token


def candidates(line, top_level):
    """Gera (referência, tipo) de uma linha do plano."""
    for raw in re.split(r"[\s,;|]+", line):          # "|" separa células de tabelas markdown
        in_backticks = "`" in raw
        tok = clean(raw)
        if re.fullmatch(r"[\w.@-]+(?:\\[\w.@-]+)+", tok):
            tok = tok.replace("\\", "/")             # src\auth\login.py (Windows)
        if not tok or len(tok) < 3 or "://" in tok:
            continue
        if any(c in tok for c in "*{}$=\\") or tok.startswith(("@", "-", "#")):
            continue                                    # glob, template, pacote npm, flag
        if tok.lower() in NOT_FILES:
            continue
        last = tok.rstrip("/").split("/")[-1]
        ext = last.rsplit(".", 1)[-1].lower() if "." in last else ""
        has_ext = ext in EXTS
        if "/" in tok:
            first = tok.lstrip("/").split("/")[0]
            if has_ext or tok.endswith("/") or in_backticks or first in top_level:
                yield tok, "caminho"
        elif has_ext:
            yield tok, "arquivo"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--root", default=os.getcwd())
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    try:
        with open(args.plan, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError as e:
        print(f"ERRO: não consegui ler o plano: {e}", file=sys.stderr)
        return 2

    by_name = walk_repo(root)
    top_level = {d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))}

    rroot = os.path.realpath(root)
    seen, ok, moved, missing = set(), [], [], []
    for n, line in enumerate(lines, 1):
        for ref, kind in candidates(line, top_level):
            if ref in seen:
                continue
            real = os.path.realpath(os.path.join(root, ref))
            if real != rroot and not real.startswith(rroot + os.sep):
                continue                                # fora da raiz (absoluto ou ../): não revelar se existe
            seen.add(ref)
            if os.path.exists(os.path.join(root, ref)):
                ok.append((ref, n))
                continue
            base = ref.rstrip("/").split("/")[-1]
            others = [p for p in by_name.get(base, []) if p.endswith(ref)] or (
                by_name.get(base, []) if kind == "arquivo" else []
            )
            if others:
                moved.append((ref, n, others[:5]))
            else:
                missing.append((ref, n))

    print(f"Raiz verificada: {root}")
    print(f"Referências únicas analisadas: {len(seen)}\n")
    print(f"## Existem ({len(ok)})")
    for ref, n in ok:
        print(f"- {ref}  (plano, linha {n})")
    print(f"\n## Existem em outro caminho ({len(moved)})")
    for ref, n, others in moved:
        print(f"- {ref}  (plano, linha {n}) -> {', '.join(others)}")
    print(f"\n## Não encontrados ({len(missing)})")
    for ref, n in missing:
        print(f"- {ref}  (plano, linha {n})")
    print("\nObs.: heurística. 'Não encontrado' pode ser arquivo que o plano vai criar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
