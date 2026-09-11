import os
import pytest
from sqlalchemy import create_engine, inspect
from alembic.config import Config
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from models import Base

@pytest.fixture
def alembic_config():
    """
    Creates an Alembic config object pointing to a fresh,
    in-memory SQLite database specifically for migration tests.
    """
    db_path = "sqlite:///migration_test.db"
    
    # We must construct the path to alembic.ini relative to the backend directory
    # Pytest usually runs from the 'backend' dir in our environment.
    ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
    alembic_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic")
    
    cfg = Config(ini_path)
    cfg.set_main_option("script_location", alembic_dir)
    cfg.set_main_option("sqlalchemy.url", db_path)
    
    engine = create_engine(db_path)
    
    yield cfg, engine
    
    engine.dispose()
    if os.path.exists("migration_test.db"):
        os.remove("migration_test.db")

def test_upgrade_and_downgrade(alembic_config):
    """
    Verifies that we can upgrade a fresh database to 'head',
    verify its tables, and then downgrade it to 'base'.
    """
    cfg, engine = alembic_config
    
    # Run upgrades to head
    command.upgrade(cfg, "head")
    
    # Verify tables
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    assert "users" in tables
    assert "meshes" in tables
    assert "jobs" in tables
    assert "alembic_version" in tables
    
    # Run downgrades to base
    command.downgrade(cfg, "base")
    
    # Verify tables are gone (except sqlite specifics)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    assert "users" not in tables
    assert "jobs" not in tables
    assert "meshes" not in tables

def test_schema_drift(alembic_config):
    """
    Verifies that there is no drift between the ORM models
    and the database schema constructed by the migrations.
    """
    cfg, engine = alembic_config
    
    # Run upgrades to head
    command.upgrade(cfg, "head")
    
    with engine.connect() as connection:
        mc = MigrationContext.configure(connection)
        
        # compare_metadata returns a list of differences
        diff = compare_metadata(mc, Base.metadata)
        
        # A perfectly aligned database should have zero differences
        # Diff is a list of tuples detailing the discrepancies.
        # However, SQLite handles some things poorly like autoincrement sequence, 
        # so we filter out typical noise if necessary.
        filtered_diff = []
        for diff_item in diff:
            if isinstance(diff_item, tuple) and diff_item[0] == "remove_table":
                # ignore removed tables like alembic_version
                if diff_item[1].name == "alembic_version":
                    continue
            if isinstance(diff_item, tuple) and diff_item[0] == "add_table":
                # ignore test dummy models
                if diff_item[1].name == "dummy_models":
                    continue
            filtered_diff.append(diff_item)
            
        assert not filtered_diff, f"Schema drift detected: {filtered_diff}"
