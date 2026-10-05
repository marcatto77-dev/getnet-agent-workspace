from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

AGENT_TOOLS = {
    "Support": {"get_receivables", "get_terminal_status", "get_customer_profile", "list_customer_terminals"},
    "Knowledge": {"rag.retrieve", "web_search"},
    "Escalation": {"get_customer_profile", "get_terminal_status", "llm.escalation"},
}


class ToolPolicyError(RuntimeError):
    pass


def validate_tool_plan(agent: str, names: list[str], maximum: int = 4) -> list[str]:
    if len(names) > maximum:
        raise ValueError("Limite de ferramentas excedido.")
    allowed = AGENT_TOOLS.get(agent, set())
    if any(name not in allowed for name in names):
        raise ToolPolicyError("Ferramenta não permitida para este agente.")
    return list(dict.fromkeys(names))


def execute_readonly(function, *args, timeout: float):
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(function, *args)
    try:
        result = future.result(timeout=timeout)
    except FutureTimeout as exc:
        future.cancel()
        # The callable cannot be forcibly stopped once running. Do not wait for it
        # during shutdown: database/network clients must enforce their own I/O limits.
        pool.shutdown(wait=False, cancel_futures=True)
        raise ToolPolicyError("A ferramenta excedeu o tempo permitido.") from exc
    except BaseException:
        pool.shutdown(wait=True)
        raise
    else:
        pool.shutdown(wait=True)
        return result
