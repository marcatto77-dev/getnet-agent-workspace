from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .config import settings


@contextmanager
def connection(vector: bool = False):
    with psycopg.connect(settings().database_url, row_factory=dict_row, connect_timeout=5) as conn:
        if vector:
            register_vector(conn)
        yield conn
