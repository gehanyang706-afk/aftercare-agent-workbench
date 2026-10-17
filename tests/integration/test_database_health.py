import os

import pytest

from aftercare.config import Settings
from aftercare.repositories.database import database_health


@pytest.mark.integration
def test_real_postgres_has_extension_and_migration():
    url = os.getenv("AFTERCARE_TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Dedicated PostgreSQL not started; set AFTERCARE_TEST_DATABASE_URL after migration"
        )
    result = database_health(Settings(_env_file=None, database_url=url))
    assert result.status == "ready", result.code
