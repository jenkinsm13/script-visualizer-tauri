# Intentionally empty. Submodules import their own deps lazily so that
# pulling one (e.g. prompt_gen) doesn't drag in heavyweight or unwanted
# deps from siblings (e.g. sd_connector's aiohttp-based legacy client).
