from alembic import context
from sqlalchemy import create_engine

config = context.config
engine = create_engine(config.get_main_option("sqlalchemy.url"))
with engine.connect() as conn:
    context.configure(connection=conn, target_metadata=None, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
