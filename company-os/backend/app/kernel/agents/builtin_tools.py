"""
app/kernel/agents/builtin_tools.py
──────────────────────────────────
Kernel tools every department can grant to its agents. Departments register
their own tools from their package; they don't edit this file.
"""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import select

from app.kernel import records
from app.kernel.agents.tools import Effect, Tool, ToolContext, register_tool, require_approval
from app.kernel.agents.untrusted import wrap
from app.kernel.channels import email as email_channel
from app.kernel.channels import whatsapp as whatsapp_channel
from app.kernel.memory.retriever import default_retriever
from app.kernel.models import ChannelMessage, Task
from app.kernel.schemas import NoteIn, TaskIn, normalize_phone


def _search_memory(ctx: ToolContext, args: dict) -> dict:
    hits = default_retriever().search(ctx.db, ctx.principal.workspace_id, args["query"], args.get("limit", 5))
    results = []
    for h in hits:
        ctx.citations.append(h.as_dict())
        n = len(ctx.citations)
        results.append({
            "citation": n,
            "document_title": h.document_title,
            "heading": h.heading,
            "content": wrap(f"document:{h.document_id}#{h.chunk_index}", h.content),
        })
    return {"results": results, "note": "Cite sources as [n] using the citation numbers." if results else "No matching documents."}


def _list_tasks(ctx: ToolContext, args: dict) -> dict:
    stmt = select(Task).where(Task.workspace_id == ctx.principal.workspace_id)
    if args.get("status"):
        stmt = stmt.where(Task.status == args["status"])
    else:
        stmt = stmt.where(Task.status.in_(["open", "in_progress"]))
    rows = ctx.db.execute(stmt.order_by(Task.due_date.asc().nulls_last(), Task.id).limit(50)).scalars()
    return {"tasks": [
        {"id": t.id, "title": t.title, "status": t.status, "priority": t.priority,
         "due_date": t.due_date.isoformat() if t.due_date else None}
        for t in rows
    ]}


def _validated(model, args: dict):
    try:
        return model(**args)
    except ValidationError as e:
        raise ValueError("; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())) from None


def _create_task(ctx: ToolContext, args: dict) -> dict:
    task = records.create_record(ctx.db, ctx.principal, "task", _validated(TaskIn, args), agent_run_id=ctx.agent_run_id)
    return {"task_id": task.id, "title": task.title}


def _create_note(ctx: ToolContext, args: dict) -> dict:
    note = records.create_record(ctx.db, ctx.principal, "note", _validated(NoteIn, args), agent_run_id=ctx.agent_run_id)
    return {"note_id": note.id, "title": note.title}


def _send_email(ctx: ToolContext, args: dict) -> dict:
    require_approval(ctx)
    message_id = email_channel.send(args["to"], args["subject"], args["body"])
    ctx.db.add(ChannelMessage(
        workspace_id=ctx.principal.workspace_id, channel="email", direction="out",
        from_addr="company", to_addr=args["to"], body=f"{args['subject']}\n\n{args['body']}",
        user_id=ctx.principal.user_id,
    ))
    return {"sent": True, "message_id": message_id}


def _send_whatsapp(ctx: ToolContext, args: dict) -> dict:
    require_approval(ctx)
    to = normalize_phone(args["to"])
    if not to:
        raise ValueError("invalid phone number")
    sid = whatsapp_channel.send(to, args["body"])
    ctx.db.add(ChannelMessage(
        workspace_id=ctx.principal.workspace_id, channel="whatsapp", direction="out", external_id=sid or None,
        from_addr="company", to_addr=to, body=args["body"], user_id=ctx.principal.user_id,
    ))
    return {"sent": True, "sid": sid}


def register_builtin_tools() -> None:
    register_tool(Tool(
        name="search_memory",
        description="Search the company's documents. Returns numbered passages; cite them as [n].",
        effect=Effect.READ,
        permission="memory.search",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 500, "description": "What to look for"},
                "limit": {"type": "integer", "description": "Max passages (1-10)"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=_search_memory,
    ))
    register_tool(Tool(
        name="list_tasks",
        description="List the workspace's tasks (open and in-progress by default).",
        effect=Effect.READ,
        permission="records.read",
        input_schema={
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["open", "in_progress", "done", "cancelled"]}},
            "additionalProperties": False,
        },
        handler=_list_tasks,
    ))
    register_tool(Tool(
        name="create_task",
        description="Create a task in the OS (internal; no approval needed).",
        effect=Effect.INTERNAL,
        permission="records.write",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "maxLength": 300},
                "description": {"type": "string"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        handler=_create_task,
    ))
    register_tool(Tool(
        name="create_note",
        description="Save a note in the OS (internal; no approval needed).",
        effect=Effect.INTERNAL,
        permission="records.write",
        input_schema={
            "type": "object",
            "properties": {"title": {"type": "string", "maxLength": 300}, "body": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
        },
        handler=_create_note,
    ))
    register_tool(Tool(
        name="send_email",
        description="Send an email to someone outside the company. Always becomes a proposal the founder must approve.",
        effect=Effect.EXTERNAL,
        permission="approvals.propose",
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "maxLength": 320},
                "subject": {"type": "string", "maxLength": 300},
                "body": {"type": "string", "maxLength": 20000},
            },
            "required": ["to", "subject", "body"],
            "additionalProperties": False,
        },
        handler=_send_email,
        summarize=lambda a: f"Email to {a.get('to')}: {a.get('subject')}",
    ))
    register_tool(Tool(
        name="send_whatsapp",
        description="Send a WhatsApp message to someone outside the company. Always becomes a proposal the founder must approve.",
        effect=Effect.EXTERNAL,
        permission="approvals.propose",
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "maxLength": 32, "description": "Phone number, international format"},
                "body": {"type": "string", "maxLength": 1600},
            },
            "required": ["to", "body"],
            "additionalProperties": False,
        },
        handler=_send_whatsapp,
        summarize=lambda a: f"WhatsApp to {a.get('to')}: {str(a.get('body', ''))[:80]}",
    ))
