"""The few server texts that a person or a model reads, in English and Portuguese.

Only prose is translated. Tool names, statuses (active, pending...), types and
API fields stay the same in every language, so clients never need to care.
"""

LANGS = ("en", "pt")

TEXT = {
    "en": {
        "instructions": """\
Long-term memory shared by every Claude session of {owner}: servers, databases,
projects, decisions and the recipes that are known to work.

READ: call search_memory before touching any server, database or system of
{owner}. The approved way of doing it is probably already written down here.

WRITE: new memories go through save_memory, NOT to local files, so they are
visible from every machine and every project. Set `project` to the project the
fact belongs to, `type` to one of project/reference/feedback/user, and link to
existing memories with [[other-memory-name]] in the body. Hand-written links
carry relationships that similarity search cannot infer.

VALIDITY: every memory has a status (active | pending | resolved | superseded).
When something a memory listed as pending gets done, call mark_memory with
status resolved and a short note; otherwise it keeps showing up as open. New
memories about unfinished work start as pending. For "what is still pending?",
use list_pending.""",
        "not_found": "No memory found for: {q}",
        "no_pending": "(no pending memories)",
        "empty": "(empty)",
        "n_memories": "{n} memories",
        "ctx_title": "# Relevant memories for: {q}",
        "ctx_project": "project",
        "ctx_on": "on",
        "ctx_stale": "> Old facts may be stale: check the date before acting on them.",
        "pinned": "# Pinned",
    },
    "pt": {
        "instructions": """\
Memória de longo prazo compartilhada por todas as sessões do Claude de {owner}:
servidores, bancos, projetos, decisões e as receitas que já se sabe que funcionam.

LER: chame search_memory antes de mexer em qualquer servidor, banco ou sistema
de {owner}. O jeito aprovado de fazer provavelmente já está escrito aqui.

GRAVAR: memória nova vai por save_memory, NÃO em arquivo local, para ficar
visível de qualquer máquina e de qualquer projeto. Preencha `project` com o
projeto a que o fato pertence, `type` com project/reference/feedback/user, e
ligue a memórias existentes com [[nome-da-outra]] no corpo. A ligação escrita
à mão guarda relações que a busca por semelhança não consegue inferir.

VALIDADE: toda memória tem status (active | pending | resolved | superseded).
Quando algo que uma memória dava como pendente for feito, chame mark_memory com
status resolved e uma nota curta; sem isso ela continua aparecendo como aberta.
Memória nova sobre trabalho inacabado nasce como pending. Para "o que está
pendente?", use list_pending. Escreva as memórias em português.""",
        "not_found": "Nenhuma memória encontrada para: {q}",
        "no_pending": "(nenhuma memória pendente)",
        "empty": "(vazio)",
        "n_memories": "{n} memórias",
        "ctx_title": "# Memórias relevantes para: {q}",
        "ctx_project": "projeto",
        "ctx_on": "em",
        "ctx_stale": "> Fatos antigos podem estar desatualizados: confira a data antes de agir.",
        "pinned": "# Fixada",
    },
}


def norm(lang):
    """'pt-BR', 'pt_br', 'PT' -> 'pt'; anything unknown -> 'en'."""
    lang = (lang or "").strip().lower()[:2]
    return lang if lang in LANGS else "en"


def text(lang, key, **kw):
    s = TEXT[norm(lang)].get(key) or TEXT["en"][key]
    return s.format(**kw) if kw else s
