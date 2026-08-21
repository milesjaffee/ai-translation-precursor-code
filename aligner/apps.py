import sys

from django.apps import AppConfig


class AlignerConfig(AppConfig):
    name = 'aligner'

    def ready(self):
        # Only pay for the model load when actually serving requests --
        # not for `manage.py migrate`/`makemigrations`/`shell`/etc.
        if 'runserver' in sys.argv:
            from . import model_singleton
            model_singleton.get_client()
