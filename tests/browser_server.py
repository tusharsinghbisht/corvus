"""Isolated browser-test backend. Test records never enter the live application database."""

import os
from uuid import uuid4

import psycopg
import uvicorn
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_ingestion import document, settings

from corvus.server.api import create_app
from corvus.server.database import connect, initialize
from corvus.server.ingestion import insert_alert


def main():
    base = os.environ["CORVUS_TEST_DATABASE_URL"]
    schema = "corvus_browser_" + uuid4().hex
    with psycopg.connect(base) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    config = settings(
        database_url=make_conninfo(base, options="-csearch_path=" + schema),
        origin="http://127.0.0.1:8768",
    )
    try:
        initialize(config)
        connection_id = uuid4()
        with connect(config) as db:
            db.execute(
                """
                INSERT INTO connections(id,name,indexer_url,username,encrypted_password,backfill_start,checkpoint,last_sync_at)
                VALUES(%s,'Browser-test Wazuh','https://wazuh.indexer:9200','reader','test-only',now()-interval '24 hours',now(),now())
            """,
                (connection_id,),
            )
            for number in range(55):
                item = document(str(number), level=12 if number < 3 else 5)
                if number == 0:
                    item["source"]["rule"]["description"] = (
                        '<img src=x onerror="window.corvusInjection=true">'
                    )
                insert_alert(db, connection_id, item)
        uvicorn.run(
            create_app(config),
            host="127.0.0.1",
            port=8769,
            access_log=False,
            server_header=False,
            proxy_headers=False,
        )
    finally:
        with psycopg.connect(base) as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    main()
