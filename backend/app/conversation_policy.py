"""Customer-facing policy messages, independent of model-generated facts."""

import re


def language_for(message: str) -> str:
    if re.search(r"\b(?:quiero|necesito|llover|mañana|gracias|tarjeta|puedo|mi máquina|sí)\b", message, re.I):
        return "es"
    if re.search(
        r"\b(?:what|when|how|will|rain|weather|please|thanks|my|need|want|not working|yes)\b", message, re.I
    ):
        return "en"
    return "pt"


MESSAGES = {
    "scope": {
        "pt": "Sou o assistente de atendimento Getnet. Posso ajudar com produtos, serviços, máquinas e suporte Getnet, além de consultas de câmbio. Outros assuntos ficam fora deste atendimento.",
        "en": "I am the Getnet support assistant. I can help with Getnet products, services, card machines and support, as well as exchange-rate inquiries. Other topics are outside this service.",
        "es": "Soy el asistente de atención de Getnet. Puedo ayudar con productos, servicios, terminales y soporte de Getnet, además de consultas de cambio. Otros temas quedan fuera de esta atención.",
    },
    "offer": {
        "pt": "Minhas orientações ainda não resolveram sua dúvida. Gostaria de atendimento com um técnico humano?",
        "en": "My guidance has not resolved your issue yet. Would you like to speak with a human support technician?",
        "es": "Mis indicaciones todavía no resolvieron su consulta. ¿Le gustaría hablar con un técnico humano?",
    },
    "missing": {
        "pt": "Não consegui confirmar uma resposta na base de conhecimento nem no site oficial da Getnet. Pode detalhar sua dúvida ou o que já tentou para eu continuar ajudando?",
        "en": "I could not verify an answer in the knowledge base or on Getnet's official website. Could you describe your issue or what you have already tried so I can keep helping?",
        "es": "No pude verificar una respuesta en la base de conocimiento ni en el sitio oficial de Getnet. ¿Puede detallar su consulta o lo que ya intentó para que pueda seguir ayudándole?",
    },
    "missing_exchange": {
        "pt": "A consulta às fontes financeiras oficiais não retornou uma cotação verificável para esse par e data. Não vou inventar um valor. Você pode tentar novamente em instantes.",
        "en": "The official financial sources did not return a verifiable quotation for that pair and date. I will not invent a value. Please try again shortly.",
        "es": "Las fuentes financieras oficiales no devolvieron una cotización verificable para ese par y fecha. No inventaré un valor. Puede intentarlo de nuevo en unos instantes.",
    },
    "exchange_pair": {
        "pt": "Qual moeda você quer consultar: dólar para real, euro para real ou outro par? Se não indicar uma data, consultarei a cotação mais recente.",
        "en": "Which currency pair would you like: USD/BRL, EUR/BRL or another pair? Without a date, I will look up the latest quotation.",
        "es": "¿Qué par desea consultar: USD/BRL, EUR/BRL u otro? Sin fecha, consultaré la cotización más reciente.",
    },
    "exchange_date": {
        "pt": "Essa data não é válida. Informe a data no formato dd/mm/aaaa.",
        "en": "That date is invalid. Please provide a date in dd/mm/yyyy format.",
        "es": "La fecha no es válida. Indique la fecha en formato dd/mm/aaaa.",
    },
    "continue": {
        "pt": "Tudo bem, continuamos por aqui. O que ainda falta resolver ou o que aconteceu após a última orientação?",
        "en": "Of course, we can continue here. What is still unresolved, or what happened after the last suggestion?",
        "es": "De acuerdo, seguimos por aquí. ¿Qué falta resolver o qué sucedió después de la última indicación?",
    },
    "thanks": {
        "pt": "Por nada! Se precisar de mais alguma coisa, estou por aqui.",
        "en": "You're welcome! I am here if you need more help.",
        "es": "¡De nada! Estoy aquí si necesita más ayuda.",
    },
    "terminal": {
        "pt": "Qual máquina precisa de ajuda?",
        "en": "Which card machine needs help?",
        "es": "¿Qué terminal necesita ayuda?",
    },
    "assigned": {
        "pt": "Estamos transferindo você para um técnico. Um especialista já entrou na conversa e receberá suas próximas mensagens.",
        "en": "You are being transferred to a technician. A specialist has joined the conversation and will receive your next messages.",
        "es": "Le estamos transfiriendo a un técnico. Un especialista se ha unido a la conversación y recibirá sus próximos mensajes.",
    },
    "queue": {
        "pt": "Estamos transferindo você para um técnico. Você está na fila, posição {position}.",
        "en": "You are being transferred to a technician. Your position in the queue is {position}.",
        "es": "Le estamos transfiriendo a un técnico. Su posición en la cola es {position}.",
    },
    "personal_missing": {
        "pt": "Não encontrei recebíveis dessa data no seu cadastro. A orientação abaixo é geral e não confirma um recebimento individual: ",
        "en": "I found no receivables for that date in your account. The following guidance is general and does not confirm an individual settlement: ",
        "es": "No encontré cobros para esa fecha en su cuenta. La siguiente orientación es general y no confirma un abono individual: ",
    },
}


def policy_message(key: str, language: str) -> str:
    return MESSAGES[key].get(language.split("-")[0], MESSAGES[key]["pt"])


def offer_reply(message: str) -> bool | None:
    normalized = message.casefold().strip(" .,!?")
    if re.match(r"^(?:não|nao|no|prefiro continuar|quero continuar)\b", normalized):
        return False
    if normalized in {
        "sim",
        "sim por favor",
        "yes",
        "yes please",
        "sí",
        "si",
        "sí por favor",
        "aceito",
        "pode encaminhar",
    }:
        return True
    return None


def offer_choices(language: str) -> list[str]:
    return {
        "pt": ["Sim, quero falar com um técnico", "Não, quero continuar por aqui"],
        "en": ["Yes, I want a human technician", "No, I want to continue here"],
        "es": ["Sí, quiero hablar con un técnico", "No, quiero continuar aquí"],
    }.get(language.split("-")[0], ["Sim, quero falar com um técnico", "Não, quero continuar por aqui"])
