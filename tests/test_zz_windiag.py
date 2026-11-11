import sys
import pytest
from tenure import classify as c
from test_audit_cap_bypass import world, w9, wsh  # noqa: F401


@pytest.mark.skipif(sys.platform != "win32", reason="temporary Windows diagnosis")
def test_windiag(w9):
    full = c._abs(".hermes/skills", w9.proj, w9.h)
    c._CACHE.memo, c._CACHE.roots, c._CACHE.cwd, c._CACHE.home = {}, None, w9.proj, w9.h
    real = c._resolved(full)
    info = {"full": full, "real": real, "lexical": c._lexical(full), "roots": c._roots(), "user": c._user_homes()}
    for p in dict.fromkeys((full, real)):
        low = p.rstrip("/").casefold()
        info[p] = dict(tenure=bool(c.TENURE_NAMES.search(low + "/")), level=c._home_level(p), self=c._self_hit(low),
                       above=c._above_home(p))
    info["dir"] = c._dir_exists(full)
    info["res"] = wsh(w9, "mkdir -p .hermes/skills")
    info["fb"] = wsh(w9, "rm -rf @FB@")
    assert False, repr(info)
