from alembic import context
from sqlalchemy import create_engine

config = context.config
database_url = config.get_main_option("sqlalchemy.url")

connect_args = {}
if database_url.startswith(("postgresql://", "postgresql+")):
    connect_args["options"] = "-csearch_path=reviewai,public"

engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

with engine.connect() as conn:
    context.configure(
        connection=conn,
        target_metadata=None,
        render_as_batch=True,
        version_table_schema="reviewai" if database_url.startswith(("postgresql://", "postgresql+")) else None,
    )
    with context.begin_transaction():
        context.run_migrations()
