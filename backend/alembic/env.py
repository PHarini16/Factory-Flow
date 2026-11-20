from logging.config import fileConfig

from alembic import context

from app.core.config import get_settings
from app.core.db import Base, make_engine
import app.models  # noqa: F401  (register all tables)

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata
URL = get_settings().database_url


def run_migrations_offline():
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True, user_module_prefix="app.core.types.")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = make_engine(URL)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=URL.startswith("sqlite"),
                          user_module_prefix="app.core.types.")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
