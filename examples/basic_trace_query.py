from __future__ import annotations

import datacontext


datacontext.configure(service_name="checkout-api", environment="development")

query = "select * from orders where id = 123"

with datacontext.trace_query(
    db_system="postgres",
    client="internal-db-wrapper",
    query=query,
):
    pass

