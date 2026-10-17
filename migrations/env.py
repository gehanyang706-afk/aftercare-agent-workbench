from alembic import context
from sqlalchemy import create_engine

from aftercare.config import Settings

config = context.config
settings = config.attributes.get("settings") or Settings()
target_metadata = None

if context.is_offline_mode():
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(
        settings.database_url.get_secret_value(),
        connect_args={"connect_timeout": 2, "options": "-c statement_timeout=5000"},
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
