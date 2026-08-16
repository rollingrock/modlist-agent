"""modlist-agent core — game-neutral.

Nothing in this package may import a game-specific module except `platforms`, which is
the single seam. If a change here needs an `if game == "fo4vr"`, the seam is in the
wrong place.
"""
__version__ = "0.1.0"
