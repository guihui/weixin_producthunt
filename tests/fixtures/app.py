# -*- coding: utf-8 -*-
"""
    productporter unit test
    ~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by the ProductPorter Team.
    :license: BSD, see LICENSE for more details.
"""
import pytest
import os

from productporter import create_app
from productporter.extensions import db
from productporter.configs.testing import TestingConfig as Config
from productporter.utils.helper import create_default_groups

@pytest.yield_fixture(autouse=True)
def app():
    """application with context."""
    app = create_app(Config)
    ctx = app.app_context()
    ctx.push()
    yield app
    ctx.pop()

@pytest.fixture()
def test_client(app):
    """test client"""
    return app.test_client()

@pytest.yield_fixture()
def database():
    """database setup."""
    db.create_all()  # Maybe use migration instead?
    yield db
    db.drop_all()

@pytest.fixture()
def default_groups(database):
    """Creates the default groups"""
    return create_default_groups()
