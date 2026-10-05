"""One minimal paid request; prints only safe status fields, never credentials."""

from openai import APIStatusError

from .provider import Provider


def main():
    try:
        Provider().client.embeddings.create(model="text-embedding-3-small", input="teste de conexão")
        print("OpenAI: OK")
    except APIStatusError as exc:
        print(f"OpenAI: {type(exc).__name__}; HTTP={exc.status_code}; code={exc.code}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
