# -*- coding: utf-8 -*-
"""همه ماژول‌های سلف."""
from . import (antidelete, cloud_mod, core_mod, groups_mod, media,
               profile_mod, quickreply, reminders_mod, secretary,
               translate_voice)

MODULES = [core_mod.setup, media.setup, antidelete.setup, secretary.setup,
           quickreply.setup, profile_mod.setup, groups_mod.setup,
           reminders_mod.setup, translate_voice.setup, cloud_mod.setup]
