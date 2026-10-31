# -*- coding: utf-8 -*-
"""همه ماژول‌های سلف."""
from . import (ai_mod, antidelete, bomber_mod, boss_mod, cloud_mod, core_mod,
               games_mod, groups_mod, later_mod, media, msg_mod, profile_mod,
               quickreply, reminders_mod, secretary, tools_mod, translate_voice)

MODULES = [core_mod.setup, media.setup, antidelete.setup, secretary.setup,
           quickreply.setup, profile_mod.setup, groups_mod.setup,
           reminders_mod.setup, later_mod.setup, translate_voice.setup,
           cloud_mod.setup, msg_mod.setup, tools_mod.setup, games_mod.setup,
           ai_mod.setup, bomber_mod.setup, boss_mod.setup]
