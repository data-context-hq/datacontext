from __future__ import annotations

import datacontext


def execute(query: str) -> str:
    return f"executed {query}"


datacontext.configure(
    service_name="checkout-api",
    environment="development",
    instruments=[
        datacontext.instrument_function(
            target="__main__.execute",
            query_arg="query",
            db_system="postgres",
            client="example-wrapper",
        )
    ],
)

execute("select * from orders where id = 123")
