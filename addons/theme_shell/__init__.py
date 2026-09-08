# theme_shell: mostly a frontend-asset module (custom branded sidebar),
# plus one small backend controller aliasing /binget/* onto the same
# handler Odoo's core webclient already serves at /odoo/* — see
# controllers/main.py for why the alias needs to exist server-side too.
from . import controllers
