# -*- coding: utf-8 -*-
"""
    productporter.app
    ~~~~~~~~~~~~~~~~~

    manages the app creation and configuration process

    :copyright: (c) 2014 by the ProductPorter Team.
    :license: BSD, see LICENSE for more details.
"""
import os
import logging
import datetime

from flask import Flask

from productporter.weixin.views import weixin
from productporter.product.views import product
from productporter.user.views import user
from productporter.user.models import Guest, User
from productporter.utils.helper import render_markup, root_url_prefix, \
        is_online, can_translate, can_comment, can_review, can_report, \
        can_topic, can_setgroup, format_date, is_moderator, is_admin
# extensions
from productporter.extensions import db, cache, themes, login_manager, migrate
# default config
from productporter.configs.default import DefaultConfig
from flask.ext.login import current_user

def create_app(config=None):
    """
    Creates the app.
    """
    static_url_path = ''
    instance_path = None
    if config is None:
        static_url_path = DefaultConfig.ROOT_URL_PREFIX + '/static'
        instance_path = DefaultConfig.INSTANCE_PATH
    else:
        static_url_path = config.ROOT_URL_PREFIX + '/static'
        instance_path = config.INSTANCE_PATH
    # Initialize the app
    app = Flask("productporter",
        static_url_path=static_url_path,
        instance_path=instance_path)

    # Use the default config and override it afterwards
    app.config.from_object('productporter.configs.default.DefaultConfig')
    # Update the config
    app.config.from_object(config)

    configure_blueprints(app)
    configure_extensions(app)
    configure_template_filters(app)
    configure_context_processors(app)
    configure_before_handlers(app)
    configure_errorhandlers(app)
    configure_logging(app)

    return app

def configure_blueprints(app):
    """
    Configures the blueprints
    """
    app.register_blueprint(weixin, url_prefix=root_url_prefix(app, 'WEIXIN_URL_PREFIX'))
    app.register_blueprint(product, url_prefix=root_url_prefix(app, 'PRODUCT_URL_PREFIX'))
    app.register_blueprint(user, url_prefix=root_url_prefix(app, 'USER_URL_PREFIX'))

def configure_extensions(app):
    """
    Configures the extensions
    """

    # Flask-SQLAlchemy
    db.init_app(app)

    # Flask-Migrate
    migrate.init_app(app, db)

    # Flask-Cache
    cache.init_app(app)

    # Flask-Themes
    themes.init_themes(app, app_identifier="productporter")

    # Flask-Login
    login_manager.login_view = app.config["LOGIN_VIEW"]
    login_manager.refresh_view = app.config["REAUTH_VIEW"]
    login_manager.anonymous_user = Guest

    @login_manager.user_loader
    def load_user(id):
        """
        Loads the user. Required by the `login` extension
        """
        u = db.session.query(User).filter(User.id == id).first()

        if u:
            return u
        else:
            return None

    login_manager.init_app(app)


def configure_template_filters(app):
    """
    Configures the template filters
    """
    app.jinja_env.filters['markup'] = render_markup
    app.jinja_env.filters['format_date'] = format_date
    app.jinja_env.filters['is_online'] = is_online
    app.jinja_env.filters['can_translate'] = can_translate
    app.jinja_env.filters['can_comment'] = can_comment
    app.jinja_env.filters['can_review'] = can_review
    app.jinja_env.filters['can_report'] = can_report
    app.jinja_env.filters['can_topic'] = can_topic
    app.jinja_env.filters['can_setgroup'] = can_setgroup
    app.jinja_env.filters['is_moderator'] = is_moderator
    app.jinja_env.filters['is_admin'] = is_admin

def configure_context_processors(app):
    """
    Configures the context processors
    """
    pass

def configure_before_handlers(app):
    """
    Configures the before request handlers
    """

    @app.before_request
    def update_lastseen():
        """
        Updates `lastseen` before every reguest if the user is authenticated
        """
        if current_user.is_authenticated():
            current_user.lastseen = datetime.datetime.utcnow()
            db.session.add(current_user)
            db.session.commit()


def configure_errorhandlers(app):
    """
    Configures the error handlers
    """
    # @app.errorhandler(403)
    # def forbidden_page(error):
    #     return render_template("errors/forbidden_page.html"), 403

    # @app.errorhandler(404)
    # def page_not_found(error):
    #     return render_template("errors/page_not_found.html"), 404

    # @app.errorhandler(500)
    # def server_error_page(error):
    #     return render_template("errors/server_error.html"), 500


def configure_logging(app):
    """
    Configures logging.
    """

    logs_folder = os.path.join(app.instance_path, "logs")
    from logging.handlers import SMTPHandler
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]')

    info_log = os.path.join(logs_folder, app.config['INFO_LOG'])

    info_file_handler = logging.handlers.RotatingFileHandler(
        info_log,
        maxBytes=100000,
        backupCount=10
    )

    info_file_handler.setLevel(logging.INFO)
    info_file_handler.setFormatter(formatter)
    app.logger.addHandler(info_file_handler)

    error_log = os.path.join(logs_folder, app.config['ERROR_LOG'])

    error_file_handler = logging.handlers.RotatingFileHandler(
        error_log,
        maxBytes=100000,
        backupCount=10
    )

    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)
    app.logger.addHandler(error_file_handler)

    if app.config["SEND_LOGS"]:
        mail_handler = \
            SMTPHandler(app.config['MAIL_SERVER'],
                        app.config['MAIL_SENDER'],
                        app.config['ADMINS'],
                        'ProductPorter application error',
                        (
                            app.config['MAIL_USERNAME'],
                            app.config['MAIL_PASSWORD'],
                        ))

        mail_handler.setLevel(logging.ERROR)
        mail_handler.setFormatter(logging.Formatter('''
            Message type:       %(levelname)s
            Location:           %(pathname)s:%(lineno)d
            Module:             %(module)s
            Function:           %(funcName)s
            Time:               %(asctime)s

            Message:

            %(message)s
            '''))
        app.logger.addHandler(mail_handler)
